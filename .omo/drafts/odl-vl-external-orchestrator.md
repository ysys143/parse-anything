---
slug: odl-vl-external-orchestrator
status: awaiting-approval
intent: clear
pending-action: execute .omo/plans/odl-vl-external-orchestrator.md
approach: Implement the first external orchestration slice on top of the completed Paddle/Gemini common scaffold.
---

# Draft: odl-vl-external-orchestrator

## Components (topology ledger)

| id | outcome | status | evidence path |
|---|---|---|---|
| input-contract | JSON document/page contract representing ODL-like local output plus page image refs and intent prompt. | active | `src/odl_vl/ir.py`, `docs/parsing-engine-tracks-pdf.md:75` |
| provider-normalizers | Convert deterministic text, Gemini text, and Paddle layout JSON/JSONL into `NormalizedPage`. | active | `src/odl_vl/ir.py`, `src/odl_vl/providers.py` |
| orchestrator-engine | Route each page, call provider seams, merge normalized output, append redacted ledger. | active | `src/odl_vl/router.py`, `src/odl_vl/ledger.py` |
| cli-surface | Offline CLI to run orchestration over a JSON input file; optional live mode may use existing keys. | active | `scripts/odl_vl_smoke.py`, `README.md` |
| fixture-contract | Use metadata-only fixture families to test routing and normalization; no real PDF generation in this slice. | active | `tests/fixtures/manifest.json` |

## Open assumptions (announced defaults)

| assumption | adopted default | rationale | reversible? |
|---|---|---|---|
| External orchestration should not run ODL itself yet. | Consume ODL-like JSON/page image references as input. | Existing docs say Track B starts from ODL local JSON, but no ODL runner exists in repo. This keeps the slice testable. | Yes |
| Provider calls should be injectable. | Unit tests use fake transports/results; live CLI remains optional. | Existing provider tests are offline and use stdlib seams. | Yes |
| Paddle result URL download is now in scope for orchestrator normalization, but only via injected/fake transport in tests. | Implement parsing of result JSON/JSONL shape without committing live downloaded outputs. | To get real Paddle markdown, the orchestrator eventually needs result content, but secrets/signed URLs must not be logged. | Yes |
| Fixture artifacts remain metadata-only. | Add orchestration sample JSON under tests, not generated PDFs/images. | Previous plan deferred actual fixture generation. | Yes |

## Findings (cited - path:lines)

1. Track B sequence is ODL local output -> triage signal -> page image + first pass md + dynamic prompt -> VLM -> merge + ledger. Evidence: `docs/parsing-engine-tracks-pdf.md:75`, `docs/parsing-engine-tracks-pdf.md:81`, `docs/parsing-engine-tracks-pdf.md:82`.
2. Existing shared VLM contract is `page_image`, optional `first_pass_md`, optional `intent_prompt` -> md/json/table/image description/confidence. Evidence: `docs/parsing-engine-tracks-pdf.md:26`.
3. Completed common scaffold already provides config, Paddle/Gemini provider request builders, IR, router, redacted ledger, smoke CLI, and fixture manifest. Evidence: `.omo/plans/odl-vl-parser.md:80`, `.omo/plans/odl-vl-parser.md:88`, `.omo/plans/odl-vl-parser.md:96`, `.omo/plans/odl-vl-parser.md:104`, `.omo/plans/odl-vl-parser.md:112`.
4. Initial provider scope remains PaddleOCR official API + Gemini direct; Ollama/GLM/Nemotron are deferred. Evidence: `docs/vlm-provider-and-fixture-plan.md:8`, `docs/vlm-provider-and-fixture-plan.md:107`.

## Decisions (with rationale)

1. First external orchestrator slice implements library + CLI over a JSON input contract, not an ODL subprocess runner.
2. The orchestrator must support deterministic-only, Paddle, and Gemini routes using existing `choose_route` and fixture metadata.
3. Provider lifecycle code must be injectable and testable without network. Optional live commands are allowed only as smoke checks.
4. Normalization accepts minimal provider response shapes: deterministic first pass markdown, Gemini text response, and Paddle JSON/JSONL layout parsing results.
5. Ledger writes go through existing redaction helpers and must never include API keys, signed URLs, or raw provider bodies.

## Scope IN

- Input contract for ODL-like pages: page id/index, first-pass markdown, page image URL/path, fixture family, routing hints, and optional intent prompt.
- External orchestration engine that routes pages, calls deterministic/provider adapters, normalizes outputs, and writes per-page ledger.
- Offline CLI to run the orchestrator against a sample JSON input and write normalized JSONL/markdown outputs to a user-specified directory.
- Unit tests and real CLI-surface tests using fake provider responses.
- Optional live smoke path only if it can reuse existing safe redaction and avoid writing provider result files by default.

## Scope OUT (Must NOT have)

- No ODL Java fork, `HybridRequest` modification, or ODL source patching.
- No ODL CLI subprocess runner in this slice.
- No PDF page renderer in this slice.
- No generated PDF/image fixture artifacts in this slice.
- No Ollama/GLM/Nemotron/FastAPI implementation.
- No committed API keys, signed URLs, raw live provider response bodies, or `.env` contents.

## Open questions

None blocking. Adopted defaults above are reversible in later plans.

## Approval gate
status: awaiting-approval

This plan is ready for `$start-work odl-vl-external-orchestrator`.
