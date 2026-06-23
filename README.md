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

The CLI is **diagnose-then-configure**, not runtime routing (per-page auto-routing was
measured to be a false-positive gamble — [F16/F17](docs/measurement-findings.md)). It runs a
source in a configured **mode**, both modes using ODL (structure / clean text) + pypdfium2
(value completeness / bbox):

- **`deterministic`** — ODL text + tables, with a pypdfium2 value-completeness backstop
  (`odl_dropped_number:<v>` flags). No network, no keys.
- **`det_vlm`** — adds the VLM for visual structure, reconciled; the born-digital **value
  oracle** (pypdfium2) gates VLM numbers (`unsourced_number:<v>`), and the scan-legibility gate
  lets a degraded scan abstain (`illegible_low_quality`). The **mode is the lever** — `det_vlm`
  with no `GEMINI_API_KEY` is a loud error, never a silent downgrade.

```bash
# deterministic only -- no network, no keys
python3 scripts/pdf_to_markdown.py --pdf doc.pdf --out out/ --mode deterministic

# accuracy mode -- needs GEMINI_API_KEY
python3 scripts/pdf_to_markdown.py --pdf doc.pdf --out out/ --mode det_vlm

# let D-1 diagnose the source and pick the mode (saves a reusable SourceProfile)
python3 scripts/pdf_to_markdown.py --pdf doc.pdf --out out/ --source-id mydocs --diagnose
python3 scripts/pdf_to_markdown.py --pdf doc.pdf --out out/ --source-id mydocs --use-profile
```

**Output** lands under `<out>/<source_id>/<document_id>/` (`document_id` = content hash, so
re-processing is idempotent): `document.md`, `document.json` (loss-aware source of truth —
identity, provenance, pages, tables/figures with bbox + original labels), `tables/`, `assets/`,
`pages/`, `ledger.jsonl`, `results.jsonl`. Run artifacts are git-ignored.

### Source diagnosis (D-1 / D-2)

```bash
# D-1: built-in VLM diagnostic -> recommended mode + evidence (JSON)
python3 scripts/diagnose_source.py --pdf doc.pdf

# D-2: assemble a review bundle for a flagship agent (oracle position) -> SourceProfile
python3 scripts/diagnose_prepare.py --pdf doc.pdf --out bundle/   # see docs/diagnostic-d2.md
```

D-1 measures deterministic-vs-VLM token divergence + scan fraction + (structure-aware-sampled)
table/figure presence and recommends `deterministic` vs `det_vlm` with evidence; D-2 is for
hard sources / per-domain threshold calibration. Both emit a persisted `SourceProfile`.

See [processing tiers and domain adaptation](docs/processing-tiers-and-adaptation.md) (§2.5–2.6, P7),
[PDF pipeline requirements](docs/pdf-pipeline-requirements.md) (§3.4, §4, §7), and
[D-2 diagnostic](docs/diagnostic-d2.md).

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
