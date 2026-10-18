"""Compare with a separately authored oracle; never let model-generated checks grade themselves."""
import ipaddress as ip


def compare_intent(actual, reference):
    problems = []
    if actual.get('status') != reference.get('status'):
        return {'matched': False, 'problems': ['处理状态与预期不一致']}
    if reference['status'] != 'ready':
        return {'matched': True, 'problems': [], 'note': '只核对状态；澄清/拒绝理由仍需人工评阅'}
    if actual.get('status') != 'ready':
        return {'matched': False, 'problems': ['预期可部署拓扑']}
    got = {d['name']: d for d in actual.get('devices', [])}
    expected = {d['name']: d for d in reference['devices']}
    if set(got) != set(expected): problems.append('设备集合不一致')
    for name, exp in expected.items():
        if name not in got: continue
        d = got[name]
        for field in ('kind', 'model', 'gateway', 'vlans', 'static_routes', 'acls', 'services'):
            if d.get(field) != exp.get(field):
                problems.append(f'{name}.{field} 与基准不一致')
        interfaces = {i['name']: i for i in d['interfaces']}
        expif = {i['name']: i for i in exp['interfaces']}
        if set(interfaces) != set(expif): problems.append(f'{name} 接口集合不一致')
        for key, ei in expif.items():
            ai = interfaces.get(key, {})
            for field in ('mode', 'ipv4', 'vlan', 'allowed_vlans', 'clock_rate', 'ospf_cost'):
                if ai.get(field) != ei.get(field): problems.append(f'{name}.{key}.{field} 不一致')
            if ai.get('enabled', True) != ei.get('enabled', True): problems.append(f'{name}.{key} 启停状态不一致')
        ar, er = d.get('routing', {}), exp.get('routing', {})
        if set(ar) != set(er): problems.append(f'{name} 路由协议集合不一致')
        for protocol, values in er.items():
            av = ar.get(protocol, {})
            for k in ('version', 'auto_summary', 'process_id'):
                if av.get(k) != values.get(k): problems.append(f'{name}.{protocol}.{k} 不一致')
            def nets(v):
                result = set()
                for n in v.get('networks', []):
                    result.add(n if isinstance(n, str) else (n['prefix'], n['area']))
                return result
            if nets(av) != nets(values): problems.append(f'{name}.{protocol}.networks 不一致')
    def links(data):
        return {(tuple(sorted((l['a']['device'] + ':' + l['a']['interface'], l['b']['device'] + ':' + l['b']['interface']))), l['medium']) for l in data.get('links', [])}
    if links(actual) != links(reference): problems.append('接线不一致')
    # The oracle, not the candidate, defines required probes.
    def check_key(c):
        return (c['type'], c['device'], c.get('target', c.get('prefix')))
    by_key = {}
    for c in actual.get('checks', []): by_key.setdefault(check_key(c), []).append(c)
    for ec in reference['checks']:
        candidates = by_key.get(check_key(ec), [])
        if not candidates:
            problems.append('缺少验收条件：' + ec['id']); continue
        if ec['type'] == 'ping':
            ok = any(c.get('expected') == ec['expected'] and c.get('min_success_percent', 100) == 100 for c in candidates)
        elif ec['type'] == 'route':
            ok = any(c.get('protocol') == ec['protocol'] and set(ec.get('next_hops', [])) <= set(c.get('next_hops', [])) for c in candidates)
        else:
            ok = any(c.get('via') == ec['via'] for c in candidates)
        if not ok: problems.append('验收条件被改变：' + ec['id'])
    return {'matched': not problems, 'problems': problems,
            'note': '严格命名和编址基线对比；不同但等价的设计需另行人工判定，不能自动记正确'}

