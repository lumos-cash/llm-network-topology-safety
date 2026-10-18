"""Parse supplied PT evidence. Never fabricates or executes network probes."""
import ipaddress as ip
import re

from .render import check_command

IP = r'\d{1,3}(?:\.\d{1,3}){3}'


def bind_to_oracle(data, observations):
    """Rebind evidence by device/command, preserving source IDs and original output.

    A model's check identifiers need not match the independently authored oracle.
    Conflicting snapshots for the same command require an explicit user choice.
    """
    rows = observations.get('observations', [])
    if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
        raise ValueError('observations 必须是对象数组')
    ids = [r.get('id') for r in rows]
    if any(not isinstance(i, str) for i in ids) or len(ids) != len(set(ids)):
        raise ValueError('原始观测必须有唯一字符串 ID')
    devices = {d['name']: d for d in data['devices']}
    bound = []
    for check in data['checks']:
        command = check_command(check, devices)
        matches = [r for r in rows if r.get('device') == check['device'] and r.get('command') == command]
        if not matches:
            continue
        signatures = {(r.get('output'), r.get('provenance')) for r in matches}
        if len(signatures) > 1:
            raise ValueError(f"{check['device']} / {command} 有不同采集结果，请选定同一次采集的证据文件，不能自动择优")
        row = dict(matches[0])
        row.update(id=check['id'], source_observation_ids=[r['id'] for r in matches])
        bound.append(row)
    return dict(observations, observations=bound, binding='independent_oracle_by_device_command')


def ping_percent(text, target):
    if target not in text:
        return None
    m = re.search(r'Success rate is\s+(\d+)\s+percent\s*\((\d+)/(\d+)\)', text, re.I)
    if m:
        good, total = int(m[2]), int(m[3])
        return good * 100 / total if 0 <= good <= total and total > 0 else None
    m = re.search(r'(?:Packets:\s*)?Sent\s*=\s*(\d+),\s*Received\s*=\s*(\d+),\s*Lost\s*=\s*(\d+)', text, re.I)
    if not m:
        m = re.search(r'已发送\s*=\s*(\d+)，?\s*已接收\s*=\s*(\d+)，?\s*丢失\s*=\s*(\d+)', text)
    if m:
        total, good, lost = map(int, m.groups())
        if total > 0 and 0 <= good <= total and total == good + lost:
            return good * 100 / total
    return None


def route_entries(text):
    entries, current = [], None
    fixed_prefixlen = None
    for line in text.splitlines():
        header = re.search(r'(\d+\.\d+\.\d+\.\d+)/(\d+) is (variably )?subnetted', line)
        if header:
            fixed_prefixlen = None if header[3] else int(header[2])
            current = None
            continue
        m = re.match(rf'^\s*([A-Z](?:\s+(?:IA|E1|E2|N1|N2))?)\*?\s+({IP})(?:/(\d+))?\s+(.+)$', line)
        if m:
            bits = int(m[3]) if m[3] else fixed_prefixlen
            if bits is None:
                first = int(m[2].split('.')[0]); bits = 8 if first < 128 else (16 if first < 192 else 24)
            try:
                prefix = str(ip.IPv4Network(f'{m[2]}/{bits}', strict=True))
            except ValueError:
                current = None; continue
            current = {'prefix': prefix, 'protocol': ' '.join(m[1].split()), 'next_hops': []}
            entries.append(current)
            hops = re.findall(rf'\bvia\s+({IP})', m[4])
            current['next_hops'].extend(hops)
        elif current and re.match(r'^\s+\[\d+/\d+\]\s+via\s+', line):
            current['next_hops'].extend(re.findall(rf'\bvia\s+({IP})', line))
        elif line.strip():
            current = None
    return entries


def trace_hops(text):
    hops = []
    for line in text.splitlines():
        if re.match(r'^\s*\d+\s+', line):
            candidates = re.findall(IP, line)
            for value in candidates:
                try:
                    ip.IPv4Address(value)
                    if not hops or hops[-1] != value:
                        hops.append(value)
                except ValueError:
                    pass
    return hops


def verify(data, observations):
    rows = observations.get('observations', [])
    if not isinstance(rows, list):
        raise ValueError('observations 必须为数组')
    seen = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str):
            raise ValueError('每条观测必须有字符串 id')
        if row['id'] in seen:
            raise ValueError('重复观测 ID：' + row['id'])
        seen[row['id']] = row
    devices = {d['name']: d for d in data['devices']}
    results = []
    for check in data['checks']:
        row = seen.get(check['id'])
        record = {'id': check['id'], 'type': check['type'], 'expected': check, 'status': 'not_run'}
        if row and row.get('output', '').strip():
            if row.get('provenance') not in ('packet_tracer_manual', 'packet_tracer_script', 'synthetic_test'):
                record.update(status='invalid_evidence', reason='采集来源缺失/不受支持')
            elif row.get('device') != check['device'] or row.get('command') != check_command(check, devices):
                record.update(status='invalid_evidence', reason='观测设备或命令不匹配')
            elif not row.get('collected_at'):
                record.update(status='invalid_evidence', reason='缺少采集时间')
            else:
                output = row['output']
                record['provenance'] = row['provenance']
                if check['type'] == 'ping':
                    pct = ping_percent(output, check['target'])
                    passed = pct is not None and ((pct >= check.get('min_success_percent', 100)) if check['expected'] else pct == 0)
                    record.update(status=('unparsed' if pct is None else ('pass' if passed else 'fail')), actual={'success_percent': pct})
                elif check['type'] == 'route':
                    entries = route_entries(output)
                    matches = [e for e in entries if e['prefix'] == check['prefix'] and e['protocol'] == check['protocol']]
                    hops = {h for e in matches for h in e['next_hops']}
                    passed = bool(matches) and set(check.get('next_hops', [])) <= hops
                    parsed = bool(entries) or 'Gateway of last resort' in output or 'Codes:' in output
                    record.update(status=('unparsed' if not parsed else ('pass' if passed else 'fail')), actual=matches)
                elif check['type'] == 'trace':
                    hops = trace_hops(output)
                    cursor = 0
                    for hop in hops:
                        if cursor < len(check['via']) and hop == check['via'][cursor]: cursor += 1
                    passed = cursor == len(check['via']) and check['target'] in hops
                    record.update(status=('unparsed' if not hops else ('pass' if passed else 'fail')), actual={'hops': hops})
        results.append(record)
    synthetic = any(r.get('provenance') == 'synthetic_test' for r in rows)
    all_pass = bool(results) and all(r['status'] == 'pass' for r in results)
    return {'topology': data['name'], 'evidence_kind': 'synthetic_test' if synthetic else 'packet_tracer',
            'deployment_verified': all_pass and not synthetic,
            'checks_all_pass': all_pass, 'execution_mode': 'imported_evidence',
            'counts': {s: sum(r['status'] == s for r in results) for s in ('pass', 'fail', 'not_run', 'unparsed', 'invalid_evidence')},
            'results': results}

