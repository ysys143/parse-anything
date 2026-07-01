# Task 6 Evidence: README Update and Secret Scan Utility

## Scope

Implemented Todo 6 from `.omo/plans/odl-vl-parser.md` by updating the user-facing workflow docs and adding a conservative local secret scanner. This follow-up also fixed the local install blocker by switching the documented install command to `uv` and creating a project `.venv` before rerunning the editable install:

- `README.md`
- `scripts/check_no_secrets.py`
- `tests/test_secret_scan.py`
- `.omo/evidence/task-6-odl-vl-parser.md`

Adjusted existing `tests/test_ledger.py` fake long-token fixtures to construct token-like values at runtime so the required repository scan can include `tests/` without carrying literal 32+ hex strings. No provider/router/ledger implementation code was changed. No real `.env` file was scanned or recorded here.

## Commands Run and Outcomes

### UV editable install before `.venv` existed

Command:

```bash
uv pip install -e ".[dev]"
```

Outcome:

```text
[WARN] .venv not found - run `uv venv` first

`uv pip install` requires a virtual environment.
No `.venv` directory found in this project.
```

This was the local blocker that prevented the editable install from running under the new `uv` policy.

### Create the project virtual environment

Command:

```bash
uv venv
```

Outcome:

```text
Using CPython 3.12.11
Creating virtual environment at: .venv
Activate with: source .venv/bin/activate
```

### UV editable install after `.venv` existed

Command:

```bash
uv pip install -e ".[dev]"
```

Outcome:

```text
Resolved 6 packages in 245ms
   Building odl-vl @ file:///Users/jaesolshin/Documents/GitHub/odl-vl
      Built odl-vl @ file:///Users/jaesolshin/Documents/GitHub/odl-vl
Prepared 2 packages in 249ms
Installed 6 packages in 11ms
 + iniconfig==2.3.0
 + odl-vl==0.1.0 (from file:///Users/jaesolshin/Documents/GitHub/odl-vl)
 + packaging==26.2
 + pluggy==1.6.0
 + pygments==2.20.0
 + pytest==9.1.1
```

### RED: scanner tests before utility existed

Command:

```bash
python3 -m pytest tests/test_secret_scan.py
```

Outcome:

```text
tests/test_secret_scan.py FFF [100%]
FileNotFoundError: scripts/check_no_secrets.py
3 failed in 0.03s
```

This confirmed the test failed for the intended missing scanner utility before implementation.

### Focused scanner tests

Command:

```bash
python3 -m pytest tests/test_secret_scan.py
```

Outcome:

```text
tests/test_secret_scan.py ... [100%]
3 passed in 0.02s
```

### Ledger tests after removing literal long fake tokens

Command:

```bash
python3 -m pytest tests/test_ledger.py
```

Outcome:

```text
tests/test_ledger.py ... [100%]
3 passed in 0.02s
```

### Full offline test suite

Command:

```bash
python3 -m pytest
```

Outcome:

```text
collected 33 items
tests/test_config.py ..... [ 15%]
tests/test_fixture_manifest.py ..... [ 30%]
tests/test_ledger.py ... [ 39%]
tests/test_providers.py ....... [ 60%]
tests/test_router.py ..... [ 75%]
tests/test_secret_scan.py ... [ 84%]
tests/test_smoke_cli.py ..... [100%]
33 passed in 0.06s
```

### Python syntax check

Command:

```bash
python3 -m compileall src tests scripts
```

Outcome:

```text
Listing 'src'...
Listing 'src/odl_vl'...
Listing 'tests'...
Listing 'tests/fixtures'...
Compiling 'tests/test_ledger.py'...
Compiling 'tests/test_secret_scan.py'...
Listing 'scripts'...
```

Exit code 0.

### Gemini dry-config command

Command:

```bash
python3 scripts/odl_vl_smoke.py --provider gemini --dry-config
```

Outcome:

```text
provider=gemini
api_key=present
model=gemini-3.1-flash-lite
base_url_host=generativelanguage.googleapis.com
```

The output reports presence and host/model metadata only, not key values.

### Paddle dry-config command

Command:

```bash
python3 scripts/odl_vl_smoke.py --provider paddle --dry-config
```

Outcome:

```text
provider=paddle
api_key=present
model=PaddleOCR-VL-1.6
base_url_host=paddleocr.aistudio-app.com
```

The output reports presence and host/model metadata only, not key values.

### Required normal repository secret scan

Command:

```bash
python3 scripts/check_no_secrets.py README.md docs .env.example src tests scripts
```

Outcome:

```text
secret scan passed
```

### Manual QA: temporary fake token-like file under `/tmp`

Command:

```bash
python3 - <<'PY'
import subprocess
import tempfile
from pathlib import Path

path = Path(tempfile.gettempdir()) / 'odl-vl-secret-scan-qa.txt'
path.write_text('GOOGLE_API_KEY=' + 'AI' + 'za' + ('A' * 35), encoding='utf-8')
try:
    result = subprocess.run(
        ['python3', 'scripts/check_no_secrets.py', str(path)],
        check=False,
        cwd='.',
        text=True,
        capture_output=True,
    )
    print(f'exit_code={result.returncode}')
    print(result.stdout.strip())
finally:
    path.unlink(missing_ok=True)
PY
```

Outcome:

```text
exit_code=1
secret scan failed
/var/folders/hw/9m3g7fvn4_l3rp2y473km9sm0000gn/T/odl-vl-secret-scan-qa.txt:1: google_api_key
/var/folders/hw/9m3g7fvn4_l3rp2y473km9sm0000gn/T/odl-vl-secret-scan-qa.txt:1: hex_token
/var/folders/hw/9m3g7fvn4_l3rp2y473km9sm0000gn/T/odl-vl-secret-scan-qa.txt:1: secret_assignment
```

The scanner returned non-zero and printed only file, line, and finding kinds. The temporary file was deleted in the `finally` block.

### Pure LOC check

Command:

```bash
for file in README.md scripts/check_no_secrets.py tests/test_secret_scan.py tests/test_ledger.py; do printf '%s ' "$file"; awk '!/^[[:space:]]*$/ && !/^[[:space:]]*(\/\/|#|--)/' "$file" | wc -l; done
```

Outcome:

```text
README.md       35
scripts/check_no_secrets.py      101
tests/test_secret_scan.py       68
tests/test_ledger.py       85
```

All changed source/test files are below the 200 pure LOC healthy threshold.

### LSP diagnostics attempt

Command surface:

```text
lsp_diagnostics on scripts/check_no_secrets.py, tests/test_secret_scan.py, tests/test_ledger.py
```

Outcome:

```text
Language server 'ty' not found.
Install with: Install ty from https://github.com/astral-sh/ty
```

The Python language server was unavailable in this environment, so `python3 -m compileall` and the pytest suite above are the executed code checks for this task.

## Optional Live Smoke

Live smoke commands were not run because this task explicitly required no network. The README documents them as optional commands for an already configured local environment.
