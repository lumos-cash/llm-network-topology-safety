"""Rebuild the versioned public JSON Schema (no network, no device access)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def obj(properties, required=()):
    return {'type': 'object', 'properties': properties, 'required': list(required), 'additionalProperties': False}


def arr(items, minimum=0):
    return {'type': 'array', 'items': items, 'minItems': minimum}


def enum(*values):
    result = {'enum': list(values)}
    if all(isinstance(v, str) for v in values):
        result['type'] = 'string'
    elif all(type(v) is int for v in values):
        result['type'] = 'integer'
    return result


def string(pattern=None):
    s = {'type': 'string', 'minLength': 1, 'maxLength': 500}
    if pattern:
        s['pattern'] = pattern
    return s


def integer(lo, hi):
    return {'type': 'integer', 'minimum': lo, 'maximum': hi}


def build():
    name = string(r'^[A-Za-z][A-Za-z0-9_-]{0,31}$')
    iface = string(r'^(?:GigabitEthernet\d+/\d+|FastEthernet\d+(?:/\d+)?|Serial\d+/\d+/\d+|Vlan\d+|Loopback\d+)(?:\.\d+)?$')
    ipv4 = {'type': 'string', 'format': 'ipv4'}
    cidr = string(r'^\d{1,3}(?:\.\d{1,3}){3}/(?:[0-9]|[12][0-9]|3[0-2])$')
    vlan = integer(1, 4094)
    endpoint = obj({'device': name, 'interface': iface}, ['device', 'interface'])
    interface = obj({'name': iface, 'mode': enum('routed', 'access', 'trunk', 'svi', 'subinterface'),
                     'ipv4': cidr, 'vlan': vlan, 'allowed_vlans': arr(vlan, 1),
                     'enabled': {'type': 'boolean'}, 'clock_rate': integer(1200, 8000000),
                     'ospf_cost': integer(1, 65535)}, ['name', 'mode'])
    interface['allOf'] = [
        {'if': {'properties': {'mode': enum('access', 'svi', 'subinterface')}}, 'then': {'required': ['vlan']}},
        {'if': {'properties': {'mode': enum('trunk')}}, 'then': {'required': ['allowed_vlans']}},
        {'if': {'properties': {'mode': enum('access', 'trunk')}}, 'then': {'not': {'required': ['ipv4']}}}]
    rip = obj({'version': enum(1, 2), 'auto_summary': {'type': 'boolean'}, 'networks': arr(cidr, 1)},
              ['version', 'auto_summary', 'networks'])
    ospf = obj({'process_id': integer(1, 65535), 'router_id': ipv4,
               'networks': arr(obj({'prefix': cidr, 'area': integer(0, 4294967295)}, ['prefix', 'area']), 1)},
               ['process_id', 'networks'])
    aclrule = obj({'action': enum('permit', 'deny'), 'protocol': enum('ip', 'icmp', 'tcp', 'udp'),
                   'source': {'anyOf': [cidr, {'const': 'any'}]},
                   'destination': {'anyOf': [cidr, {'const': 'any'}]},
                   'destination_port': integer(1, 65535)}, ['action', 'protocol', 'source', 'destination'])
    acl = obj({'number': integer(100, 199), 'rules': arr(aclrule, 1),
               'interface': iface, 'direction': enum('in', 'out')}, ['number', 'rules', 'interface', 'direction'])
    route = obj({'prefix': cidr, 'next_hop': ipv4, 'distance': integer(1, 254)}, ['prefix', 'next_hop'])
    device = obj({'name': name, 'kind': enum('router', 'switch', 'l3_switch', 'pc', 'server'),
                  'model': enum('2911', '1941', '2960-24TT', '3560-24PS', 'PC-PT', 'Server-PT'),
                  'interfaces': arr(interface, 1), 'gateway': ipv4,
                  'vlans': arr(obj({'id': vlan, 'name': name}, ['id', 'name'])),
                  'routing': obj({'rip': rip, 'ospf': ospf}), 'static_routes': arr(route),
                  'acls': arr(acl), 'services': arr(enum('http'))}, ['name', 'kind', 'model', 'interfaces'])
    ping = obj({'id': name, 'type': {'const': 'ping'}, 'device': name, 'target': ipv4,
                'expected': {'type': 'boolean'}, 'min_success_percent': {'const': 100}},
               ['id', 'type', 'device', 'target', 'expected'])
    trace = obj({'id': name, 'type': {'const': 'trace'}, 'device': name, 'target': ipv4,
                 'via': arr(ipv4, 1)}, ['id', 'type', 'device', 'target', 'via'])
    routecheck = obj({'id': name, 'type': {'const': 'route'}, 'device': name, 'prefix': cidr,
                      'protocol': enum('C', 'L', 'S', 'R', 'O', 'O IA', 'B'), 'next_hops': arr(ipv4)},
                     ['id', 'type', 'device', 'prefix', 'protocol'])
    data = obj({'schema_version': {'const': '1.0'}, 'status': enum('ready', 'needs_clarification', 'rejected'),
                'name': name, 'source': enum('manual_reference', 'model_generated'),
                'intent': string(), 'questions': arr(string(), 1), 'reason': string(),
                'assumptions': arr(string()), 'devices': arr(device, 1),
                'links': arr(obj({'a': endpoint, 'b': endpoint, 'medium': enum('copper', 'serial')},
                                 ['a', 'b', 'medium'])),
                'checks': arr({'oneOf': [ping, trace, routecheck]}, 1)},
               ['schema_version', 'status', 'name', 'source', 'intent'])
    data['$schema'] = 'https://json-schema.org/draft/2020-12/schema'
    data['title'] = 'Packet Tracer topology DSL 1.0'
    data['allOf'] = [
        {'if': {'properties': {'status': {'const': 'ready'}}}, 'then': {'required': ['devices', 'links', 'checks']}},
        {'if': {'properties': {'status': {'const': 'needs_clarification'}}}, 'then': {'required': ['questions']}},
        {'if': {'properties': {'status': {'const': 'rejected'}}}, 'then': {'required': ['reason']}}]
    return data


if __name__ == '__main__':
    p = ROOT / 'schemas' / 'topology.schema.json'
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(p)

