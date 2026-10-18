import json
import pytest
from netlab.retry import retry_context
from netlab.storage import ROOT


def test_truncated_retry_uses_saved_response_without_rewriting(tmp_path):
    (tmp_path / 'requirement.txt').write_text('original requirement', encoding='utf-8')
    response = {'choices': [{'finish_reason': 'length', 'message': {'content': 'schema_version: ['}}]}
    raw = json.dumps(response)
    (tmp_path / 'response.json').write_text(raw, encoding='utf-8')
    messages, feedback = retry_context(tmp_path, 'original requirement')
    assert messages[0]['content'] == 'schema_version: ['
    assert feedback['previous_finish_reason'] == 'length'
    assert feedback['current_validation']['valid'] is False
    assert (tmp_path / 'response.json').read_text(encoding='utf-8') == raw
    assert not (tmp_path / 'model-output.yaml').exists()


def test_retry_cannot_switch_requirements(tmp_path):
    (tmp_path / 'requirement.txt').write_text('A', encoding='utf-8')
    with pytest.raises(ValueError, match='不一致'):
        retry_context(tmp_path, 'B')


def test_retry_includes_new_validation_failures(tmp_path):
    (tmp_path / 'requirement.txt').write_text('same', encoding='utf-8')
    (tmp_path / 'validation.json').write_text('{"valid":true}', encoding='utf-8')
    (tmp_path / 'model-output.yaml').write_text('status: ready\nsource: model_generated', encoding='utf-8')
    _, feedback = retry_context(tmp_path, 'same')
    assert feedback['validation.json']['valid'] is True
    assert feedback['current_validation']['valid'] is False


def test_retry_after_provider_error_does_not_treat_it_as_model_output(tmp_path):
    (tmp_path / 'requirement.txt').write_text('same', encoding='utf-8')
    (tmp_path / 'response.json').write_text(json.dumps({'error': {'message': 'queue timeout'}}), encoding='utf-8')
    messages, feedback = retry_context(tmp_path, 'same')
    assert feedback['previous_provider_error'] is True
    assert feedback['empty_output'] is True
    assert len(messages) == 1 and messages[0]['role'] == 'user'
