"""Manually authored baselines. NOT DeepSeek output or PT test evidence."""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / '.vendor'), str(ROOT)]
from netlab.storage import write_yaml, write_json


def iface(name, address=None, mode='routed', **kw):
    return {'name': name, 'mode': mode, **({'ipv4': address} if address else {}), **kw}


def pc(name, address, gateway=None):
    return {'name': name, 'kind': 'pc', 'model': 'PC-PT', 'interfaces': [iface('FastEthernet0', address)],
            **({'gateway': gateway} if gateway else {})}


def router(name, interfaces):
    return {'name': name, 'kind': 'router', 'model': '2911', 'interfaces': interfaces}


def link(a, ai, b, bi, medium='copper'):
    return {'a': {'device': a, 'interface': ai}, 'b': {'device': b, 'interface': bi}, 'medium': medium}


def ping(id, device, target, expected=True):
    return {'id': id, 'type': 'ping', 'device': device, 'target': target, 'expected': expected}


def base(name, intent, devices, links, checks):
    return {'schema_version': '1.0', 'status': 'ready', 'name': name, 'source': 'manual_reference',
            'intent': intent, 'devices': devices, 'links': links, 'checks': checks}


def triangle(protocol, version=2):
    r0 = router('Router0', [iface('GigabitEthernet0/0', '192.168.16.126/25'), iface('GigabitEthernet0/1', '10.0.0.1/30'), iface('Serial0/0/0', '30.0.0.1/30', clock_rate=64000)])
    r1 = router('Router1', [iface('GigabitEthernet0/0', '192.168.16.190/26'), iface('GigabitEthernet0/1', '20.0.0.1/30'), iface('Serial0/0/0', '30.0.0.2/30')])
    r2 = router('Router2', [iface('GigabitEthernet0/0', '10.0.0.2/30'), iface('GigabitEthernet0/1', '20.0.0.2/30')])
    import ipaddress
    for r in (r0, r1, r2):
        networks = [str(ipaddress.IPv4Interface(i['ipv4']).network) for i in r['interfaces']]
        if protocol == 'rip':
            r['routing'] = {'rip': {'version': version, 'auto_summary': version == 1, 'networks': networks}}
        else:
            r['routing'] = {'ospf': {'process_id': 100, 'networks': [{'prefix': n, 'area': 0} for n in networks]}}
    devices = [r0, r1, r2, pc('PC0', '192.168.16.1/25', '192.168.16.126'), pc('PC1', '192.168.16.129/26', '192.168.16.190')]
    links = [link('PC0', 'FastEthernet0', 'Router0', 'GigabitEthernet0/0'), link('PC1', 'FastEthernet0', 'Router1', 'GigabitEthernet0/0'),
             link('Router0', 'GigabitEthernet0/1', 'Router2', 'GigabitEthernet0/0'), link('Router1', 'GigabitEthernet0/1', 'Router2', 'GigabitEthernet0/1'),
             link('Router0', 'Serial0/0/0', 'Router1', 'Serial0/0/0', 'serial')]
    expected = protocol != 'rip' or version == 2
    checks = [ping('pc0_pc1', 'PC0', '192.168.16.129', expected), ping('pc1_pc0', 'PC1', '192.168.16.1', expected)]
    if expected:
        checks.append({'id': 'remote_route', 'type': 'route', 'device': 'Router0', 'prefix': '192.168.16.128/26', 'protocol': 'R' if protocol == 'rip' else 'O'})
    if protocol == 'ospf':
        checks += [{'id': 'least_cost_path', 'type': 'trace', 'device': 'PC0', 'target': '192.168.16.129', 'via': ['192.168.16.126', '10.0.0.2', '20.0.0.1']},
                   {'id': 'ecmp_route', 'type': 'route', 'device': 'Router2', 'prefix': '30.0.0.0/30', 'protocol': 'O', 'next_hops': ['10.0.0.1', '20.0.0.1']}]
    name = 'lab4_11_ospf' if protocol == 'ospf' else 'lab4_10_ripv' + str(version)
    return base(name, '课件人工基线；比较 RIP 版本或 OSPF 选路。尚未在 PT 实测。', devices, links, checks)


