# odl-vl

ODL-VL parsing experiments for evaluating a deterministic parsing front with VLM/OCR provider fallbacks. This repository currently documents and scaffolds the initial development loop; it does not claim production readiness.

## Provider Decision

Initial development is limited to **PaddleOCR official API** and **Gemini direct**.

- PaddleOCR official API is the primary OCR/VLM provider path for PaddleOCR-VL style jobs.
- Gemini direct is included as a comparison VLM provider and fallback candidate.
- Ollama, GLM-OCR, and NGC/Nemotron are deferred until the provider interface, ledger, and fixture bake-off are stable.
- API keys and live provider credentials must stay in local environment configuration only and must not be committed.

See [VLM provider and fixture plan](docs/vlm-provider-and-fixture-plan.md) for the full decision record, provider environment-variable names, routing notes, and fixture strategy.

## Target PDF Pipeline

The full target is not just per-page OCR. It is a PDF pipeline that renders pages,
keeps deterministic text/table/bbox data as the source of truth, escalates only
when explicit processing-depth triggers require OCR/VLM, reconstructs complex and
page-spanning tables, and writes both readable Markdown and loss-aware JSON. The
mandatory target contract is documented in [PDF pipeline requirements](docs/pdf-pipeline-requirements.md).
The processing-tier boundary and domain-adaptation requirements are documented
in [Processing tiers and domain adaptation](docs/processing-tiers-and-adaptation.md).

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
```

Run focused checks for this parser slice:

```bash
python3 -m pytest tests/test_config.py tests/test_providers.py tests/test_router.py tests/test_ledger.py tests/test_smoke_cli.py tests/test_fixture_manifest.py
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
per-page ledger. **This is not an ODL runner or a PDF renderer**: it
does not execute ODL, render PDF pages, generate fixture artifacts, reconstruct
page-spanning tables, or enforce numeric source guards. Those are target
requirements, not completed behavior in this slice.

Run the offline orchestration over the sample document. Offline mode uses
synthetic placeholder provider output, so it makes no network call:

```bash
python3 scripts/odl_vl_orchestrate.py \
  --input tests/fixtures/orchestrator/sample_document.json \
  --output-dir /tmp/odl-vl-orchestrator-qa --mode offline
```

Outputs land in the output directory: `results.jsonl` (per-page route, provider,
status), `pages/` markdown files, and `ledger.jsonl`. The ledger records
provider, model alias, route reason, latency, and status only. Secrets stay out
of these artifacts at the source -- error reasons are opaque codes (e.g.
`gemini_http_429`), and only non-secret metadata is recorded -- so the ledger is
written faithfully rather than scrubbed field-by-field. The run artifacts
(`results.jsonl`, `ledger.jsonl`) are git-ignored so a run is never committed.

`--mode live` is opt-in and calls real providers using the same key contract as
the smoke checks (`GEMINI_API_KEY`, `PADDLE_API_KEY`, `PADDLE_BASE_URL`). It
requires locally configured environment variables; pages whose provider keys are
missing are recorded as failed without leaking any secret value. Gemini direct
authenticates via the `x-goog-api-key` header; PaddleOCR jobs are submitted and
polled, and the completed layout result is fetched from the job's signed result
URL. The signed URL and raw provider bodies are never printed or written to the
ledger.

Pages are processed sequentially by default. `--max-workers N` (N > 1) is an
opt-in, experimental concurrency knob for live mode; it preserves output order
and serializes ledger writes, but live providers may rate-limit concurrent jobs,
so keep the default of 1 unless you have verified your provider tolerates it.

In live mode the Gemini path fetches the page image from `page_image` and sends
it to the model as base64 `inlineData` alongside the prompt, so the VLM actually
sees the page (not just `first_pass_md`). Cross-provider fallback is not performed
this slice: each page runs only its routed provider, and a failed page is reported
as failed rather than silently re-run through another provider.

The full pipeline output contract is broader: page-level Markdown/JSON, a
document-level Markdown/JSON assembly, logical table outputs, image/table asset
metadata, guard flags, and provider-cost ledger fields. See the requirements
document before treating this CLI output as the final parser artifact format.

## Fixture Plan

The fixture work is metadata-only in this slice. The initial eight fixture families and page-level golden schema contract live under [`tests/fixtures/`](tests/fixtures/README.md). The fixture sufficiency and discriminativeness criteria are documented in [VLM provider and fixture plan](docs/vlm-provider-and-fixture-plan.md#5-fixture-and-golden-set-strategy).

## Design Notes

- [External orchestrator architecture](docs/orchestrator-architecture.md): module map, data flow, input contract, provider modes, contract verification, and security posture.
- [PDF pipeline requirements](docs/pdf-pipeline-requirements.md): mandatory full-pipeline behavior for rendering, processing-depth routing, complex/page-spanning tables, VLM inputs, numeric guards, outputs, validation, and provider/privacy constraints.
- [Processing tiers and domain adaptation](docs/processing-tiers-and-adaptation.md): deterministic/VLM/human boundaries, escalation policy, and domain calibration tooling.
- [VLM provider and fixture plan](docs/vlm-provider-and-fixture-plan.md): PaddleOCR official API + Gemini direct 개발 결정, provider key 계약, fixture/golden-set 전략.
