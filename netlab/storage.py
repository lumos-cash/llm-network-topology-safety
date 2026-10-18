import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class UniqueLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node, deep=False):
    result = {}
    for k, v in node.value:
        key = loader.construct_object(k, deep=deep)
        if not isinstance(key, str):
            raise ValueError('YAML mapping keys must be strings')
        if key in result:
            raise ValueError(f'Duplicate YAML key: {key}')
        result[key] = loader.construct_object(v, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def parse_yaml(text):
    if len(text.encode('utf-8')) > 1_000_000:
        raise ValueError('YAML exceeds 1 MB')
    # No alias expansion, custom tags or silent duplicate-key overrides.
    for token in yaml.scan(text):
        if isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken, yaml.tokens.TagToken)):
            raise ValueError('YAML aliases, anchors and custom tags are not supported')
    return yaml.load(text, Loader=UniqueLoader)


def read_yaml(path):
    return parse_yaml(Path(path).read_text(encoding='utf-8-sig'))


def parse_model_yaml(text):
    """Explicit format adapter. Preserve original text in audit before calling."""
    stripped = text.strip()
    match = re.fullmatch(r'```(?:yaml|yml)?\s*\n([\s\S]*?)\n```', stripped)
    if match:
        return parse_yaml(match[1]), 'single_markdown_fence_removed'
    return parse_yaml(stripped), 'none'


def write_json(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_yaml(path, data):
    Path(path).write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding='utf-8')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Audit:
    def __init__(self, purpose, root=None, secrets=()):
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        self.path = Path(root or ROOT / 'runs') / f'{stamp}-{purpose}-{uuid.uuid4().hex[:8]}'
        self.path.mkdir(parents=True, exist_ok=False)
        self.secrets = [s for s in secrets if s]
        self.event('started', {'purpose': purpose, 'tool_version': '0.1.0'})

    def clean(self, value):
        if isinstance(value, dict):
            return {k: ('[REDACTED]' if re.search(r'api[_-]?key|authorization|password|secret', k, re.I)
                        else self.clean(v)) for k, v in value.items()}
        if isinstance(value, list):
            return [self.clean(v) for v in value]
        if isinstance(value, str):
            for secret in self.secrets:
                value = value.replace(secret, '[REDACTED]')
            value = re.sub(r'(?i)Bearer\s+\S+', 'Bearer [REDACTED]', value)
            value = re.sub(r'(?im)^(\s*(?:enable (?:secret|password)|username \S+ (?:privilege \d+ )?(?:secret|password)|password|snmp-server community|crypto isakmp key)\s+).+$',
                           r'\1[REDACTED]', value)
        return value

    def event(self, kind, data):
        record = {'time_utc': datetime.now(timezone.utc).isoformat(), 'event': kind,
                  'data': self.clean(data)}
        with (self.path / 'audit.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

    def json(self, name, data):
        write_json(self.path / name, self.clean(data))

    def text(self, name, text):
        (self.path / name).write_text(self.clean(text), encoding='utf-8')