def lan():
    s = {'name': 'Switch0', 'kind': 'switch', 'model': '2960-24TT', 'vlans': [{'id': 10, 'name': 'LAN'}],
         'interfaces': [iface('FastEthernet0/1', mode='access', vlan=10), iface('FastEthernet0/2', mode='access', vlan=10)]}
    return base('uc06_lan', '两台 PC 通过交换机连接，同一 /24 网络互通，不使用路由器。',
                [s, pc('PC0', '192.168.1.1/24'), pc('PC1', '192.168.1.2/24')],
                [link('PC0', 'FastEthernet0', 'Switch0', 'FastEthernet0/1'), link('PC1', 'FastEthernet0', 'Switch0', 'FastEthernet0/2')],
                [ping('pc0_pc1', 'PC0', '192.168.1.2'), ping('pc1_pc0', 'PC1', '192.168.1.1')])


def http():
    server = {'name': 'Server0', 'kind': 'server', 'model': 'Server-PT',
              'interfaces': [iface('FastEthernet0', '192.168.0.2/24')], 'services': ['http']}
    return base('lab6_6_http', '实验6-6：PC0 与 HTTP 服务器直连；GUI 开启 HTTP 并另行观察 HTTP/TCP，ping 仅验证连通性。',
                [pc('PC0', '192.168.0.1/24'), server], [link('PC0', 'FastEthernet0', 'Server0', 'FastEthernet0')],
                [ping('http_server_reachable', 'PC0', '192.168.0.2')])


def vlsm():
    r0 = router('Router0', [iface('GigabitEthernet0/0', '218.75.230.30/27'), iface('GigabitEthernet0/1', '218.75.230.46/28'), iface('GigabitEthernet0/2', '218.75.230.81/30')])
    r1 = router('Router1', [iface('GigabitEthernet0/0', '218.75.230.78/28'), iface('GigabitEthernet0/1', '218.75.230.62/28'), iface('GigabitEthernet0/2', '218.75.230.82/30')])
    r0['static_routes'] = [{'prefix': n, 'next_hop': '218.75.230.82'} for n in ['218.75.230.48/28', '218.75.230.64/28']]
    r1['static_routes'] = [{'prefix': n, 'next_hop': '218.75.230.81'} for n in ['218.75.230.0/27', '218.75.230.32/28']]
    hosts = [pc('PC0', '218.75.230.1/27', '218.75.230.30'), pc('PC1', '218.75.230.33/28', '218.75.230.46'),
             pc('PC2', '218.75.230.49/28', '218.75.230.62'), pc('PC3', '218.75.230.65/28', '218.75.230.78')]
    links = [link('PC0', 'FastEthernet0', 'Router0', 'GigabitEthernet0/0'), link('PC1', 'FastEthernet0', 'Router0', 'GigabitEthernet0/1'),
             link('PC2', 'FastEthernet0', 'Router1', 'GigabitEthernet0/1'), link('PC3', 'FastEthernet0', 'Router1', 'GigabitEthernet0/0'),
             link('Router0', 'GigabitEthernet0/2', 'Router1', 'GigabitEthernet0/2')]
    return base('lab4_5_vlsm', '实验4-5人工基线：四个不同长度子网加/30互联，静态路由；公网数字地址仅用于本地仿真。', [r0, r1] + hosts, links,
                [ping('pc0_pc2', 'PC0', '218.75.230.49'), ping('pc3_pc1', 'PC3', '218.75.230.33'),
                 {'id': 'r0_remote', 'type': 'route', 'device': 'Router0', 'prefix': '218.75.230.48/28', 'protocol': 'S', 'next_hops': ['218.75.230.82']}])


