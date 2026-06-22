# Task 2 Evidence: Provider Request Builders and Offline Client Seams

## Scope

Implemented Todo 2 from `.omo/plans/odl-vl-parser.md` by adding only the requested task files:

- `src/odl_vl/providers.py`
- `tests/test_providers.py`
- `.omo/evidence/task-2-odl-vl-parser.md`

Runtime provider code uses Python stdlib only. Unit tests use injected fake transport and make no live API calls. The request dataclasses and `HttpRequest` hide authorization headers/API keys from `repr` while still constructing `Authorization: Bearer ...` headers.

## Commands Run and Outcomes

### RED: provider module missing before implementation

Command:

```bash
python3 -m pytest tests/test_providers.py
```

Outcome:

```text
collected 0 items / 1 error
ModuleNotFoundError: No module named 'odl_vl.providers'
```

This confirmed the new provider tests failed for the intended missing module before adding runtime code.

### Targeted provider tests after implementation

Command:

```bash
python3 -m pytest tests/test_providers.py
```

Outcome:

```text
tests/test_providers.py .... [100%]
4 passed in 0.02s
```

### LSP diagnostics attempt

Commands:

```text
lsp_diagnostics /Users/jaesolshin/Documents/GitHub/odl-vl/src/odl_vl/providers.py severity=error
lsp_diagnostics /Users/jaesolshin/Documents/GitHub/odl-vl/tests/test_providers.py severity=error
```

Outcome:

```text
Language server 'ty' not found.
Install with: Install ty from https://github.com/astral-sh/ty
```

### Compile check

Command:

```bash
python3 -m compileall src tests
```

Outcome: passed. Python listed and compiled `src`, `src/odl_vl`, `tests`, and `tests/fixtures` without errors.

### Full pytest regression check

Command:

```bash
python3 -m pytest
```

Outcome:

```text
tests/test_config.py ..... [ 35%]
tests/test_fixture_manifest.py ..... [ 71%]
tests/test_providers.py .... [100%]
14 passed in 0.03s
```

### CLI surface QA: request summary without secret output

Initial command without `PYTHONPATH`:

```bash
python3 - <<'PY'
import json
import urllib.parse
from odl_vl.providers import (
    GeminiGenerateContentRequest,
    PaddleSubmitRequest,
    build_gemini_generate_content_request,
    build_paddle_submit_request,
)

gemini_key = "fake-gemini-secret-cli"
paddle_key = "fake-paddle-secret-cli"
gemini = build_gemini_generate_content_request(
    GeminiGenerateContentRequest(api_key=gemini_key, prompt="Extract visible text.")
)
paddle = build_paddle_submit_request(
    PaddleSubmitRequest(
        api_key=paddle_key,
        base_url="https://paddle.example.invalid",
        document_url="https://fixtures.example.invalid/page.png",
    )
)
gemini_url = urllib.parse.urlparse(gemini.url)
paddle_url = urllib.parse.urlparse(paddle.url)
gemini_body = json.loads(gemini.body.decode("utf-8"))
paddle_body = json.loads(paddle.body.decode("utf-8"))
summary = json.dumps(
    {
        "gemini": {
            "host": gemini_url.netloc,
            "path": gemini_url.path,
            "model": gemini_url.path.split("/models/", 1)[1].removesuffix(":generateContent"),
            "parts": len(gemini_body["contents"][0]["parts"]),
        },
        "paddle": {
            "host": paddle_url.netloc,
            "path": paddle_url.path,
            "model": paddle_body["model"],
        },
    },
    sort_keys=True,
)
assert gemini_key not in summary
assert paddle_key not in summary
print(summary)
PY
```

Outcome:

```text
ModuleNotFoundError: No module named 'odl_vl'
```

Corrected command with explicit CLI import path:

```bash
PYTHONPATH=src python3 - <<'PY'
import json
import urllib.parse
from odl_vl.providers import (
    GeminiGenerateContentRequest,
    PaddleSubmitRequest,
    build_gemini_generate_content_request,
    build_paddle_submit_request,
)

gemini_key = "fake-gemini-secret-cli"
paddle_key = "fake-paddle-secret-cli"
gemini = build_gemini_generate_content_request(
    GeminiGenerateContentRequest(api_key=gemini_key, prompt="Extract visible text.")
)
paddle = build_paddle_submit_request(
    PaddleSubmitRequest(
        api_key=paddle_key,
        base_url="https://paddle.example.invalid",
        document_url="https://fixtures.example.invalid/page.png",
    )
)
gemini_url = urllib.parse.urlparse(gemini.url)
paddle_url = urllib.parse.urlparse(paddle.url)
gemini_body = json.loads(gemini.body.decode("utf-8"))
paddle_body = json.loads(paddle.body.decode("utf-8"))
summary = json.dumps(
    {
        "gemini": {
            "host": gemini_url.netloc,
            "path": gemini_url.path,
            "model": gemini_url.path.split("/models/", 1)[1].removesuffix(":generateContent"),
            "parts": len(gemini_body["contents"][0]["parts"]),
        },
        "paddle": {
            "host": paddle_url.netloc,
            "path": paddle_url.path,
            "model": paddle_body["model"],
        },
    },
    sort_keys=True,
)
assert gemini_key not in summary
assert paddle_key not in summary
print(summary)
PY
```

Outcome: passed and printed only URL host/path plus model names. The fake secrets did not appear in stdout.

```text
{"gemini": {"host": "generativelanguage.googleapis.com", "model": "gemini-3.1-flash-lite", "parts": 1, "path": "/v1beta/models/gemini-3.1-flash-lite:generateContent"}, "paddle": {"host": "paddle.example.invalid", "model": "PaddleOCR-VL-1.6", "path": "/api/v2/ocr/jobs"}}
```

