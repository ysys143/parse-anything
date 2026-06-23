# ODL-VL Roadmap and Handoff

## Current State

ODL-VL is an early parsing experiment for a deterministic-first PDF parsing pipeline with VLM/OCR escalation. The page-level external-orchestrator scaffold (ODL-like page JSON input) has been **removed and superseded**. A working PDF pipeline now exists under `src/odl_vl/pipeline/` (render, deterministic extraction, per-page processing, value-oracle + scan/quality guards, page-spanning tables, Markdown + ledger output, review/scorecard tooling). It doesn't claim production readiness.

Real-corpus measurement (F16/F17 in [measurement findings](measurement-findings.md)) redirected the architecture: **runtime per-page auto-routing is a false-positive gamble** (no deterministic structure detector is reliable across document types), so the target is **source-level diagnose-then-configure** with two configured modes (deterministic; deterministic-powered VLM) — see [Processing tiers and domain adaptation](processing-tiers-and-adaptation.md) §2.5–2.6/P7 and [PDF pipeline requirements](pdf-pipeline-requirements.md).

This target architecture is now **implemented** (R1–R4):

- **No runtime routing.** `decide_route` is demoted to a diagnostic-only signal; the run is mode-driven via `assemble.py`. `deterministic` = ODL structure/clean-text + pypdfium2 value-completeness backstop; `det_vlm` = + VLM reconciled, with the born-digital **value oracle** gating VLM numbers (R-M1). The mode is the lever — a missing key with `--mode det_vlm` is a loud error, never a silent downgrade.
- **Source diagnosis.** D-1 built-in VLM (`diagnose.py`, `scripts/diagnose_source.py`) measures deterministic-vs-VLM token divergence + scan fraction + (structure-aware-sampled) table/figure presence → recommends a mode with evidence. D-2 (`scripts/diagnose_prepare.py` + `docs/diagnostic-d2.md`) assembles a review bundle for a flagship agent in the oracle position. Both emit a `SourceProfile`, which is persisted and reusable (`--use-profile`).
- **Rich output.** `document.json` (loss-aware source of truth: content-hash id, provenance, pages, tables/figures with bbox + original labels), `tables/`, `assets/`, keyed `<out>/<source_id>/<document_id>/`. Original fig/table numbers come from ODL captions, backfilled from VLM-read captions in `det_vlm` (every entry `source`-tagged).
- 144 tests pass in an isolated `uv` env. CLI: `--mode`, `--diagnose`, `--use-profile`, `--source-id/--external-id/--ingested-from`.

## Overall Roadmap

1. Completed: provider scaffold (Gemini direct + PaddleOCR official API) + smoke CLI.
2. Completed: PDF pipeline slice — render, deterministic extraction (pypdfium2), per-page processing, value-oracle source-gate + scan legibility + input-quality guards, page-spanning table batching, Markdown + ledger output, review/scorecard tooling. The old JSON-input orchestrator was removed.
3. Measurement redirect (F16/F17): no deterministic structure detector is reliable across document types; `pypdfium2` vs `ODL` is role-based (pypdfium2 = value completeness + char bbox; ODL = structure + clean text). Runtime per-page auto-routing dropped in favor of source-level diagnose-then-configure.
4. **Completed (R1):** demoted `decide_route` to a diagnostic signal; mode-driven run with the two configured modes — **deterministic** (ODL + pypdfium2) and **det_vlm** (ODL + pypdfium2 + VLM reconciled, value oracle gating VLM numbers). CLI `--mode`.
5. **Completed (R2):** rich output contract — `document.json` (loss-aware), `tables/`, `assets/`, content-hash document ids + source/provenance metadata, original fig/table labels.
6. **Completed (R3–R4):** source-level diagnosis — D-1 built-in VLM (measured, structure-aware sampling) and D-2 flagship-agent review bundle/skill — producing a **SourceProfile** that is persisted and reusable; CLI `--diagnose` / `--use-profile`; VLM caption-label extraction in `det_vlm`.
7. **Next (not implemented):** run the diagnose-then-configure flow on real labeled corpora; calibrate per-domain thresholds; golden scoring via the scorecard tool; deeper ODL integration (page-spanning table merge wiring into `source_pages`; per-cell bbox).
8. Later: a derived SQLite index for cross-document queries (filesystem stays source of truth); deferred provider adapters and a service interface (e.g. FastAPI) only after the CLI/library path proves the contract.

## Completed Foundation

The completed foundation is PaddleOCR official API + Gemini direct common scaffold, config, providers, IR, router, ledger, smoke CLI, fixture metadata, README setup/test/smoke docs.

Completed pieces include:

