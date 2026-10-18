"""Build explicit retry feedback without rewriting a previous audit record."""
import json
from .storage import parse_model_yaml, read_yaml
from .validate import validate


def retry_context(previous, requirement, reference=None):
    if (previous / 'requirement.txt').read_text(encoding='utf-8-sig').strip() != requirement.strip():
        raise ValueError('重试需求与原运行不一致；应建立新用例，不能混入同一重试链')
    feedback = {}
    for filename in ('validation.json', 'intent.json'):
        if (previous / filename).exists():
            feedback[filename] = json.loads((previous / filename).read_text(encoding='utf-8'))
    content = None
    if (previous / 'response.json').exists():
        response = json.loads((previous / 'response.json').read_text(encoding='utf-8'))
        choices = response.get('choices') if isinstance(response, dict) else None
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            choice = choices[0]
            content = choice.get('message', {}).get('content')
            feedback['previous_finish_reason'] = choice.get('finish_reason')
        elif isinstance(response, dict) and response.get('error'):
            feedback['previous_provider_error'] = True
    if (previous / 'model-output.yaml').exists():
        content = (previous / 'model-output.yaml').read_text(encoding='utf-8')
    if not isinstance(content, str):
        content = ''
    if content.strip():
        try:
            candidate, adapter = parse_model_yaml(content)
            feedback['current_validation'] = validate(candidate)
            feedback['current_format_adapter'] = adapter
        except Exception as exc:
            feedback['current_validation'] = {'valid': False, 'parse_error': str(exc)}
    else:
        feedback['empty_output'] = True
    if reference:
        feedback['required_checks'] = read_yaml(reference).get('checks', [])
    messages = ([{'role': 'assistant', 'content': content}] if content.strip() else [])
    messages.append({'role': 'user', 'content': '上一版未通过当前检查或被截断。保留原需求，修正反馈中的问题并重新输出完整 YAML；不要只续写片段。反馈：' + json.dumps(feedback, ensure_ascii=False)})
    return messages, feedback