### Changed file pure LOC check

Command:

```bash
awk '!/^[[:space:]]*$/ && !/^[[:space:]]*(#)/' src/odl_vl/providers.py tests/test_providers.py | wc -l
```

Outcome:

```text
195
```

Both changed Python files together remain below the 200 LOC healthy threshold.

## Fix Verification: PaddleOCR Official JSON Mode Payload

### RED: tests updated before runtime fix

Command:

```bash
python3 -m pytest tests/test_providers.py
```

Outcome:

```text
tests/test_providers.py .FF.. [100%]
2 failed, 3 passed in 0.04s
```

The failures confirmed the old runtime still emitted `input.url` and `PaddleSubmitRequest` did not accept `optional_payload`.

### Targeted provider tests after fix

Command:

```bash
python3 -m pytest tests/test_providers.py
```

Outcome:

```text
tests/test_providers.py ..... [100%]
5 passed in 0.02s
```

The provider tests now assert the exact Paddle submit payload shape:

```json
{
  "fileUrl": "https://fixtures.example.invalid/page.png",
  "model": "PaddleOCR-VL-1.6",
  "optionalPayload": {
    "useChartRecognition": false,
    "useDocOrientationClassify": false,
    "useDocUnwarping": false
  }
}
```

### LSP diagnostics attempt

Commands:

```text
lsp_diagnostics /Users/jaesolshin/Documents/GitHub/odl-vl/src/odl_vl/providers.py severity=error
lsp_diagnostics /Users/jaesolshin/Documents/GitHub/odl-vl/tests/test_providers.py severity=error
```

Outcome:

```text
Language server 'ty' not found.
Install with: Install ty from https://github.com/astral-sh/ty
```

### Full pytest regression check

Command:

```bash
python3 -m pytest
```

Outcome:

```text
tests/test_config.py ..... [ 33%]
tests/test_fixture_manifest.py ..... [ 66%]
tests/test_providers.py ..... [100%]
15 passed in 0.03s
```

### Compile check

Command:

```bash
python3 -m compileall src tests
```

Outcome: passed. Python listed `src`, `src/odl_vl`, `tests`, and `tests/fixtures`; it compiled `tests/test_providers.py` without errors.

### CLI surface QA: request summary without secret output

Command:

```bash
PYTHONPATH=src python3 - <<'PY'
import json
import urllib.parse
from odl_vl.providers import (
    GeminiGenerateContentRequest,
    PaddleSubmitRequest,
    build_gemini_generate_content_request,
    build_paddle_submit_request,
)

gemini_key = "fake-gemini-secret-cli"
paddle_key = "fake-paddle-secret-cli"
gemini = build_gemini_generate_content_request(
    GeminiGenerateContentRequest(api_key=gemini_key, prompt="Extract visible text.")
)
paddle = build_paddle_submit_request(
    PaddleSubmitRequest(
        api_key=paddle_key,
        base_url="https://paddle.example.invalid",
        document_url="https://fixtures.example.invalid/page.png",
    )
)
gemini_url = urllib.parse.urlparse(gemini.url)
paddle_url = urllib.parse.urlparse(paddle.url)
gemini_body = json.loads(gemini.body.decode("utf-8"))
paddle_body = json.loads(paddle.body.decode("utf-8"))
summary = json.dumps(
    {
        "gemini": {
            "host": gemini_url.netloc,
            "path": gemini_url.path,
            "model": gemini_url.path.split("/models/", 1)[1].removesuffix(":generateContent"),
            "parts": len(gemini_body["contents"][0]["parts"]),
        },
        "paddle": {
            "host": paddle_url.netloc,
            "path": paddle_url.path,
            "model": paddle_body["model"],
            "optionalPayload": paddle_body["optionalPayload"],
        },
    },
    sort_keys=True,
)
assert gemini_key not in summary
assert paddle_key not in summary
print(summary)
PY
```

Outcome: passed and printed only URL host/path, model names, and boolean optional payload flags. The fake secrets did not appear in stdout.

```text
{"gemini": {"host": "generativelanguage.googleapis.com", "model": "gemini-3.1-flash-lite", "parts": 1, "path": "/v1beta/models/gemini-3.1-flash-lite:generateContent"}, "paddle": {"host": "paddle.example.invalid", "model": "PaddleOCR-VL-1.6", "optionalPayload": {"useChartRecognition": false, "useDocOrientationClassify": false, "useDocUnwarping": false}, "path": "/api/v2/ocr/jobs"}}
```

### Changed Python file pure LOC check

Command:

```bash
for file in src/odl_vl/providers.py tests/test_providers.py; do printf '%s ' "$file"; awk '!/^[[:space:]]*$/ && !/^[[:space:]]*(#)/' "$file" | wc -l; done
```

Outcome:

```text
src/odl_vl/providers.py      120
tests/test_providers.py      115
```

Both changed Python files remain below the 200 LOC healthy threshold individually.

## Follow-up Compatibility Fix: Paddle jobs endpoint base URL

Date: 2026-06-22

Provider URL normalization was updated so `PaddleSubmitRequest` and `PaddlePollRequest` accept either the service root (`https://paddleocr.aistudio-app.com`) or the full jobs endpoint (`https://paddleocr.aistudio-app.com/api/v2/ocr/jobs`) without duplicating `/api/v2/ocr/jobs`.

Commands and outcomes:

```bash
python3 -m pytest tests/test_providers.py tests/test_smoke_cli.py
```

Outcome: passed, `11 passed in 0.03s`.

```bash
python3 -m pytest
```

Outcome: passed, `29 passed in 0.05s`.

Live Paddle smoke result is recorded in `.omo/evidence/task-4-odl-vl-parser.md`; output was redacted and no result files were downloaded.
