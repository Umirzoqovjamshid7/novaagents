import pytest
import sys
from pathlib import Path
from fastapi import HTTPException

import app
from telegram_bot import command_arg


def test_command_arg_requires_an_id():
    with pytest.raises(ValueError):
        command_arg('/status   ', '/status')
    assert command_arg('/status abc123', '/status') == 'abc123'


def test_project_path_traversal_is_rejected():
    with pytest.raises(HTTPException) as error:
        app.project_dir('../outside')
    assert error.value.status_code == 400


def test_known_project_resolves_inside_workspace():
    assert app.project_dir('sample').parent == app.WORKSPACE


def test_managed_process_is_cleaned_up(monkeypatch):
    monkeypatch.setattr(app, 'is_cancelled', lambda _task_id: False)
    ok, output = app.run_process(
        'regression-process',
        [sys.executable, '-c', 'print("ok")'],
        Path.cwd(),
        timeout=5,
    )
    assert ok is True
    assert output.strip() == 'ok'
    assert 'regression-process' not in app.ACTIVE_PROCESSES


def test_secret_redaction_masks_common_credentials():
    value=app.redact('api_key=abc123 bearer eyJtoken password: hidden')
    assert 'abc123' not in value
    assert 'eyJtoken' not in value
    assert 'hidden' not in value
    assert value.count('[REDACTED]') == 3


def test_feature_helpers_report_project_health_and_templates():
    health=app.project_health(app.WORKSPACE / 'sample')
    assert health['tests_detected'] is True
    assert 'bugfix' in app.TASK_TEMPLATES


def test_readonly_role_cannot_mutate():
    with pytest.raises(HTTPException) as error:
        app.require_operator('readonly')
    assert error.value.status_code == 403
