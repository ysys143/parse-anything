# odl-vl

ODL-VL parsing experiments for evaluating a deterministic parsing front with VLM/OCR provider fallbacks. This repository currently documents and scaffolds the initial development loop; it does not claim production readiness.

## Provider Decision

Initial development is limited to **PaddleOCR official API** and **Gemini direct**.

- PaddleOCR official API is the primary OCR/VLM provider path for PaddleOCR-VL style jobs.
- Gemini direct is included as a comparison VLM provider and fallback candidate.
- Ollama, GLM-OCR, and NGC/Nemotron are deferred until the provider interface, ledger, and fixture bake-off are stable.
- API keys and live provider credentials must stay in local environment configuration only and must not be committed.

See [VLM provider and fixture plan](docs/vlm-provider-and-fixture-plan.md) for the full decision record, provider environment-variable names, routing notes, and fixture strategy.

## Setup

Install the package and test dependency in editable mode:

```bash
uv pip install -e ".[dev]"
```

Prepare local provider configuration outside git-tracked files. `.env.example` documents the expected variable names only; keep actual values in a local `.env`, shell, CI secret store, or deployment secret store.

## Offline Development Checks

Run deterministic tests and syntax checks without network access:

```bash
python3 -m pytest
python3 -m compileall src tests scripts
python3 scripts/check_no_secrets.py README.md docs .env.example src tests scripts
```

Run focused checks for this parser slice:

```bash
python3 -m pytest tests/test_config.py tests/test_providers.py tests/test_router.py tests/test_ledger.py tests/test_smoke_cli.py tests/test_fixture_manifest.py tests/test_secret_scan.py
```

Run focused checks for the external orchestration slice:

```bash
python3 -m pytest tests/test_orchestrator_input.py tests/test_normalizers.py tests/test_orchestrator.py tests/test_orchestrate_cli.py tests/test_orchestrator_fixture.py
```

## Dry Configuration Checks

These commands inspect provider configuration presence and selected non-secret metadata only. They must not print key values.

```bash
python3 scripts/odl_vl_smoke.py --provider gemini --dry-config
python3 scripts/odl_vl_smoke.py --provider paddle --dry-config
```

## Optional Live Smoke Checks

Run live smoke checks only when local environment variables are already configured. These commands call external services and may fail because of local auth, provider availability, quota, or network state.

```bash
python3 scripts/odl_vl_smoke.py --provider gemini --live
python3 scripts/odl_vl_smoke.py --provider paddle --live --demo-url https://paddle-model-ecology.bj.bcebos.com/paddlex/imgs/demo_image/paddleocr_vl_demo.png
```

The live smoke commands report pass/fail status without printing API keys, signed result URLs, full response bodies, or local `.env` contents.

## External Orchestration (offline)

The external orchestrator consumes ODL-like page JSON (document id, per-page
`first_pass_md`, `page_image` reference, `fixture_family`, and optional routing
hints), routes each page to the deterministic / PaddleOCR / Gemini path via the
existing router, normalizes provider output into the internal IR, and writes a
redacted per-page ledger. **This is not an ODL runner or a PDF renderer**: it
does not execute ODL, render PDF pages, or generate fixture artifacts.

Run the offline orchestration over the sample document. Offline mode uses
synthetic placeholder provider output, so it makes no network call:

```bash
python3 scripts/odl_vl_orchestrate.py \
  --input tests/fixtures/orchestrator/sample_document.json \
  --output-dir /tmp/odl-vl-orchestrator-qa --mode offline
```

Outputs land in the output directory: `results.jsonl` (per-page route, provider,
status), `pages/` markdown files, and `ledger.jsonl`. The ledger records
provider, model alias, route reason, latency, and status only; API keys, signed
result URLs, and raw provider bodies are never written.

`--mode live` is opt-in and calls real providers using the same key contract as
the smoke checks (`GEMINI_API_KEY`, `PADDLE_API_KEY`, `PADDLE_BASE_URL`). It
requires locally configured environment variables; pages whose provider keys are
missing are recorded as failed without leaking any secret value. Gemini direct
authenticates via the `x-goog-api-key` header; PaddleOCR jobs are submitted and
polled, and the completed layout result is fetched from the job's signed result
URL. The signed URL and raw provider bodies are never printed or written to the
ledger.

## Fixture Plan

The fixture work is metadata-only in this slice. The initial eight fixture families and page-level golden schema contract live under [`tests/fixtures/`](tests/fixtures/README.md). The fixture sufficiency and discriminativeness criteria are documented in [VLM provider and fixture plan](docs/vlm-provider-and-fixture-plan.md#5-fixture-and-golden-set-strategy).

## Design Notes

- [VLM provider and fixture plan](docs/vlm-provider-and-fixture-plan.md): PaddleOCR official API + Gemini direct 개발 결정, provider key 계약, fixture/golden-set 전략.
