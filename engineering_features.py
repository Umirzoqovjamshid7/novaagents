"""Local, side-effect-conscious engineering helpers used by the API."""
import json
import shutil
import subprocess
import time
from pathlib import Path


TASK_TEMPLATES = {
    'bugfix': {'title': 'Bug fix', 'prompt': 'Muammoni top, test yoz, tuzat va barcha testlarni ishga tushir.'},
    'refactor': {'title': 'Refactoring', 'prompt': 'Kod tuzilmasini yaxshila, xatti-harakatni saqla va regression test yoz.'},
    'security': {'title': 'Security audit', 'prompt': 'Xavfsizlik zaifliklarini top, xavf darajasini yoz va xavfsiz tuzatish taklif qil.'},
    'tests': {'title': 'Test yozish', 'prompt': 'Muhim biznes mantiq uchun unit va integration testlar yoz.'},
    'release': {'title': 'Release check', 'prompt': 'Test, dependency, config va release tayyorgarligini tekshir; deploy qilma.'},
}

TRANSLATIONS = {
    'uz': {'new_task': 'Yangi vazifa', 'start': 'Vazifani boshlash', 'cancel': 'Bekor qilish', 'history': 'Vazifalar tarixi'},
    'ru': {'new_task': 'Новая задача', 'start': 'Запустить задачу', 'cancel': 'Отменить', 'history': 'История задач'},
    'en': {'new_task': 'New task', 'start': 'Start task', 'cancel': 'Cancel', 'history': 'Task history'},
}


def _run(command, cwd, timeout=60):
    try:
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return {'ok': result.returncode == 0, 'code': result.returncode,
                'output': (result.stdout + '\n' + result.stderr).strip()[-4000:]}
    except FileNotFoundError:
        return {'ok': None, 'code': None, 'output': f'Not installed: {command[0]}'}
    except subprocess.TimeoutExpired:
        return {'ok': False, 'code': None, 'output': f'Timeout after {timeout}s: {command[0]}'}


def git_info(path):
    if not (path / '.git').exists():
        return {'available': False, 'clean': None, 'branch': None, 'diff': ''}
    branch = _run(['git', 'branch', '--show-current'], path, 10)
    status = _run(['git', 'status', '--porcelain'], path, 10)
    diff = _run(['git', 'diff', '--stat'], path, 10)
    return {'available': True, 'clean': status['ok'] and not status['output'],
            'branch': branch['output'], 'diff': diff['output']}


def project_health(path):
    markers = ['pyproject.toml', 'requirements.txt', 'package.json', 'Dockerfile', '.gitignore']
    present = [name for name in markers if (path / name).exists()]
    tests = (path / 'tests').is_dir() or any(path.glob('**/test_*.py'))
    return {'project': path.name, 'markers': present, 'tests_detected': tests,
            'git': git_info(path), 'checked_at': time.time()}


def quality_gate(path):
    checks = {}
    if (path / 'tests').is_dir():
        checks['pytest'] = _run(['python', '-m', 'pytest', '-q', 'tests'], path, 120)
    else:
        checks['pytest'] = {'ok': None, 'code': None, 'output': 'tests/ not found'}
    if shutil.which('ruff'):
        checks['ruff'] = _run(['ruff', 'check', '.'], path, 60)
    else:
        checks['ruff'] = {'ok': None, 'code': None, 'output': 'ruff not installed (optional)'}
    return {'passed': all(item['ok'] is not False for item in checks.values()), 'checks': checks}


def dependency_audit(path):
    checks = {}
    if (path / 'requirements.txt').exists() and shutil.which('pip-audit'):
        checks['pip-audit'] = _run(['pip-audit', '-r', 'requirements.txt'], path, 120)
    elif (path / 'requirements.txt').exists():
        checks['pip-audit'] = {'ok': None, 'code': None, 'output': 'pip-audit not installed (optional)'}
    if (path / 'package-lock.json').exists() and shutil.which('npm'):
        checks['npm-audit'] = _run(['npm', 'audit', '--omit=dev'], path, 120)
    return {'passed': all(item['ok'] is not False for item in checks.values()), 'checks': checks}
