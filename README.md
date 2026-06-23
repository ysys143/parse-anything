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

Run focused checks for the provider layer:

```bash
python3 -m pytest tests/test_config.py tests/test_providers.py tests/test_normalizers.py tests/test_paddle_jobs.py tests/test_smoke_cli.py tests/test_fixture_manifest.py
```

Run focused checks for the PDF pipeline:

```bash
python3 -m pytest tests/test_pipeline_*.py tests/test_pdf_to_markdown_cli.py
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

## PDF Pipeline (`pdf_to_markdown`)

The current CLI renders PDF pages, extracts deterministic text/values (pypdfium2),
processes each page (deterministic or VLM), batches page-spanning tables into one
multi-image VLM request, applies the born-digital value oracle gate and the scan
legibility gate, and writes per-page Markdown, a `document.md` assembly,
`ledger.jsonl`, and `results.jsonl`.

```bash
# deterministic only -- no network, no keys
python3 scripts/pdf_to_markdown.py --pdf path/to/doc.pdf --out out/ --no-vlm

# with VLM -- uses GEMINI_API_KEY from .env when present
python3 scripts/pdf_to_markdown.py --pdf path/to/doc.pdf --out out/
```

Guards surface as flags in `ledger.jsonl` for review rather than silently trusting
output: a VLM-needed page with no key is flagged `vlm_unavailable`; a scan the model
judges unreadable abstains (`illegible_low_quality`); a VLM number absent from the
born-digital text layer is flagged `unsourced_number:<v>`. Run artifacts (`pages/`,
`document.md`, `ledger.jsonl`, `results.jsonl`) are git-ignored.

### Target architecture (diagnose-then-configure)

The CLI above does per-page routing at runtime; measurement showed that is a
false-positive gamble (no deterministic structure detector is reliable across document
types — see [F16/F17](docs/measurement-findings.md)). The target architecture instead:

- **Diagnoses a *source*** (a stream of similar documents) once / periodically and produces
  a **source profile** — built-in VLM diagnostic for routine ingestion, or a flagship
  **coding-agent skill** (Claude Code / Codex) for hard sources and calibration.
- **Runs a configured mode** (no runtime routing): **deterministic** (ODL for structure +
  pypdfium2 for value completeness/bbox) or **deterministic-powered VLM** (ODL + pypdfium2 +
  VLM all reconciled, value oracle gating VLM numbers).
- **Emits a rich output contract** — `pages/`, `document.md`, `document.json` (loss-aware,
  source-of-truth), `tables/`, `assets/`, plus source-level metadata — not Markdown alone
  (current code is MD + ledger only).

See [processing tiers and domain adaptation](docs/processing-tiers-and-adaptation.md) (§2.5–2.6, P7)
and [PDF pipeline requirements](docs/pdf-pipeline-requirements.md) (§3.4, §4, §7).

> The earlier ODL-like-JSON external orchestrator scaffold has been **removed** and
> superseded by this pipeline. The shared provider layer (`config`, `providers`,
> `paddle_jobs`, `normalizers`, `cli_support`) and the smoke CLI are retained.

## Fixture Plan

The fixture work is metadata-only in this slice. The initial eight fixture families and page-level golden schema contract live under [`tests/fixtures/`](tests/fixtures/README.md). The fixture sufficiency and discriminativeness criteria are documented in [VLM provider and fixture plan](docs/vlm-provider-and-fixture-plan.md#5-fixture-and-golden-set-strategy).

## Design Notes

- [Measurement findings](docs/measurement-findings.md): prototype evidence (renderer, layer choice, hallucination, oracle, cross-page, triage, orientation, table structure) behind the pipeline design.
- [External orchestrator architecture](docs/orchestrator-architecture.md): historical -- the design of the removed page-level scaffold, superseded by the PDF pipeline.
- [PDF pipeline requirements](docs/pdf-pipeline-requirements.md): mandatory full-pipeline behavior for rendering, processing-depth routing, complex/page-spanning tables, VLM inputs, numeric guards, outputs, validation, and provider/privacy constraints.
- [Processing tiers and domain adaptation](docs/processing-tiers-and-adaptation.md): deterministic/VLM/human boundaries, escalation policy, and domain calibration tooling.
- [VLM provider and fixture plan](docs/vlm-provider-and-fixture-plan.md): PaddleOCR official API + Gemini direct 개발 결정, provider key 계약, fixture/golden-set 전략.
