import ipaddress as ip
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .guard import check_commands
from .storage import ROOT, digest, write_json, write_yaml
from .validate import validate


def major_networks(prefixes):
    results = set()
    for prefix in prefixes:
        addr = ip.IPv4Interface(prefix).ip
        first = int(str(addr).split('.')[0])
        bits = 8 if first < 128 else (16 if first < 192 else 24)
        results.add(str(ip.IPv4Network(f'{addr}/{bits}', strict=False).network_address))
    return sorted(results)


def acl_address(value):
    if value == 'any': return value
    net = ip.IPv4Network(value)
    if net.prefixlen == 32: return f'host {net.network_address}'
    return f'{net.network_address} {net.hostmask}'


def render_device(device):
    if device['kind'] in ('pc', 'server'):
        return None
    env = Environment(loader=FileSystemLoader(ROOT / 'templates'), undefined=StrictUndefined,
                      trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True)
    env.filters.update(address=lambda s: str(ip.IPv4Interface(s).ip),
                       netmask=lambda s: str(ip.IPv4Interface(s).netmask),
                       network=lambda s: str(ip.IPv4Network(s, strict=False).network_address),
                       wildcard=lambda s: str(ip.IPv4Network(s, strict=False).hostmask),
                       major_networks=major_networks, acl_address=acl_address)
    text = env.get_template('device.cfg.j2').render(device=device)
    text = '\n'.join(line for line in text.splitlines() if line.strip()) + '\n'
    guard = check_commands(text, device)
    if not guard['allowed']:
        raise ValueError('生成配置未通过护栏：' + json.dumps(guard, ensure_ascii=False))
    return text


def check_command(check, devices):
    if check['type'] == 'ping': return f"ping {check['target']}"
    if check['type'] == 'route': return 'show ip route'
    kind = devices[check['device']]['kind']
    return ('tracert ' if kind in ('pc', 'server') else 'traceroute ') + check['target']


def export(data, out, audit):
    result = validate(data)
    audit.json('validation.json', result)
    if not result['deployable']:
        raise ValueError('拓扑不可部署；查看 validation.json。澄清/拒绝状态不生成配置。')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    preview = out / 'preview'
    preview.mkdir()
    write_yaml(out / 'topology.yaml', data)
    devices = {d['name']: d for d in data['devices']}
    files = {}
    for d in data['devices']:
        cfg = render_device(d)
        if cfg:
            path = preview / (d['name'] + '.cfg')
            path.write_text(cfg, encoding='ascii')
            files[str(path.relative_to(out)).replace('\\', '/')] = digest(path)
    expected = [{'id': c['id'], 'device': c['device'], 'command': check_command(c, devices),
                 'type': c['type'], 'output': '', 'collected_at': '', 'provenance': 'not_run'}
                for c in data['checks']]
    write_json(out / 'observations.template.json', {'schema_version': '1.0', 'observations': expected})
    files['topology.yaml'] = digest(out / 'topology.yaml')
    write_json(out / 'manifest.json', {'name': data['name'], 'source': data['source'],
                'deployment_status': 'not_run', 'approval_status': 'pending', 'files_sha256': files})
    lines = ['# Packet Tracer 部署与采集指南', '',
             '状态：配置预览已生成，尚未人工确认或部署。配置仅适用于本地隔离仿真。', '',
             '## 1. 准备', '',
             '在空白拓扑或另存的工程副本操作。配置为完整初始配置，不会自动清理旧路由、ACL 或旧地址；禁止直接当作任意旧工程的增量补丁。',
             '对照现有配置后运行 `python netlab.py approve <本目录>`，检查摘要并亲自输入 CONFIRM，随后才使用 released 目录。', '',
             '## 2. 设备和地址', '', '|设备|型号|接口|模式|IPv4|网关|', '|---|---|---|---|---|---|']
    for d in data['devices']:
        for i in d['interfaces']:
            lines.append(f"|{d['name']}|{d['model']}|{i['name']}|{i['mode']}|{i.get('ipv4', '-')}|{d.get('gateway','-')}|")
        if d.get('services'):
            lines.append(f"\n{d['name']}：在 Services 中开启 HTTP。服务页面属于 GUI 操作，不由 IOS 配置文件完成。\n")
    lines += ['', '## 3. 接线', '', '|端点 A|端点 B|线缆|', '|---|---|---|']
    for l in data['links']:
        lines.append(f"|{l['a']['device']} {l['a']['interface']}|{l['b']['device']} {l['b']['interface']}|{l['medium']}|")
    lines += ['', '串口设备先关机安装 HWIC-2T 后开机；有 clock_rate 的接口是计划 DCE 端，连接后需核对实际 DCE 归属。', '',
              '## 4. 配置', '',
              '路由器/交换机打开 CLI，拒绝初始配置向导，回到用户/特权执行模式后粘贴对应 released/*.cfg。遇到 Invalid input 立即停止并保存原始错误。',
              'PC/Server 在 Desktop → IP Configuration 填静态地址、掩码和网关。等链路及路由收敛后执行检查。', '',
              '## 5. 验收采集', '', '|检查 ID|设备|命令|预期|', '|---|---|---|---|']
    for c in data['checks']:
        expectation = {k: v for k, v in c.items() if k not in ('id', 'device', 'type')}
        lines.append(f"|{c['id']}|{c['device']}|`{check_command(c, devices)}`|{json.dumps(expectation, ensure_ascii=False)}|")
    lines += ['', '将完整命令输出填入 observations.template.json 的 output，填写 collected_at，provenance 改为 packet_tracer_manual。保存为 observations.json 后运行 verify。',
              '若首次 ping 因 ARP 超时，保留首次输出，预热后另作一次采集；不要静默替换。trace 超时或路由表缺失记为未通过/无法解析。',
              '人工采集会如实记录，不能据此宣称自动执行验收。', '',
              '## 6. 留存', '', '另存 .pkt 副本，保留原始命令输出、审批记录与运行日志。']
    (out / 'PT操作指南.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    audit.json('export.json', {'directory': str(out.resolve()), 'files_sha256': files, 'deployment_status': 'not_run'})
    return out

