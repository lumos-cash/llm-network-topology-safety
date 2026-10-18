import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from netlab.guard import check_commands
from netlab.render import check_command, export, render_device
from netlab.storage import ROOT, Audit, parse_yaml, read_yaml
from netlab.validate import schema, validate
from netlab.verify import ping_percent, route_entries, verify
from netlab.intent import compare_intent
from netlab.storage import parse_model_yaml


@pytest.fixture
def ospf():
    return read_yaml(ROOT / 'examples/lab4_11_ospf.yaml')


def test_schema_itself():
    Draft202012Validator.check_schema(schema())


@pytest.mark.parametrize('path', sorted((ROOT / 'examples').glob('*.yaml')), ids=lambda p: p.stem)
def test_manual_examples_valid(path):
    assert validate(read_yaml(path))['valid']


@pytest.mark.parametrize('text', ['a: 1\na: 2', 'a: &x [1]\nb: *x', 'a: !!python/object/apply:os.system [echo test]'])
def test_unsafe_yaml_rejected(text):
    with pytest.raises((ValueError, Exception)):
        parse_yaml(text)


@pytest.mark.parametrize('mutation,code', [
    (lambda d: d['devices'][4]['interfaces'][0].update(ipv4='192.168.16.1/25'), 'duplicate_ip'),
    (lambda d: d['devices'][4].update(gateway='192.168.17.1'), 'gateway'),
    (lambda d: d['devices'][4].update(gateway='192.168.16.180'), 'gateway_reference'),
    (lambda d: d['devices'][0]['interfaces'][0].update(ipv4='192.168.16.0/25'), 'host_address'),
    (lambda d: d['devices'][0]['interfaces'][1].update(ipv4='10.0.0.1/29'), 'link_subnet'),
    (lambda d: d['links'][0]['a'].update(device='Ghost'), 'link_reference'),
    (lambda d: d['devices'][0]['interfaces'][2].pop('clock_rate'), 'serial_clock'),
    (lambda d: d['devices'][2]['routing']['ospf']['networks'][0].update(area=1), 'ospf_area'),
    (lambda d: d['devices'][0]['routing']['ospf']['networks'][0].update(prefix='172.16.0.0/24'), 'routing_network'),
    (lambda d: d['checks'][0].update(target='8.8.8.8'), 'check_target'),
    (lambda d: d['devices'][0].update(name='Router0;reload'), 'schema'),
    (lambda d: d['devices'][0].update(commands=['reload']), 'schema'),
])
def test_invalid_topology_is_blocked(ospf, mutation, code):
    mutation(ospf)
    result = validate(ospf)
    assert not result['deployable']
    assert code in {e['code'] for e in result['errors']}, result


def test_undefined_vlan():
    d = read_yaml(ROOT / 'examples/uc06_lan.yaml')
    d['devices'][0]['interfaces'][0]['vlan'] = 20
    assert 'vlan_reference' in {e['code'] for e in validate(d)['errors']}


def test_unrelated_duplicate_subnets(ospf):
    ospf['links'] = [l for l in ospf['links'] if l['a']['device'] != 'PC0']
    assert 'subnet_overlap' in {e['code'] for e in validate(ospf)['errors']}


@pytest.mark.parametrize('line', ['reload', 'write erase', 'format flash:', 'copy tftp: running-config',
                                  'ip address 10.0.0.1 255.255.255.0; reload', 'router bgp 100',
                                  'ip address 999.1.1.1 255.255.255.0', 'network 10.0.0.0 255.0.255.0 area 0'])
def test_guard_blocks_unknown_or_unsafe(line):
    assert not check_commands('enable\nconfigure terminal\n' + line + '\nend\n')['allowed']


@pytest.mark.parametrize('filename', ['lab4_10_ripv1.yaml', 'lab4_10_ripv2.yaml', 'lab4_11_ospf.yaml', 'uc06_lan.yaml', 'lab4_5_vlsm.yaml', 'lab7_1_acl.yaml', 'lab6_6_http.yaml', 'uc05_svi.yaml', 'uc05_router_on_stick.yaml'])
def test_rendered_configs_pass_guard(filename):
    data = read_yaml(ROOT / 'examples' / filename)
    for d in data['devices']:
        rendered = render_device(d)
        if rendered:
            assert check_commands(rendered, d)['allowed']
            if filename == 'lab4_11_ospf.yaml' and d['name'] == 'Router0':
                assert 'network 192.168.16.0 0.0.0.127 area 0' in rendered
                assert 'network 10.0.0.0 0.0.0.3 area 0' in rendered
            if filename == 'lab4_10_ripv2.yaml':
                assert 'version 2\nno auto-summary' in rendered
                assert 'network 192.168.16.128' not in rendered


def test_export_pending_and_no_overwrite(ospf, tmp_path):
    audit = Audit('test', root=tmp_path / 'audit')
    out = tmp_path / 'package'
    export(ospf, out, audit)
    manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['deployment_status'] == 'not_run'
    assert not (out / 'released').exists()
    with pytest.raises(FileExistsError):
        export(ospf, out, audit)


