# Task 4 Evidence: live smoke CLI for Gemini and PaddleOCR

Date: 2026-06-22

## TDD red

Command:

```bash
python3 -m pytest tests/test_smoke_cli.py
```

Outcome: failed as expected before implementation. All 3 initial tests failed with `FileNotFoundError` for `scripts/odl_vl_smoke.py`.

## Offline tests

Command:

```bash
python3 -m pytest tests/test_smoke_cli.py
```

Outcome: passed, `4 passed in 0.03s`.

Command:

```bash
python3 -m pytest tests/test_config.py tests/test_providers.py tests/test_smoke_cli.py
```

Outcome: passed, `14 passed in 0.03s`.

Command:

```bash
python3 -m py_compile scripts/odl_vl_smoke.py tests/test_smoke_cli.py
```

Outcome: passed with exit code 0 and no output.

## Dry-config CLI checks

Command:

```bash
python3 scripts/odl_vl_smoke.py --provider gemini --dry-config
```

Outcome: passed with exit code 0. Output reported `provider=gemini`, `api_key=present`, model `gemini-3.1-flash-lite`, and host `generativelanguage.googleapis.com`. No key or `.env` value was printed.

Command:

```bash
python3 scripts/odl_vl_smoke.py --provider paddle --dry-config
```

Outcome: passed with exit code 0. Output reported `provider=paddle`, `api_key=present`, model `PaddleOCR-VL-1.6`, and only the Paddle base URL host. No key or `.env` value was printed.

## Manual CLI surface

Command:

```bash
python3 scripts/odl_vl_smoke.py --help
```

Outcome: passed with exit code 0. Help listed `--provider {gemini,paddle}`, `--dry-config`, `--live`, `--demo-url`, `--timeout`, and `--poll-interval`.

Command:

```bash
python3 scripts/odl_vl_smoke.py --provider gemini
```

Outcome: failed as expected. `argparse` reported that one of `--dry-config` or `--live` is required.

## Optional live CLI checks

Command:

```bash
python3 scripts/odl_vl_smoke.py --provider gemini --live
```

Outcome: passed with redacted output: `provider=gemini live=pass status=200 text=ok`. No key, full response body, or `.env` value was printed.

Command:

```bash
python3 scripts/odl_vl_smoke.py --provider paddle --live --demo-url https://paddle-model-ecology.bj.bcebos.com/paddlex/imgs/demo_image/paddleocr_vl_demo.png --timeout 45
```

Outcome: failed safely with redacted output: `provider=paddle live=fail submit_status=404`. No key, signed URL, result file, full response body, or `.env` value was printed.

## Size check

Command:

```bash
awk '!/^[[:space:]]*$/ && !/^[[:space:]]*(#|\/\/|--)/' scripts/odl_vl_smoke.py | wc -l
awk '!/^[[:space:]]*$/ && !/^[[:space:]]*(#|\/\/|--)/' tests/test_smoke_cli.py | wc -l
```

Outcome: `scripts/odl_vl_smoke.py` measured 249 pure LOC and `tests/test_smoke_cli.py` measured 146 pure LOC.

## LSP diagnostics

Command: LSP diagnostics for `scripts/odl_vl_smoke.py` and `tests/test_smoke_cli.py`.

Outcome: not available because the configured Python language server `ty` is not installed in this environment. Syntax compilation and pytest checks above passed.

## Blocker Fix: Paddle full jobs endpoint base URL

Date: 2026-06-22

Issue: Paddle live smoke previously returned `submit_status=404` because local `PADDLE_BASE_URL` can be the full jobs endpoint, while the provider builder always appended `/api/v2/ocr/jobs`.

### RED: endpoint base URL tests before provider fix

Command:

```bash
python3 -m pytest tests/test_providers.py
```

Outcome: failed as expected with 2 failures. The new submit and poll tests showed duplicated paths like `/api/v2/ocr/jobs/api/v2/ocr/jobs`.

### Targeted provider and smoke tests

Command:

```bash
python3 -m pytest tests/test_providers.py tests/test_smoke_cli.py
```

Outcome: passed, `11 passed in 0.03s`.

Command:

