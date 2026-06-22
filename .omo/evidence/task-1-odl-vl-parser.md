# Task 1 Evidence: Bootstrap Python Package and Environment Contract

## Scope

Created only the requested task files:

- `pyproject.toml`
- `.env.example`
- `src/odl_vl/__init__.py`
- `src/odl_vl/config.py`
- `tests/test_config.py`
- `.omo/evidence/task-1-odl-vl-parser.md`

The config loader uses Python stdlib runtime only. It reads shell environment values plus an optional `.env` file, prefers canonical names, and supports `PADDLEOCR_API_KEY` and `PADDLEOCR_BASE_URL` only as fallback aliases. No real `.env` file was read.

## Commands And Outcomes

1. Red check before implementation:

```bash
python3 -m pytest tests/test_config.py
```

Outcome: failed before collection because the local global pytest environment auto-loaded `pytest_html`, which failed to import `jinja2.Environment`. This occurred before project code or tests were imported.

2. Isolated Red check before implementation:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_config.py
```

Outcome: failed for the expected TDD reason: `ModuleNotFoundError: No module named 'odl_vl'`.

3. Acceptance unit test after implementation:

```bash
python3 -m pytest tests/test_config.py
```

Outcome: passed. Pytest collected 5 tests and reported `5 passed in 0.02s`.

4. Compile check:

```bash
python3 -m compileall src tests
```

Outcome: passed. Python listed and compiled `src`, `src/odl_vl`, and tests without errors.

5. CLI import surface check with a temporary `.env` containing placeholder values only:

```bash
PYTHONPATH=src python3 - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from odl_vl.config import load_settings

with TemporaryDirectory() as directory:
    env_file = Path(directory) / '.env'
    gemini_value = 'cli-gemini-placeholder'
    paddle_value = 'cli-paddle-placeholder'
    base_url = 'https://cli-placeholder.invalid'
    env_file.write_text(
        '\n'.join([
            f'GEMINI_API_KEY={gemini_value}',
            f'PADDLE_API_KEY={paddle_value}',
            f'PADDLE_BASE_URL={base_url}',
        ]),
        encoding='utf-8',
    )
    settings = load_settings(env_file=env_file, environ={})
    output = f'gemini={settings.has_gemini}\npaddle={settings.has_paddle}'
    for secret in (gemini_value, paddle_value, base_url):
        assert secret not in output
    print(output)
PY
```

Outcome: passed and printed only provider presence booleans:

```text
gemini=True
paddle=True
```

6. Changed file pure LOC check:

```bash
python3 - <<'PY'
from pathlib import Path

paths = [
    Path('pyproject.toml'),
    Path('.env.example'),
    Path('src/odl_vl/__init__.py'),
    Path('src/odl_vl/config.py'),
    Path('tests/test_config.py'),
]
for path in paths:
    count = 0
    for line in path.read_text(encoding='utf-8').splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(('#', '//', '--')):
            count += 1
    print(f'{path}: {count}')
PY
```

Outcome: passed with all files below the 200 LOC healthy threshold:

```text
pyproject.toml: 17
.env.example: 4
src/odl_vl/__init__.py: 2
src/odl_vl/config.py: 78
tests/test_config.py: 80
```