def vlan_routing(svi=False):
    kind = 'l3_switch' if svi else 'switch'
    s = {'name': 'Switch0', 'kind': kind, 'model': '3560-24PS' if svi else '2960-24TT',
         'vlans': [{'id': 10, 'name': 'Finance'}, {'id': 20, 'name': 'Marketing'}], 'interfaces': []}
    hosts, links = [], []
    for index in range(6):
        v = 10 if index < 3 else 20
        subnet = 1 if v == 10 else 2
        s['interfaces'].append(iface(f'FastEthernet0/{index+1}', mode='access', vlan=v))
        hosts.append(pc(f'PC{index}', f'192.168.{subnet}.{index%3+1}/24', f'192.168.{subnet}.254'))
        links.append(link(f'PC{index}', 'FastEthernet0', 'Switch0', f'FastEthernet0/{index+1}'))
    devices = [s] + hosts
    if svi:
        s['interfaces'] += [iface('Vlan10', '192.168.1.254/24', mode='svi', vlan=10), iface('Vlan20', '192.168.2.254/24', mode='svi', vlan=20)]
    else:
        s['interfaces'].append(iface('GigabitEthernet0/1', mode='trunk', allowed_vlans=[10, 20]))
        devices.append(router('Router0', [iface('GigabitEthernet0/0'), iface('GigabitEthernet0/0.10', '192.168.1.254/24', mode='subinterface', vlan=10),
                                          iface('GigabitEthernet0/0.20', '192.168.2.254/24', mode='subinterface', vlan=20)]))
        links.append(link('Switch0', 'GigabitEthernet0/1', 'Router0', 'GigabitEthernet0/0'))
    checks = [ping(f'p{i}_p{j}', f'PC{i}', hosts[j]['interfaces'][0]['ipv4'].split('/')[0]) for i in range(6) for j in range(6) if i != j]
    return base('uc05_svi' if svi else 'uc05_router_on_stick', 'VLAN10/20 各三台 PC，网关 .254，验证六台 PC 两两互通。', devices, links, checks)


def acl_lab():
    r0 = router('Router0', [iface('GigabitEthernet0/0', '192.168.0.254/24'), iface('GigabitEthernet0/1', '10.0.0.1/30')])
    r1 = router('Router1', [iface('GigabitEthernet0/0', '192.168.1.254/24'), iface('GigabitEthernet0/1', '10.0.0.2/30')])
    r0['static_routes'] = [{'prefix': '192.168.1.0/24', 'next_hop': '10.0.0.2'}]
    r1['static_routes'] = [{'prefix': '192.168.0.0/24', 'next_hop': '10.0.0.1'}]
    rules = [dict(action='deny', protocol='tcp', source='192.168.0.0/24', destination='192.168.1.2/32', destination_port=80),
             *[dict(action='deny', protocol='tcp', source='192.168.0.1/32', destination='192.168.1.2/32', destination_port=p) for p in (20, 21)],
             dict(action='deny', protocol='ip', source='192.168.0.2/32', destination='192.168.1.1/32'),
             dict(action='deny', protocol='icmp', source='192.168.0.0/24', destination='10.0.0.2/32'),
             dict(action='permit', protocol='ip', source='any', destination='any')]
    r1['acls'] = [{'number': 100, 'rules': rules, 'interface': 'GigabitEthernet0/1', 'direction': 'in'}]
    switches = [{'name': f'Switch{i}', 'kind': 'switch', 'model': '2960-24TT', 'vlans': [{'id': 1, 'name': 'default'}],
                 'interfaces': [iface(f'FastEthernet0/{p}', mode='access', vlan=1) for p in (1, 2, 3)]} for i in (0, 1)]
    hosts = [pc('PC0', '192.168.0.1/24', '192.168.0.254'), pc('PC1', '192.168.0.2/24', '192.168.0.254'), pc('PC2', '192.168.1.1/24', '192.168.1.254'),
             {'name': 'Server0', 'kind': 'server', 'model': 'Server-PT', 'interfaces': [iface('FastEthernet0', '192.168.1.2/24')], 'gateway': '192.168.1.254', 'services': ['http']}]
    links = [link('Router0', 'GigabitEthernet0/1', 'Router1', 'GigabitEthernet0/1'),
             link('Router0', 'GigabitEthernet0/0', 'Switch0', 'FastEthernet0/3'), link('Router1', 'GigabitEthernet0/0', 'Switch1', 'FastEthernet0/3'),
             link('PC0', 'FastEthernet0', 'Switch0', 'FastEthernet0/1'), link('PC1', 'FastEthernet0', 'Switch0', 'FastEthernet0/2'),
             link('PC2', 'FastEthernet0', 'Switch1', 'FastEthernet0/1'), link('Server0', 'FastEthernet0', 'Switch1', 'FastEthernet0/2')]
    return base('lab7_1_acl', '实验7-1：扩展 ACL 阻断指定 HTTP/FTP/主机/ICMP；当前机器可读检查仅覆盖 ICMP，HTTP/FTP 需 GUI 留证，不能仅凭 ping 宣称业务全部通过。',
                [r0, r1] + switches + hosts, links, [ping('pc1_pc2_denied', 'PC1', '192.168.1.1', False), ping('pc0_r1_denied', 'PC0', '10.0.0.2', False), ping('pc0_pc2_allowed', 'PC0', '192.168.1.1')])


