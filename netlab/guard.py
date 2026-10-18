"""Closed, context-aware CLI grammar for this project's generated subset."""
import ipaddress as ip
import re


IFACE = r'(?:GigabitEthernet\d+/\d+|FastEthernet\d+(?:/\d+)?|Serial\d+/\d+/\d+|Vlan\d+|Loopback\d+)(?:\.\d+)?'
IP = r'\d{1,3}(?:\.\d{1,3}){3}'
ADDR = rf'(?:any|host {IP}|{IP} {IP})'
DENY = re.compile(r'(?:^|\s)(?:reload|erase|format|delete|boot|copy|tclsh|shell|bash|python)(?:\s|$)|write\s+erase', re.I)
ACL = re.compile(rf'access-list (\d+) (permit|deny) (ip|icmp|tcp|udp) ({ADDR}) ({ADDR})(?: eq (\d+))?')


def check_commands(text, device=None):
    errors = []
    context = 'exec'
    current_iface = None
    declared_vlans = {1}  # Default VLAN exists on supported switches.
    declared_acls = set()
    bindings = []
    entered_config = False

    def error(n, code, message):
        errors.append({'line': n, 'code': code, 'message': message})

    for n, raw in enumerate(text.splitlines(), 1):
        if any(ord(c) < 32 and c not in '\t' for c in raw) or not raw.isascii():
            error(n, 'characters', '命令含控制字符或非 ASCII 字符'); continue
        line = raw.strip()
        if not line or line.startswith('!'):
            continue
        if DENY.search(line):
            error(n, 'blacklist', '危险命令被硬拦截'); continue
        if any(c in line for c in ';|&`<>'):
            error(n, 'separator', '不允许命令拼接或重定向'); continue
        valid = False
        try:
            if line == 'enable' and context == 'exec':
                valid = True
            elif line == 'configure terminal' and context == 'exec':
                valid = True; context = 'global'; entered_config = True
            elif line == 'end' and context != 'exec':
                valid = True; context = 'exec'
            elif line == 'exit' and context not in ('exec', 'global'):
                valid = True; context = 'global'; current_iface = None
            elif context == 'global':
                if re.fullmatch(r'hostname [A-Za-z][A-Za-z0-9_-]{0,31}', line):
                    valid = device is None or line == 'hostname ' + device['name']
                elif line == 'ip routing':
                    valid = device is None or device['kind'] == 'l3_switch'
                elif m := re.fullmatch(r'vlan (\d+)', line):
                    v = int(m[1]); valid = 1 <= v <= 4094
                    if valid: declared_vlans.add(v); context = 'vlan'
                elif m := re.fullmatch(rf'interface ({IFACE})', line):
                    current_iface = m[1]
                    valid = device is None or current_iface in [i['name'] for i in device['interfaces']]
                    if valid: context = 'interface'
                elif line == 'router rip':
                    valid = True; context = 'rip'
                elif m := re.fullmatch(r'router ospf (\d+)', line):
                    valid = 1 <= int(m[1]) <= 65535
                    if valid: context = 'ospf'
                elif m := re.fullmatch(rf'ip route ({IP}) ({IP}) ({IP})(?: (\d+))?', line):
                    ip.IPv4Network(m[1] + '/' + m[2], strict=True); ip.IPv4Address(m[3])
                    valid = not m[4] or 1 <= int(m[4]) <= 254
                elif m := ACL.fullmatch(line):
                    valid = 100 <= int(m[1]) <= 199
                    for address in (m[4], m[5]):
                        if address == 'any': continue
                        tokens = address.split()
                        if tokens[0] == 'host': ip.IPv4Address(tokens[1])
                        else:
                            wildcard = int(ip.IPv4Address(tokens[1]))
                            mask = str(ip.IPv4Address(0xffffffff ^ wildcard))
                            ip.IPv4Network(tokens[0] + '/' + mask, strict=True)
                    if m[6]: valid = valid and m[3] in ('tcp', 'udp') and 1 <= int(m[6]) <= 65535
                    if valid: declared_acls.add(int(m[1]))
            elif context == 'vlan':
                valid = bool(re.fullmatch(r'name [A-Za-z][A-Za-z0-9_-]{0,31}', line))
            elif context == 'interface':
                if m := re.fullmatch(rf'ip address ({IP}) ({IP})', line):
                    address = ip.IPv4Interface(m[1] + '/' + m[2])
                    valid = address.network.prefixlen >= 31 or address.ip not in (address.network.network_address, address.network.broadcast_address)
                elif line in ('no shutdown', 'shutdown', 'no switchport', 'switchport mode access', 'switchport mode trunk', 'switchport trunk encapsulation dot1q'):
                    valid = True
                elif m := re.fullmatch(r'switchport access vlan (\d+)', line):
                    valid = int(m[1]) in declared_vlans
                elif m := re.fullmatch(r'switchport trunk allowed vlan ([0-9,]+)', line):
                    vs = [int(v) for v in m[1].split(',')]; valid = bool(vs) and set(vs) <= declared_vlans
                elif m := re.fullmatch(r'encapsulation dot1Q (\d+)', line):
                    valid = '.' in (current_iface or '') and 1 <= int(m[1]) <= 4094
                elif m := re.fullmatch(r'clock rate (\d+)', line):
                    valid = current_iface.startswith('Serial') and 1200 <= int(m[1]) <= 8000000
                elif m := re.fullmatch(r'ip ospf cost (\d+)', line):
                    valid = 1 <= int(m[1]) <= 65535
                elif m := re.fullmatch(r'ip access-group (\d+) (in|out)', line):
                    valid = 100 <= int(m[1]) <= 199; bindings.append((n, int(m[1])))
            elif context == 'rip':
                if line in ('version 1', 'version 2', 'auto-summary', 'no auto-summary'): valid = True
                elif m := re.fullmatch(rf'network ({IP})', line):
                    address = ip.IPv4Address(m[1]); first = int(m[1].split('.')[0])
                    bits = 8 if first < 128 else (16 if first < 192 else 24)
                    valid = first < 224 and str(ip.IPv4Network(f'{address}/{bits}', strict=False).network_address) == m[1]
            elif context == 'ospf':
                if m := re.fullmatch(rf'router-id ({IP})', line):
                    ip.IPv4Address(m[1]); valid = True
                elif m := re.fullmatch(rf'network ({IP}) ({IP}) area (\d+)', line):
                    wildcard = int(ip.IPv4Address(m[2]))
                    mask = str(ip.IPv4Address(0xffffffff ^ wildcard))
                    ip.IPv4Network(m[1] + '/' + mask, strict=True)
                    valid = 0 <= int(m[3]) <= 4294967295
        except (ValueError, AttributeError):
            error(n, 'parameter', 'IP、掩码、范围或上下文参数非法'); continue
        if not valid:
            error(n, 'whitelist', f'命令不在当前上下文白名单内：{line}')
    for n, acl in bindings:
        if acl not in declared_acls:
            error(n, 'acl_reference', f'ACL {acl} 未定义')
    if context != 'exec':
        error(len(text.splitlines()), 'context', '配置没有通过 end 返回执行模式')
    if not entered_config:
        error(0, 'empty_configuration', '缺少配置模式入口，不能将空文本作为配置通过')
    return {'allowed': not errors, 'errors': errors}

