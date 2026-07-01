# Task 3 Evidence: IR Routing and Redacted Ledger

## Scope

Implemented Todo 3 from `.omo/plans/odl-vl-parser.md`: internal IR dataclasses, routing policy, and ledger redaction helpers.

Created only these task files:

- `src/odl_vl/ir.py`
- `src/odl_vl/router.py`
- `src/odl_vl/ledger.py`
- `tests/test_router.py`
- `tests/test_ledger.py`
- `.omo/evidence/task-3-odl-vl-parser.md`

Did not touch `src/odl_vl/providers.py`, smoke CLI, README, fixtures, docs, `.env`, or `pyproject.toml`.

## TDD Red

Command:

```bash
python3 -m pytest tests/test_router.py tests/test_ledger.py
```

Outcome before implementation: failed during collection for the expected reason. `odl_vl.router` and `odl_vl.ledger` did not exist yet.

Key output:

```text
ModuleNotFoundError: No module named 'odl_vl.router'
ModuleNotFoundError: No module named 'odl_vl.ledger'
```

## Targeted Tests

Command:

```bash
python3 -m pytest tests/test_router.py tests/test_ledger.py
```

Outcome after implementation:

```text
collected 7 items
tests/test_router.py .....
tests/test_ledger.py ..
7 passed in 0.02s
```

## Full Offline Test Suite

Command:

```bash
python3 -m pytest
```

Outcome:

```text
collected 22 items
tests/test_config.py .....
tests/test_fixture_manifest.py .....
tests/test_ledger.py ..
tests/test_providers.py .....
tests/test_router.py .....
22 passed in 0.04s
```

## Compile Check

Command:

```bash
python3 -m compileall src tests
```

Outcome:

```text
Listing 'src'...
Listing 'src/odl_vl'...
Listing 'tests'...
Listing 'tests/fixtures'...
Compiling 'tests/test_ledger.py'...
Compiling 'tests/test_router.py'...
```

Exit status: 0.

## CLI QA Snippet

Command:

```bash
PYTHONPATH=src python3 - <<'PY'
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from odl_vl.ledger import LedgerEvent, append_ledger_event
from odl_vl.router import RoutingTask, choose_route

manifest = json.loads(Path('tests/fixtures/manifest.json').read_text(encoding='utf-8'))
families = manifest['families']
secret_hex = '0123456789abcdef' * 2
other_secret_hex = 'fedcba9876543210' * 2
url_secret_hex = 'aabbccddeeff0011' * 2
scenarios = [
    ('simple_text', RoutingTask(fixture_family='simple_text')),
    ('merged_table', RoutingTask(fixture_family='merged_table', needs_table_structure=True)),
    ('chart_like_page', RoutingTask(fixture_family='chart_like_page', needs_image_description=True)),
]
with tempfile.TemporaryDirectory() as temp_dir:
    ledger_path = Path(temp_dir) / 'ledger.jsonl'
    routed = []
    for family, task in scenarios:
        decision = choose_route(task, family_metadata=families[family])
        routed.append((family, decision.provider.value, decision.reason))
        append_ledger_event(
            ledger_path,
            LedgerEvent(
                provider=decision.provider.value,
                model_alias='local-deterministic' if decision.provider.value == 'deterministic' else 'fixture-model',
                route_reason=decision.reason,
                latency_ms=1.0,
                status='ok',
                fallback=decision.fallback,
                cost_estimate_usd=0.0,
                metadata={
                    'family': family,
                    'API_KEY': secret_hex,
                    'TOKEN': other_secret_hex,
                    'signed_url': f'https://example.invalid/result?token={url_secret_hex}',
                },
            ),
        )
    contents = ledger_path.read_text(encoding='utf-8')
    assert 'API_KEY' not in contents
    assert 'TOKEN' not in contents
    assert re.search(r'[0-9a-fA-F]{32,}', contents) is None
    print(routed)
PY
```

Outcome:

```text
[('simple_text', 'deterministic', 'fixture:simple_text expected deterministic_only'), ('merged_table', 'paddle', 'hint:needs_table_structure'), ('chart_like_page', 'gemini', 'hint:needs_image_description')]
```

The snippet routed all required families, wrote JSONL ledger events to a temp file, and asserted that `API_KEY`, `TOKEN`, and 32+ hex token patterns were absent from the ledger contents.

## File Size Check

Command:

```bash
python3 - <<'PY'
from pathlib import Path
paths = [
    Path('src/odl_vl/ir.py'),
    Path('src/odl_vl/router.py'),
    Path('src/odl_vl/ledger.py'),
    Path('tests/test_router.py'),
    Path('tests/test_ledger.py'),
]
for path in paths:
    count = 0
    for line in path.read_text(encoding='utf-8').splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith('#'):
            count += 1
    print(f'{path}: {count}')
PY
```

Outcome:

```text
src/odl_vl/ir.py: 38
src/odl_vl/router.py: 58
src/odl_vl/ledger.py: 67
tests/test_router.py: 38
tests/test_ledger.py: 59
```

All changed files are under 250 pure LOC.

## Redaction Fix: Non-Hex Long Token-Like Values

Scope update: amended only `src/odl_vl/ledger.py`, `tests/test_ledger.py`, and this evidence file to redact long mixed alphanumeric/base64url-like values, not only 32+ hex values.

### TDD Red For Non-Hex Token Gap

Command:

```bash
python3 -m pytest tests/test_ledger.py
```

Outcome before the implementation fix:

```text
collected 3 items
tests/test_ledger.py ..F
FAILED tests/test_ledger.py::test_redacted_event_removes_long_non_hex_token_like_values_but_keeps_safe_text
```

The failing assertion confirmed that a long mixed non-hex token-like metadata value remained in rendered ledger JSON. The failure output is intentionally not copied here because it included the fake token value used to prove the leak.

### Requested Verification Commands

Command:

```bash
python3 -m pytest tests/test_ledger.py
```

Outcome after the implementation fix:

```text
collected 3 items
tests/test_ledger.py ...
3 passed in 0.01s
```

Command:

```bash
python3 -m pytest tests/test_router.py tests/test_ledger.py
```

Outcome:

```text
collected 8 items
tests/test_router.py .....
tests/test_ledger.py ...
8 passed in 0.02s
```

Command:

```bash
python3 -m pytest
```

Outcome:

```text
collected 23 items
tests/test_config.py .....
tests/test_fixture_manifest.py .....
tests/test_ledger.py ...
tests/test_providers.py .....
tests/test_router.py .....
23 passed in 0.04s
```

### File Size Check For Fix Files

Command:

```bash
python3 - <<'PY'
from pathlib import Path
for path in [Path('src/odl_vl/ledger.py'), Path('tests/test_ledger.py')]:
    count = 0
    for line in path.read_text(encoding='utf-8').splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith('#'):
            count += 1
    print(f'{path}: {count}')
PY
```

Outcome:

```text
src/odl_vl/ledger.py: 71
tests/test_ledger.py: 81
```

Both modified code/test files remain under 250 pure LOC.
