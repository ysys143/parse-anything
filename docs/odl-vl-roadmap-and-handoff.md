# ODL-VL Roadmap and Handoff

## Current State

ODL-VL is an early parsing experiment for a deterministic parsing front with VLM/OCR providers. The repository has a completed common scaffold (provider configuration, routing, ledger, smoke checks, fixture metadata) and the external orchestrator slice. It doesn't claim production readiness.

The external orchestrator is implemented: it consumes ODL-like page JSON, routes each page through the deterministic, PaddleOCR official API, or Gemini direct path, normalizes outputs into the existing IR, and records a faithful per-page ledger. See [orchestrator architecture](orchestrator-architecture.md). It is not an ODL CLI execution stage.

The mandatory full PDF pipeline contract is now documented in [PDF pipeline requirements](pdf-pipeline-requirements.md). Processing-tier boundaries and domain adaptation are documented in [Processing tiers and domain adaptation](processing-tiers-and-adaptation.md). Current implementation covers only the page-level routing scaffold; rendering, deterministic extraction, orientation correction, processing-depth automation, page-spanning table assembly, numeric guards, human-review targeting, domain calibration tooling, and document-level outputs remain future work.

## Overall Roadmap

1. Completed foundation: PaddleOCR official API + Gemini direct common scaffold.
2. Completed: external orchestrator over ODL-like page JSON (offline default + opt-in live), not ODL CLI execution. See [orchestrator architecture](orchestrator-architecture.md).
3. Next: add PDF input rendering with a license-clean renderer and ODL/deterministic extraction so real text, bbox, table regions, and page images can feed the orchestrator.
4. Then: add orientation correction, processing-depth routing, DET/VLM/HUM escalation boundaries, page-spanning table assembly, numeric source gates, arithmetic invariant checks, and document-level output assembly.
5. Then: add domain adaptation tooling for measuring domain error rates, reviewing flagged cells/structures, capturing corrections, and comparing policy/provider changes.
6. Then: generate real fixtures and add golden scoring over the documented fixture families, including page-spanning tables and numeric guard cases.
7. Then: run a live provider bake-off across deterministic, PaddleOCR official API, Gemini direct, and privacy-safe alternatives where URL fetch is not acceptable.
8. Later: add deferred provider adapters only after the provider interface, ledger fields, guard fields, adaptation metrics, and fixture bake-off are stable.
9. Optional later layer: add FastAPI or another service interface only after the CLI/library path proves the contract.

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