@pytest.mark.parametrize('text,expected', [
    ('Pinging 192.168.16.129 with 32 bytes of data:\nPackets: Sent = 4, Received = 3, Lost = 1 (25% loss)', 75),
    ('Sending 5, 100-byte ICMP Echos to 192.168.16.129\nSuccess rate is 100 percent (5/5)', 100),
    ('Pinging 192.168.16.129\nPackets: Sent = 4, Received = 0, Lost = 4 (100% loss)', 0),
    ('ping 192.168.16.129\nRequest timed out.', None),
    ('Pinging 8.8.8.8\nPackets: Sent = 4, Received = 4, Lost = 0', None),
])
def test_ping_parsing(text, expected):
    assert ping_percent(text, '192.168.16.129') == expected


def test_route_ecmp_continuation():
    text = 'O    30.0.0.0/30 [110/65] via 10.0.0.1, 00:00:11, GigabitEthernet0/0\n                 [110/65] via 20.0.0.1, 00:00:11, GigabitEthernet0/1'
    assert route_entries(text) == [{'prefix': '30.0.0.0/30', 'protocol': 'O', 'next_hops': ['10.0.0.1', '20.0.0.1']}]


def test_missing_evidence_is_not_pass(ospf):
    result = verify(ospf, {'observations': []})
    assert not result['deployment_verified']
    assert result['counts']['not_run'] == len(ospf['checks'])


def test_expected_failure_and_synthetic_not_real():
    d = read_yaml(ROOT / 'examples/lab4_10_ripv1.yaml')
    devices = {x['name']: x for x in d['devices']}
    obs = [{'id': c['id'], 'device': c['device'], 'command': check_command(c, devices),
            'output': f"Pinging {c['target']}\nPackets: Sent = 4, Received = 0, Lost = 4 (100% loss)",
            'provenance': 'synthetic_test', 'collected_at': '2026-10-14T00:00:00Z'} for c in d['checks']]
    result = verify(d, {'observations': obs})
    assert result['checks_all_pass']
    assert not result['deployment_verified']
    assert result['evidence_kind'] == 'synthetic_test'


def test_audit_redacts(tmp_path):
    audit = Audit('test', root=tmp_path, secrets=['test-secret-value'])
    audit.json('redacted.json', {'api_key': 'foo', 'text': 'test-secret-value Bearer abc'})
    text = (audit.path / 'redacted.json').read_text()
    assert 'test-secret-value' not in text and 'foo' not in text and 'Bearer abc' not in text


def test_format_adapter_explicit():
    data, adapter = parse_model_yaml('```yaml\na: 1\n```')
    assert data == {'a': 1} and adapter == 'single_markdown_fence_removed'
    with pytest.raises(Exception):
        parse_model_yaml('Here is YAML\n```yaml\na: 1\n```')


def test_oracle_catches_omitted_protocol(ospf):
    candidate = copy.deepcopy(ospf)
    candidate['devices'][0].pop('routing')
    assert not compare_intent(candidate, ospf)['matched']


def test_oracle_catches_weakened_ping(ospf):
    candidate = copy.deepcopy(ospf)
    candidate['checks'][0]['expected'] = False
    assert not compare_intent(candidate, ospf)['matched']


def test_threshold_cannot_be_lowered(ospf):
    ospf['checks'][0]['min_success_percent'] = 60
    assert not validate(ospf)['valid']


def test_numeric_router_model_is_not_silently_coerced(ospf):
    ospf['devices'][0]['model'] = 2911
    result = validate(ospf)
    assert not result['deployable']
    assert any(e['path'] == 'devices/0/model' and 'string' in e['message']
               for e in result['errors'])
    assert type(ospf['devices'][0]['model']) is int


def test_trace_cannot_count_two_interfaces_of_one_router_as_two_hops(ospf):
    trace = next(c for c in ospf['checks'] if c['type'] == 'trace')
    trace['via'] = ['192.168.16.126', '30.0.0.2', '192.168.16.190']
    result = validate(ospf)
    assert not result['deployable']
    assert 'trace_repeated_device' in {e['code'] for e in result['errors']}


def test_unknown_trace_hop_is_blocked(ospf):
    trace = next(c for c in ospf['checks'] if c['type'] == 'trace')
    trace['via'] = ['192.168.16.126', '198.51.100.9']
    assert 'trace_hop' in {e['code'] for e in validate(ospf)['errors']}


def test_oracle_binds_model_ids_without_losing_provenance(ospf):
    from netlab.verify import bind_to_oracle
    check = ospf['checks'][0]
    row = {'id': 'different_model_id', 'device': check['device'], 'command': 'ping ' + check['target'],
           'output': 'Pinging ' + check['target'] + '\nPackets: Sent = 4, Received = 4, Lost = 0',
           'collected_at': '2026-10-14T00:00:00Z', 'provenance': 'synthetic_test'}
    bound = bind_to_oracle(ospf, {'observations': [row]})
    assert bound['observations'][0]['source_observation_ids'] == ['different_model_id']
    assert row['id'] == 'different_model_id'
    result = verify(ospf, bound)
    assert result['counts']['pass'] == 1
    assert not result['deployment_verified']


def test_oracle_does_not_select_successful_snapshot(ospf):
    from netlab.verify import bind_to_oracle
    check = ospf['checks'][0]
    base = {'device': check['device'], 'command': 'ping ' + check['target'], 'provenance': 'synthetic_test'}
    with pytest.raises(ValueError, match='不能自动择优'):
        bind_to_oracle(ospf, {'observations': [dict(base, id='first', output='failed'), dict(base, id='second', output='success')]})

