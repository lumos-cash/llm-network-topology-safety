import json
import os
from urllib.parse import urlparse

import requests

from .storage import ROOT


def settings():
    config = {}
    path = ROOT / '.env.local'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            key, sep, value = line.partition('=')
            if sep and key.strip().startswith('DEEPSEEK_'):
                config[key.strip()] = value.strip().strip('\"').strip("'")
    config.update({k: v for k, v in os.environ.items() if k.startswith('DEEPSEEK_')})
    config.setdefault('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
    config.setdefault('DEEPSEEK_MODEL', 'deepseek-flash')
    config.setdefault('DEEPSEEK_TIMEOUT', '120')
    return config


def chat(messages, audit, config=None):
    c = config or settings()
    key = c.get('DEEPSEEK_API_KEY', '')
    if not key or key.startswith('your-'):
        raise ValueError('缺少 DEEPSEEK_API_KEY。请在本机 .env.local 填写，勿发到聊天。')
    base = c['DEEPSEEK_BASE_URL'].rstrip('/')
    url = urlparse(base)
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('DEEPSEEK_BASE_URL 必须为不含凭据/查询参数的 HTTPS 地址')
    # This is the only outbound request in the project; never a PT device connection.
    max_tokens = int(c.get('DEEPSEEK_MAX_TOKENS', '8192'))
    if not 1 <= max_tokens <= 32768:
        raise ValueError('DEEPSEEK_MAX_TOKENS 必须在 1 到 32768 之间')
    body = {'model': c['DEEPSEEK_MODEL'], 'messages': messages, 'stream': False,
            'max_tokens': max_tokens}
    audit.secrets.append(key)
    audit.json('request.json', {'url': base + '/chat/completions', 'body': body})
    response = requests.post(base + '/chat/completions', json=body,
                             headers={'Authorization': f'Bearer {key}'},
                             timeout=(10, int(c['DEEPSEEK_TIMEOUT'])), allow_redirects=False)
    audit.text('response.raw.txt', response.text)
    audit.event('http_response', {'status': response.status_code})
    if response.status_code != 200:
        raise ValueError(f'DeepSeek HTTP {response.status_code}；响应已保存到审计目录。未自动重试。')
    result = response.json()
    audit.json('response.json', result)
    if not isinstance(result, dict):
        raise ValueError('DeepSeek 返回了非对象 JSON；响应已保存，未自动重试。')
    error = result.get('error')
    if error is not None:
        detail = error.get('message') if isinstance(error, dict) else None
        audit.event('provider_error', {'message': detail if isinstance(detail, str) else 'unknown'})
        raise ValueError('DeepSeek 服务返回错误；响应已保存，未自动重试。' +
                         (f' {detail}' if isinstance(detail, str) else ''))
    choices = result.get('choices')
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValueError('DeepSeek 响应缺少有效 choices；响应已保存，未自动重试。')
    choice = choices[0]
    content = choice['message'].get('content')
    if isinstance(content, str):
        audit.text('response-content.txt', content)
    if choice.get('finish_reason') != 'stop':
        raise ValueError(f"模型响应未正常结束：{choice.get('finish_reason')}，不能当作成功生成")
    if not isinstance(content, str) or not content.strip():
        raise ValueError('模型返回空内容')
    audit.event('model_response', {'model': result.get('model'), 'usage': result.get('usage'),
                                   'finish_reason': choice.get('finish_reason')})
    return content


def generation_messages(requirement, schema):
    prompt = (ROOT / 'prompts' / 'generate.txt').read_text(encoding='utf-8')
    example = (ROOT / 'examples' / 'uc06_lan.yaml').read_text(encoding='utf-8').replace('source: manual_reference', 'source: model_generated')
    return [{'role': 'system', 'content': prompt + '\nJSON Schema:\n' + json.dumps(schema, ensure_ascii=False, separators=(',', ':'))},
            {'role': 'user', 'content': '格式示例：两台 PC 经交换机 VLAN10 同网段互通。'},
            {'role': 'assistant', 'content': example},
            {'role': 'user', 'content': requirement}]

