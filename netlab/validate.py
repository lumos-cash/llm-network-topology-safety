import ipaddress as ip
import json
import re

from jsonschema import Draft202012Validator, FormatChecker

from .storage import ROOT


def schema():
    return json.loads((ROOT / 'schemas/topology.schema.json').read_text(encoding='utf-8'))


def validate(data):
    errors, warnings = [], []

    def err(code, path, message):
        errors.append({'code': code, 'path': path, 'message': message})

    validator = Draft202012Validator(schema(), format_checker=FormatChecker())
    for e in validator.iter_errors(data):
        err('schema', '/'.join(map(str, e.absolute_path)), e.message)
    if errors or data['status'] != 'ready':
        return {'valid': not errors, 'deployable': False, 'errors': errors, 'warnings': warnings}

    devices, ports, addresses = {}, {}, {}
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(a, b):
        parent[find(a)] = find(b)

    def portkey(d, i):
        return d + ':' + i

    def vnode(d, v):
        return d + ':#vlan' + str(v)

    for d in data['devices']:
        dn = d['name']
        if dn in devices:
            err('duplicate_device', dn, '设备名称重复')
        devices[dn] = d
        allowed_models = {'router': ['2911', '1941'], 'switch': ['2960-24TT'],
                          'l3_switch': ['3560-24PS'], 'pc': ['PC-PT'], 'server': ['Server-PT']}
        if d['model'] not in allowed_models[d['kind']]:
            err('platform', dn, '设备类型与型号不一致')
        vids = [v['id'] for v in d.get('vlans', [])]
        if len(set(vids)) != len(vids):
            err('duplicate_vlan', dn, 'VLAN ID 重复')
        if d['kind'] in ('pc', 'server', 'switch') and (d.get('routing') or d.get('static_routes') or d.get('acls')):
            err('platform', dn, '当前设备不支持本 DSL 中的三层路由/ACL 配置')
        for iface in d['interfaces']:
            name = iface['name']
            key = portkey(dn, name)
            if key in ports:
                err('duplicate_interface', key, '接口名称重复')
            ports[key] = iface
            find(key)
            mode = iface['mode']
            physical = name.split('.')[0]
            physical_ok = False
            if d['kind'] in ('pc', 'server'):
                physical_ok = name == 'FastEthernet0'
            elif d['kind'] == 'router':
                maximum = 2 if d['model'] == '2911' else 1
                physical_ok = bool(re.fullmatch(rf'GigabitEthernet0/[0-{maximum}]|Serial0/0/[01]|Loopback\d+', physical))
            else:
                physical_ok = bool(re.fullmatch(r'FastEthernet0/(?:[1-9]|1\d|2[0-4])|GigabitEthernet0/[12]|Vlan\d+', name))
            if not physical_ok:
                err('platform_interface', key, '接口不属于本项目支持的型号/模块组合')
            if d['kind'] == 'switch' and mode == 'routed':
                err('platform_interface', key, '二层交换机物理端口不能配置路由接口地址')
            if 'ipv4' not in iface and mode in ('routed', 'svi', 'subinterface'):
                parent_of_sub = any(i['name'].startswith(name + '.') and i['mode'] == 'subinterface' for i in d['interfaces'])
                if not parent_of_sub:
                    err('missing_address', key, '三层接口缺少地址，且不是路由子接口的父接口')
            if mode in ('access', 'trunk', 'svi') and d['kind'] not in ('switch', 'l3_switch'):
                err('platform', key, '该模式要求交换机')
            if mode == 'svi' and d['kind'] != 'l3_switch':
                err('platform', key, '本项目只在三层交换机上配置 SVI 网关')
            if d['kind'] in ('pc', 'server') and (mode != 'routed' or 'ipv4' not in iface):
                err('host_interface', key, '主机接口需要 routed 和静态 IPv4')
            if mode in ('access', 'svi'):
                if iface['vlan'] not in vids:
                    err('vlan_reference', key, '引用的 VLAN 未在设备上定义')
                union(key, vnode(dn, iface['vlan']))
            if mode == 'svi' and name != 'Vlan' + str(iface['vlan']):
                err('vlan_reference', key, 'SVI 名称必须与 VLAN ID 一致')
            if mode == 'trunk':
                if len(set(iface['allowed_vlans'])) != len(iface['allowed_vlans']):
                    err('vlan_reference', key, 'Trunk VLAN 重复')
                for v in iface['allowed_vlans']:
                    if v not in vids:
                        err('vlan_reference', key, f'Trunk 引用未定义 VLAN {v}')
            if mode == 'subinterface':
                if d['kind'] != 'router' or '.' not in name or name.split('.')[0] not in [i['name'] for i in d['interfaces']]:
                    err('subinterface', key, '路由子接口必须有对应物理父接口')
            if 'clock_rate' in iface and not name.startswith('Serial'):
                err('clock_rate', key, '时钟仅用于串口 DCE 端')
            if 'ipv4' in iface:
                try:
                    addr = ip.IPv4Interface(iface['ipv4'])
                    if addr.network.prefixlen <= 30 and addr.ip in (addr.network.network_address, addr.network.broadcast_address):
                        err('host_address', key, '不能使用网络地址或广播地址作为接口 IP')
                    if addr.ip.is_multicast or addr.ip.is_loopback or addr.ip.is_unspecified or addr.ip.is_reserved:
                        err('host_address', key, '不能使用组播、环回、未指定或保留地址')
                    if any(a.ip == addr.ip for a in addresses.values()):
                        err('duplicate_ip', key, f'地址 {addr.ip} 已被使用')
                    addresses[key] = addr
                except ValueError as e:
                    err('ipv4', key, str(e))

    used = set()
    for index, link in enumerate(data['links']):
        a, b = [portkey(link[x]['device'], link[x]['interface']) for x in ('a', 'b')]
        label = f'links/{index}'
        if a == b:
            err('link', label, '接口不能连接自己')
        if a not in ports or b not in ports:
            err('link_reference', label, '链路端点不存在')
            continue
        for p in (a, b):
            if p in used:
                err('link', label, f'物理接口 {p} 被多次连接')
            used.add(p)
            if ports[p]['mode'] in ('subinterface', 'svi') or p.split(':')[1].startswith('Loopback'):
                err('link', label, '虚拟接口不能作为物理接线端点')
        serial = [p.split(':')[1].startswith('Serial') for p in (a, b)]
        if (link['medium'] == 'serial' and not all(serial)) or (link['medium'] == 'copper' and any(serial)):
            err('link_medium', label, '接口类型与线缆不一致')
        if link['medium'] == 'serial' and sum('clock_rate' in ports[p] for p in (a, b)) != 1:
            err('serial_clock', label, '串行线必须明确一个 DCE 端及 clock_rate')
        pa, pb = ports[a], ports[b]
        if pa['mode'] == pb['mode'] == 'trunk':
            if set(pa['allowed_vlans']) != set(pb['allowed_vlans']):
                err('trunk_mismatch', label, '当前 DSL 要求两端 Trunk allowed VLAN 一致')
            for v in set(pa['allowed_vlans']) & set(pb['allowed_vlans']):
                union(vnode(a.split(':')[0], v), vnode(b.split(':')[0], v))
        elif 'trunk' in (pa['mode'], pb['mode']):
            trunk, other = (a, b) if pa['mode'] == 'trunk' else (b, a)
            od, oi = other.split(':')
            subs = [p for p in ports if p.startswith(od + ':' + oi + '.') and ports[p]['mode'] == 'subinterface']
            if not subs:
                err('trunk_mismatch', label, 'Trunk 对端没有路由子接口')
            for sub in subs:
                v = ports[sub]['vlan']
                if v not in ports[trunk]['allowed_vlans']:
                    err('trunk_mismatch', label, f'子接口 VLAN {v} 不在 Trunk 允许列表')
                else:
                    union(sub, vnode(trunk.split(':')[0], v))
        else:
            if pa['mode'] == pb['mode'] == 'access' and pa['vlan'] != pb['vlan']:
                err('access_vlan_mismatch', label, '本项目不支持两端不同 VLAN 的接入口互联')
            union(a, b)
            if a in addresses and b in addresses and addresses[a].network != addresses[b].network:
                err('link_subnet', label, '直连接口不在同一子网或掩码不一致')

    items = list(addresses.items())
    for i, (ka, aa) in enumerate(items):
        for kb, ab in items[i + 1:]:
            if aa.network.overlaps(ab.network):
                if aa.network != ab.network or find(ka) != find(kb):
                    err('subnet_overlap', ka, f'与 {kb} 子网重叠但掩码或广播域不一致')

    for dn, d in devices.items():
        local = {k: a for k, a in addresses.items() if k.startswith(dn + ':')}
        if d['kind'] in ('pc', 'server') and 'gateway' in d:
            gw = ip.IPv4Address(d['gateway'])
            matches = [(k, a) for k, a in local.items() if gw in a.network and gw != a.ip]
            if not matches:
                err('gateway', dn, '网关不在主机子网或等于主机地址')
            elif not any(a.ip == gw and find(k) == find(hostk)
                         and devices[k.split(':')[0]]['kind'] in ('router', 'l3_switch')
                         for hostk, _ in matches for k, a in addresses.items()):
                err('gateway_reference', dn, '网关不存在于同一广播域的三层设备')
        routing = d.get('routing', {})
        if 'rip' in routing and 'ospf' in routing:
            err('routing', dn, '当前阶段不支持同时运行 RIP 与 OSPF/重分发')
        for kind, r in routing.items():
            nets = r['networks']
            for n in nets:
                prefix = n if kind == 'rip' else n['prefix']
                try:
                    net = ip.IPv4Network(prefix, strict=True)
                    if not any(a.ip in net for a in local.values()):
                        err('routing_network', dn, f'{prefix} 不匹配本设备任一接口')
                except ValueError as e:
                    err('routing_network', dn, str(e))
            if kind == 'rip' and r['version'] == 1:
                warnings.append({'code': 'ripv1_vlsm', 'path': dn, 'message': 'RIPv1 不支持 VLSM；按实验预期判断，不能保证正常互通'})
        for route in d.get('static_routes', []):
            try:
                ip.IPv4Network(route['prefix'], strict=True)
                nh = ip.IPv4Address(route['next_hop'])
                if not any(nh in a.network and nh != a.ip for a in local.values()):
                    err('next_hop', dn, '静态路由下一跳必须在直连子网内且非本机地址')
                if not any(a.ip == nh for k, a in addresses.items() if not k.startswith(dn + ':')):
                    err('next_hop_reference', dn, '下一跳未在拓扑中定义')
            except ValueError as e:
                err('static_route', dn, str(e))
        aclids = set()
        bindings = set()
        for acl in d.get('acls', []):
            if acl['number'] in aclids or (acl['interface'], acl['direction']) in bindings:
                err('acl_duplicate', dn, 'ACL 编号或接口方向绑定重复')
            aclids.add(acl['number']); bindings.add((acl['interface'], acl['direction']))
            if portkey(dn, acl['interface']) not in ports:
                err('acl_reference', dn, 'ACL 接口不存在')
            for rule in acl['rules']:
                if 'destination_port' in rule and rule['protocol'] not in ('tcp', 'udp'):
                    err('acl_port', dn, '端口仅适用于 TCP/UDP')
                for field in ('source', 'destination'):
                    if rule[field] != 'any':
                        try:
                            ip.IPv4Network(rule[field], strict=True)
                        except ValueError as e:
                            err('acl_address', dn, str(e))

    # OSPF adjacent area consistency; resolve each connected routed endpoint.
    def areas(key):
        d = devices[key.split(':')[0]]
        ospf = d.get('routing', {}).get('ospf', {})
        found = set()
        if key in addresses:
            for n in ospf.get('networks', []):
                try:
                    if addresses[key].ip in ip.IPv4Network(n['prefix']):
                        found.add(n['area'])
                except ValueError:
                    pass
        return found

    for link in data['links']:
        a, b = [portkey(link[x]['device'], link[x]['interface']) for x in ('a', 'b')]
        if a in ports and b in ports:
            aa, bb = areas(a), areas(b)
            if len(aa) > 1 or len(bb) > 1 or (aa and bb and aa != bb):
                err('ospf_area', a, f'与 {b} 的 OSPF 区域配置冲突')
    ids = set()
    for c in data['checks']:
        if c['id'] in ids:
            err('check_id', c['id'], '验收 ID 重复')
        ids.add(c['id'])
        if c['device'] not in devices:
            err('check_reference', c['id'], '验收源设备不存在')
        if 'target' in c and not any(str(a.ip) == c['target'] for a in addresses.values()):
            err('check_target', c['id'], '测试目标必须为本地仿真拓扑内已定义地址')
        if c['type'] == 'route':
            try:
                ip.IPv4Network(c['prefix'], strict=True)
            except ValueError as e:
                err('check_prefix', c['id'], str(e))
        if c['type'] == 'trace':
            owners = {str(a.ip): key.split(':')[0] for key, a in addresses.items()}
            visited = set()
            for hop in c['via']:
                owner = owners.get(hop)
                if owner is None:
                    err('trace_hop', c['id'], f'路径跳点 {hop} 未在拓扑中定义')
                elif owner in visited:
                    err('trace_repeated_device', c['id'], f'正常无环路径重复经过 {owner}；不能把同一设备的进出接口当作两跳')
                else:
                    visited.add(owner)
    return {'valid': not errors, 'deployable': not errors, 'errors': errors, 'warnings': warnings}