```bash
python3 -m py_compile src/odl_vl/providers.py scripts/odl_vl_smoke.py tests/test_providers.py tests/test_smoke_cli.py
```

Outcome: passed with exit code 0 and no output.

### Full regression tests

Command:

```bash
python3 -m pytest
```

Outcome: passed, `29 passed in 0.05s`.

### Final Paddle live smoke

Command:

```bash
python3 scripts/odl_vl_smoke.py --provider paddle --live --demo-url https://paddle-model-ecology.bj.bcebos.com/paddlex/imgs/demo_image/paddleocr_vl_demo.png --timeout 60
```

Outcome: passed with redacted output: `provider=paddle live=pass submit_status=200 poll_status=done polls=1`. No API key, `.env` value, signed URL, full response body, or result file was printed or downloaded.

### Size check after provider change

Command:

```bash
awk '!/^[[:space:]]*$/ && !/^[[:space:]]*(#|\/\/|--)/' src/odl_vl/providers.py | wc -l
awk '!/^[[:space:]]*$/ && !/^[[:space:]]*(#|\/\/|--)/' tests/test_providers.py | wc -l
```

Outcome: `src/odl_vl/providers.py` measured 127 pure LOC and `tests/test_providers.py` measured 139 pure LOC.

## Blocker Fix: Paddle poll HTTP status precedence

Date: 2026-06-22

Issue: Paddle poll handling could trust a `done`/`completed` status in the JSON body even when the HTTP status was non-2xx. The smoke CLI now reports `http_<status>` failure before inspecting the body for non-2xx poll responses.

### RED: non-2xx poll with done body before fix

Command:

```bash
python3 -m pytest tests/test_smoke_cli.py
```

Outcome: failed as expected. The new offline test used a poll response `status_code=500` with body `{"data":{"status":"done"}}`; current code incorrectly returned exit code 0 instead of failing with `poll_status=http_500`.

### Targeted smoke tests

Command:

```bash
python3 -m pytest tests/test_smoke_cli.py
```

Outcome: passed, `5 passed in 0.03s`.

Command:

```bash
python3 -m pytest tests/test_providers.py tests/test_smoke_cli.py
```

Outcome: passed, `12 passed in 0.03s`.

Command:

```bash
python3 -m py_compile scripts/odl_vl_smoke.py tests/test_smoke_cli.py
```

Outcome: passed with exit code 0 and no output.

### Full regression tests

Command:

```bash
python3 -m pytest
```

Outcome: passed, `30 passed in 0.05s`.

### Dry-config and live smoke checks

Command:

```bash
python3 scripts/odl_vl_smoke.py --provider gemini --dry-config
```

Outcome: passed with redacted output: provider, key presence, model, and host only.

Command:

```bash
python3 scripts/odl_vl_smoke.py --provider paddle --dry-config
```

Outcome: passed with redacted output: provider, key presence, model, and host only.

Command:

```bash
python3 scripts/odl_vl_smoke.py --provider gemini --live
```

Outcome: passed with redacted output: `provider=gemini live=pass status=200 text=ok`.

Command:

```bash
python3 scripts/odl_vl_smoke.py --provider paddle --live --demo-url https://paddle-model-ecology.bj.bcebos.com/paddlex/imgs/demo_image/paddleocr_vl_demo.png --timeout 60
```

Outcome: passed with redacted output: `provider=paddle live=pass submit_status=200 poll_status=done polls=1`. No API keys, `.env` values, signed URLs, full response bodies, result URLs, or result files were printed or downloaded.

### Size and diagnostics

Command:

```bash
awk '!/^[[:space:]]*$/ && !/^[[:space:]]*(#|\/\/|--)/' scripts/odl_vl_smoke.py | wc -l
awk '!/^[[:space:]]*$/ && !/^[[:space:]]*(#|\/\/|--)/' tests/test_smoke_cli.py | wc -l
```

Outcome: `scripts/odl_vl_smoke.py` measured 249 pure LOC and `tests/test_smoke_cli.py` measured 175 pure LOC.

LSP diagnostics remained unavailable because the configured Python language server `ty` is not installed. Syntax compilation and pytest checks above passed.
