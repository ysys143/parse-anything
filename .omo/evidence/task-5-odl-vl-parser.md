# Task 5 Evidence: Fixture Manifest and Golden Schema Docs

## Scope

Implemented Todo 5 from `.omo/plans/odl-vl-parser.md` by adding only the requested fixture contract files:

- `tests/fixtures/manifest.json`
- `tests/fixtures/golden_schema.json`
- `tests/fixtures/README.md`
- `tests/test_fixture_manifest.py`
- `.omo/evidence/task-5-odl-vl-parser.md`

No actual PDF or image fixtures were created. No private document paths, downloaded benchmark files, provider code, `src/odl_vl`, `pyproject.toml`, `.env.example`, root `README.md`, or unrelated docs were changed.

## Commands Run and Outcomes

### RED: contract test before fixture files

Command:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_fixture_manifest.py
```

Outcome:

```text
5 failed in 0.07s
FileNotFoundError: tests/fixtures/manifest.json
FileNotFoundError: tests/fixtures/golden_schema.json
```

This confirmed the new test failed for the intended missing fixture contract files before adding the JSON/docs.

### Required pytest acceptance

Command:

```bash
python3 -m pytest tests/test_fixture_manifest.py
```

Outcome:

```text
tests/test_fixture_manifest.py ..... [100%]
5 passed in 0.01s
```

### Plugin-isolated pytest check

Command:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_fixture_manifest.py
```

Outcome:

```text
tests/test_fixture_manifest.py ..... [100%]
5 passed in 0.01s
```

### Data-surface manifest/schema snippet

Command:

```bash
python3 - <<'PY'
import json
from collections import Counter
from pathlib import Path

manifest = json.loads(Path('tests/fixtures/manifest.json').read_text(encoding='utf-8'))
schema = json.loads(Path('tests/fixtures/golden_schema.json').read_text(encoding='utf-8'))
required = {
    'expected_route',
    'primary_metric',
    'mutation_strategy',
    'expected_challenge',
    'source_type',
    'page_count',
    'language_profile',
    'generation_recipe',
    'scoring_targets',
    'expected_outputs',
    'route_rationale',
}
families = manifest['families']
missing = {
    family: sorted(required - set(metadata))
    for family, metadata in families.items()
    if required - set(metadata)
}
routes = dict(sorted(Counter(metadata['expected_route'] for metadata in families.values()).items()))
print(f"family_count={len(families)}")
print(f"route_distribution={routes}")
print(f"missing_fields={missing}")
assert manifest['golden_schema_version'] == schema['schema_version']
PY
```

Outcome:

```text
family_count=8
route_distribution={'deterministic_only': 1, 'gemini_vlm': 1, 'hybrid': 4, 'paddle_ocr': 2}
missing_fields={}
```

### Python syntax check

Command:

```bash
python3 -m py_compile tests/test_fixture_manifest.py
```

Outcome: exit code 0, no output.

### Pure LOC check

Command:

```bash
for file in tests/test_fixture_manifest.py; do printf '%s ' "$file"; awk '!/^[[:space:]]*$/ && !/^[[:space:]]*(\/\/|#|--)/' "$file" | wc -l; done
```

Outcome:

```text
tests/test_fixture_manifest.py       92
```