if __name__ == '__main__':
    folder = ROOT / 'examples'; folder.mkdir(exist_ok=True)
    for d in (triangle('rip', 1), triangle('rip', 2), triangle('ospf'), lan(), http(), vlsm(), vlan_routing(), vlan_routing(True), acl_lab()):
        write_yaml(folder / (d['name'] + '.yaml'), d)
    write_yaml(folder / 'uc11_clarification.yaml', {'schema_version': '1.0', 'status': 'needs_clarification',
        'name': 'uc11_clarification', 'source': 'manual_reference', 'intent': '二十多台机器分办公和测试两个网，需要上网和安全。',
        'questions': ['两个部门分别多少台机器？', '测试网能否访问办公网？有哪些必须开放的服务？', '模拟出口和可用地址段是什么？']})
    write_yaml(folder / 'uc12_rejected.yaml', {'schema_version': '1.0', 'status': 'rejected',
        'name': 'uc12_rejected', 'source': 'manual_reference', 'intent': '从 192.168.1.0/25 分配三个 /24。',
        'reason': '/25 只有 128 个地址，不能包含三个各 256 地址的 /24；请扩大地址块（例如合适的 /22）或减小各部门子网需求。'})
    req = ROOT / 'requirements'; req.mkdir(exist_ok=True)
    prompts = {
      '01_ripv2': '本地 Packet Tracer：三台 2911 路由器 Router0、Router1、Router2 和两台 PC。PC0=192.168.16.1/25，网关 Router0 G0/0=192.168.16.126/25；PC1=192.168.16.129/26，网关 Router1 G0/0=192.168.16.190/26。Router0 G0/1=10.0.0.1/30 连接 Router2 G0/0=10.0.0.2/30；Router2 G0/1=20.0.0.2/30 连接 Router1 G0/1=20.0.0.1/30；Router0 S0/0/0=30.0.0.1/30 连接 Router1 S0/0/0=30.0.0.2/30。Router0 串口为 DCE，clock rate 64000。配置 RIPv2，关闭自动汇总，验证两个 PC 双向互通和 Router0 到远端 LAN 的 RIP 路由。接口名写完整。',
      '02_ospf': '以上同一三角拓扑与编址不变；在空白初始配置中使用 OSPF 进程 100、全部 area 0；验证双向 ping、PC0 经 Router0-Router2-Router1 到 PC1 的低代价路径、Router0 的远端 OSPF 路由，以及 Router2 到 30.0.0.0/30 的两个等价下一跳 10.0.0.1 和 20.0.0.1。',
      '03_lan': '本地 Packet Tracer：2960-24TT Switch0，PC0 FastEthernet0 接 Switch0 FastEthernet0/1，PC1 FastEthernet0 接 Switch0 FastEthernet0/2。两端口为 VLAN 10 的 access，VLAN 名为 LAN。PC0=192.168.1.1/24，PC1=192.168.1.2/24，不配默认网关。验证双向 ping。'}
    prompts['02_ospf'] = prompts['01_ripv2'].split('配置 RIPv2')[0] + prompts['02_ospf']
    for name, text in prompts.items(): (req / (name + '.txt')).write_text(text + '\n', encoding='utf-8')
    print('Created manual_reference YAML and three natural-language requirements; no model/device runs.')