- Python package scaffold under `src/odl_vl/`.
- Environment contract using `GEMINI_API_KEY`, `PADDLE_API_KEY`, `PADDLE_BASE_URL`, and optional `PADDLE_MODEL` by name only.
- Provider request builders and offline client seams for Gemini direct and PaddleOCR official API.
- Internal IR, route selection, and faithful ledger helpers.
- Smoke CLI for dry config checks and optional live checks.
- Metadata-only fixture manifest and golden schema for the initial eight fixture families.
- README setup, offline test, dry config, optional live smoke, and fixture documentation.
- Full target PDF pipeline requirements covering rendering, processing depth, complex/page-spanning tables, VLM input recipe, numeric guards, outputs, verification, licensing, and privacy constraints.
- Processing-tier and domain-adaptation requirements covering deterministic/VLM/human boundaries, escalation policy, residual human review, and calibration tooling.

## Implemented: External Orchestrator (REMOVED, superseded by the PDF pipeline)

> The JSON-input orchestrator (`orchestrator.py`, `orchestrator_input.py`, `router.py`, `ledger.py`, `scripts/odl_vl_orchestrate.py`) was a scaffold and has been **removed**. It is superseded by the PDF pipeline (`src/odl_vl/pipeline/`, `scripts/pdf_to_markdown.py`); see `pdf-pipeline-requirements.md` and `measurement-findings.md`. The shared provider layer and smoke CLI are retained. The description below is historical.

Built as a library + CLI slice that takes ODL-like page JSON as input. The input contract represents document id, page id/index, `first_pass_md`, `page_image`, fixture family, routing hints, and optional `intent_prompt`.

The orchestrator uses the existing router and provider seams, normalizes deterministic markdown, Gemini response text, and Paddle layout JSON into `NormalizedPage`, then writes a faithful ledger (secrets are kept out at the source plus a `.gitignore` on run artifacts, not by runtime redaction). Offline execution uses synthetic provider output by default; live provider behavior is opt-in and injectable. Each page runs exactly one routed provider (no cross-provider fallback). See [orchestrator architecture](orchestrator-architecture.md) for the module map and data flow.

## Scope Boundaries

In scope now:

- ODL-like JSON input contract.
- Injectable provider calls and fake transports for offline tests.
- Metadata-only orchestration fixtures.
- Faithful ledger entries for route, provider, model alias, status, latency, and cost estimate fields.
- CLI/library proof before any service layer.

Out of scope for the external orchestrator slice:

- ODL Java fork or `HybridRequest` changes.
- ODL CLI subprocess execution.
- PDF page rendering.
- Page orientation correction.
- Processing-depth automation.
- Complex/page-spanning table reconstruction.
- Numeric source gates and arithmetic invariant guards.
- Human-review targeting.
- Domain adaptation measurement/review/calibration tooling.
- Document-level Markdown/JSON assembly.
- Real generated PDF or image fixtures.
- FastAPI or other service layer.
- Ollama, GLM-OCR, NGC, or Nemotron provider adapters.
- Raw live provider bodies, signed URLs, API keys, tokens, private paths, or `.env` values in outputs, tests, docs, evidence, or ledgers.

## Verification Contract

Keep verification source-grounded and secret-safe: offline tests, syntax checks, dry config checks, and optional live smoke only when local environment names are present. The external orchestrator adds focused offline unit/CLI tests and a real CLI surface check against a sample ODL-like JSON file.

Final checks for the external orchestrator are package install, pytest, compileall, and the offline orchestration CLI command. Secrets are kept out of artifacts at the source (opaque error codes, non-secret metadata) plus a `.gitignore` on run artifacts; the ledger holds route/provider/status metadata without key-like values or signed URLs.

## Git/State Hygiene

Do not commit API keys, tokens, signed URLs, private paths, local `.env` values, provider response bodies, or downloaded live artifacts.

Keep `.omc/state/**` and `.omo/boulder.json` out of commits. Treat `.omo/plans/**` and `.omo/drafts/**` as planning state, and only change them when the task explicitly asks for plan maintenance.

Do not commit from this handoff task. Future implementation commits should only happen after explicit user approval.

## Start Command

```bash
$start-work odl-vl-external-orchestrator
```

## Source References

- `.omo/plans/odl-vl-parser.md`: completed common scaffold todos 1-6 and final verification.
- `.omo/plans/odl-vl-external-orchestrator.md`: the external orchestrator plan (implemented).
- `.omo/drafts/odl-vl-external-orchestrator.md`: decisions to consume ODL-like JSON, use injectable provider calls, keep fixtures metadata-only, and exclude ODL runner, PDF renderer, and provider expansion.
- `docs/vlm-provider-and-fixture-plan.md`: PaddleOCR official API + Gemini direct decision, environment variable names, routing architecture, fixture strategy, and deferred providers.
- `README.md`: current setup, offline test, dry config, optional smoke, and fixture docs for the common scaffold.
