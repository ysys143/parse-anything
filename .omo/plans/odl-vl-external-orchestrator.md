# odl-vl-external-orchestrator - Work Plan

## TL;DR (For humans)

**What you'll get:** A first external orchestrator slice that accepts ODL-like page JSON, routes each page to deterministic/Paddle/Gemini paths, normalizes outputs into the existing IR, and records redacted per-page ledger events.

**Why this approach:** The common Paddle/Gemini provider scaffold is complete, but the repo has no ODL runner or page renderer yet. This slice builds the orchestration contract and engine first, so later ODL subprocess/page-rendering work can plug into a tested seam.

**What it will NOT do:** It will not modify ODL Java code, run the ODL CLI, render PDFs, generate real fixture PDFs/images, add FastAPI, or implement Ollama/GLM/Nemotron.

**Effort:** Medium
**Risk:** Medium - provider output normalization and safe ledger handling are behavior-bearing, but tests can stay offline with fake transports.
**Decisions to sanity-check:** The orchestrator consumes ODL-like JSON input rather than running ODL itself. Paddle result URL content is parsed through an injectable fetch seam, but live downloaded artifacts are not committed.

Your next move: `$start-work odl-vl-external-orchestrator` to implement. Full execution detail follows below.

---

> TL;DR (machine): Implement external orchestration library + CLI over ODL-like JSON input; route via existing router, normalize deterministic/Paddle/Gemini outputs, write redacted ledger; no ODL runner/page renderer yet.

## Scope

### Must have

- Add an external orchestration input contract for page-level ODL-like data: document id, page id/index, `first_pass_md`, `page_image`, fixture family, routing hints, and optional `intent_prompt`.
- Add provider output normalization for deterministic markdown, Gemini response text, and Paddle layout parsing result JSON/JSONL into existing `NormalizedPage`.
- Add orchestration engine that uses existing `choose_route`, `ProviderHttpClient`, and ledger helpers to process pages and return normalized results.
- Add CLI `scripts/odl_vl_orchestrate.py` that reads an input JSON file, runs offline orchestration with deterministic/fake provider modes by default, and writes JSONL/markdown outputs plus redacted ledger.
- Add sample ODL-like input JSON and golden output expectations under `tests/fixtures/orchestrator/`.
- Add TDD tests for input validation, route selection, normalization, ledger redaction, CLI output files, and failure paths.
- Update README with the new offline orchestration command and make clear it is still not an ODL runner.

### Must NOT have (guardrails, anti-slop, scope boundaries)

- No ODL Java fork or `HybridRequest` changes.
- No ODL CLI subprocess runner.
- No PDF page renderer.
- No real generated PDF/image fixtures.
- No Ollama/GLM/Nemotron/FastAPI implementation.
- No provider secret values, signed result URLs, raw live provider bodies, or `.env` content in outputs, tests, docs, evidence, or ledger.
- No new runtime dependency beyond stdlib and existing project package setup.

## Verification strategy

> Zero human intervention - all verification is agent-executed.
- Test decision: TDD + `pytest` for offline unit/CLI tests.
- Evidence: `.omo/evidence/task-<N>-odl-vl-external-orchestrator.md` per task.
- Common automated commands:
  - `uv pip install -e ".[dev]"`
  - `python3 -m pytest`
  - `python3 -m compileall src tests scripts`
  - `python3 scripts/check_no_secrets.py README.md docs .env.example src tests scripts`
- Real-surface commands:
  - `python3 scripts/odl_vl_orchestrate.py --input tests/fixtures/orchestrator/sample_document.json --output-dir /tmp/odl-vl-orchestrator-qa --mode offline`
  - `python3 - <<'PY'` snippet loads `/tmp/odl-vl-orchestrator-qa/results.jsonl` and asserts expected page count/providers.

## Execution strategy

### Parallel execution waves

- Wave 1: Input contract/schema tests and provider normalization tests can run in parallel.
- Wave 2: Orchestrator engine depends on input contract and normalizers.
- Wave 3: CLI depends on orchestrator engine; sample fixture/golden can run in parallel with README update after CLI names stabilize.
- Final verification wave runs after all tasks.

### Dependency matrix

| Todo | Depends on | Blocks | Can parallelize with |
| --- | --- | --- | --- |
| 1 | none | 3, 4 | 2 |
| 2 | none | 3, 4 | 1 |
| 3 | 1, 2 | 4, 5 | none |
| 4 | 3 | 5, 6 | none |
| 5 | 4 | 6 | none |
| 6 | 4, 5 | Final verification | none |

## TODOs

- [ ] 1. Add external orchestrator input contract
  What to do / Must NOT do: Create `src/odl_vl/orchestrator_input.py` and `tests/test_orchestrator_input.py`. Define dataclasses/functions for `DocumentInput`, `PageInput`, and routing hints. Load/validate JSON from path using stdlib only. Required page fields: `page_id`, `page_index`, `first_pass_md`, `page_image`, `fixture_family`. Optional fields: `intent_prompt`, `has_text_layer`, `needs_table_structure`, `needs_image_description`, `is_rotated_or_scan`, `is_low_quality_scan`. Must not run providers, ODL, or PDF rendering.
  Parallelization: Wave 1 | Blocked by: none | Blocks: 3, 4
  References (executor has NO interview context - be exhaustive): `docs/parsing-engine-tracks-pdf.md:75`, `docs/parsing-engine-tracks-pdf.md:81`, `src/odl_vl/router.py:12`, `tests/fixtures/manifest.json:16`
  Acceptance criteria (agent-executable): `python3 -m pytest tests/test_orchestrator_input.py` passes; malformed JSON/missing field tests fail with clear `ValueError` messages; `python3 -m compileall src tests` passes.
  QA scenarios (name the exact tool + invocation): CLI/data surface: `python3 - <<'PY'` writes a temp document JSON with two pages, loads it through `odl_vl.orchestrator_input.load_document_input`, prints only `document_id`, page count, and fixture families; expected page count 2. Evidence `.omo/evidence/task-1-odl-vl-external-orchestrator.md`.
  Commit: N | feat(orchestrator): add input contract

- [ ] 2. Add provider output normalizers
  What to do / Must NOT do: Create `src/odl_vl/normalizers.py` and `tests/test_normalizers.py`. Implement deterministic markdown normalization, Gemini text response normalization, and Paddle JSON/JSONL layout parsing normalization into `NormalizedPage`. Paddle parser must handle a minimal result shape with `layoutParsingResults[].markdown.text`, optional `markdown.images`, `outputImages`, and page-level confidence if present. Must not fetch URLs or write files.
  Parallelization: Wave 1 | Blocked by: none | Blocks: 3, 4
  References (executor has NO interview context - be exhaustive): `src/odl_vl/ir.py:39`, `src/odl_vl/providers.py:120`, `docs/parsing-engine-tracks-pdf.md:26`, `docs/vlm-provider-and-fixture-plan.md:43`
  Acceptance criteria (agent-executable): `python3 -m pytest tests/test_normalizers.py` passes; tests cover deterministic, Gemini, Paddle success, empty Paddle result, and malformed provider JSON.
  QA scenarios (name the exact tool + invocation): Data surface: `python3 - <<'PY'` normalizes one fake Paddle result and one fake Gemini response and prints provider names plus markdown lengths only; expected providers `paddle`, `gemini`. Evidence `.omo/evidence/task-2-odl-vl-external-orchestrator.md`.
  Commit: N | feat(orchestrator): add provider output normalizers

- [ ] 3. Add orchestration engine and redacted per-page ledger
  What to do / Must NOT do: Create `src/odl_vl/orchestrator.py` and `tests/test_orchestrator.py`. Engine takes `DocumentInput`, fixture manifest metadata, provider callables/transports, and output ledger path. It routes each page with existing `choose_route`, uses deterministic normalization for deterministic route, and uses injected fake provider functions for Paddle/Gemini in tests. It returns normalized page results and appends redacted ledger events. Must not perform network by default.
  Parallelization: Wave 2 | Blocked by: 1, 2 | Blocks: 4, 5
  References (executor has NO interview context - be exhaustive): `src/odl_vl/router.py:29`, `src/odl_vl/ledger.py:47`, `src/odl_vl/providers.py:112`, `tests/fixtures/manifest.json:10`
  Acceptance criteria (agent-executable): `python3 -m pytest tests/test_orchestrator.py` passes; tests cover deterministic page, Paddle-routed page, Gemini-routed page, provider failure converted to failed page result, and no secret/signed URL leakage in ledger.
  QA scenarios (name the exact tool + invocation): Data surface: run a Python snippet with three in-memory pages (`simple_text`, `merged_table`, `chart_like_page`), fake providers, temp ledger path; assert providers `deterministic,paddle,gemini` and no token-like values in ledger. Evidence `.omo/evidence/task-3-odl-vl-external-orchestrator.md`.
  Commit: N | feat(orchestrator): add external orchestration engine

- [ ] 4. Add offline orchestration CLI
  What to do / Must NOT do: Create `scripts/odl_vl_orchestrate.py` and `tests/test_orchestrate_cli.py`. CLI supports `--input`, `--output-dir`, `--mode offline`, and optional `--intent-prompt`. Offline mode must use deterministic/fake provider outputs derived from input metadata so it never calls network. It writes `results.jsonl`, per-page markdown files, and `ledger.jsonl` to output dir. Must not print secrets, signed URLs, or raw provider bodies.
  Parallelization: Wave 3 | Blocked by: 3 | Blocks: 5, 6
  References (executor has NO interview context - be exhaustive): `scripts/odl_vl_smoke.py:117`, `src/odl_vl/orchestrator.py` after Todo 3, `tests/fixtures/manifest.json:16`
  Acceptance criteria (agent-executable): `python3 -m pytest tests/test_orchestrate_cli.py` passes; `python3 scripts/odl_vl_orchestrate.py --input tests/fixtures/orchestrator/sample_document.json --output-dir /tmp/odl-vl-orchestrator-qa --mode offline` exits 0 and writes expected files.
  QA scenarios (name the exact tool + invocation): CLI surface: remove `/tmp/odl-vl-orchestrator-qa`, run the CLI command above, then `python3 - <<'PY'` reads `results.jsonl` and asserts 3 pages and providers include deterministic, paddle, gemini; delete temp dir and record cleanup. Evidence `.omo/evidence/task-4-odl-vl-external-orchestrator.md`.
  Commit: N | feat(orchestrator): add offline CLI surface

- [ ] 5. Add sample orchestration fixture and golden expectations
  What to do / Must NOT do: Create `tests/fixtures/orchestrator/sample_document.json`, `tests/fixtures/orchestrator/expected_results.json`, `tests/fixtures/orchestrator/README.md`, and `tests/test_orchestrator_fixture.py`. Sample document must include exactly three pages: `simple_text`, `merged_table`, `chart_like_page`. It may reference synthetic image paths/URLs as inert strings only; no actual image/PDF artifacts. Golden expectations assert route/provider and key normalized markdown fragments.
  Parallelization: Wave 3 | Blocked by: 4 | Blocks: 6
  References (executor has NO interview context - be exhaustive): `tests/fixtures/manifest.json:17`, `tests/fixtures/manifest.json:73`, `tests/fixtures/manifest.json:129`, `tests/fixtures/golden_schema.json:16`
  Acceptance criteria (agent-executable): `python3 -m pytest tests/test_orchestrator_fixture.py` passes; fixture files contain no private paths, no signed URLs, no downloaded benchmark data.
  QA scenarios (name the exact tool + invocation): Data surface: Python snippet loads sample/golden, prints page count and expected providers only; expected page count 3. Evidence `.omo/evidence/task-5-odl-vl-external-orchestrator.md`.
  Commit: N | test(orchestrator): add sample orchestration fixture

- [ ] 6. Update README and run final secret-safe docs check
  What to do / Must NOT do: Update `README.md` with the offline external orchestration command and clarify this is not yet an ODL runner. Add no new dependencies. Update no unrelated docs. Run secret scan. Must not claim production readiness.
  Parallelization: Wave 4 | Blocked by: 4, 5 | Blocks: Final verification
  References (executor has NO interview context - be exhaustive): `README.md:51`, `docs/vlm-provider-and-fixture-plan.md:37`, `docs/parsing-engine-tracks-pdf.md:71`
  Acceptance criteria (agent-executable): `python3 scripts/check_no_secrets.py README.md docs .env.example src tests scripts` passes; README includes external orchestration offline command and scope caveat.
  QA scenarios (name the exact tool + invocation): CLI/docs surface: run README orchestration command exactly, confirm output dir contains `results.jsonl`, `ledger.jsonl`, and markdown files; cleanup temp dir. Evidence `.omo/evidence/task-6-odl-vl-external-orchestrator.md`.
  Commit: N | docs(orchestrator): document external orchestration slice

## Final verification wave

> Runs in parallel after ALL todos. ALL must APPROVE. Surface results and wait for the user's explicit okay before declaring complete.
- [ ] F1. Plan compliance audit
- [ ] F2. Code quality review
- [ ] F3. Real manual QA
- [ ] F4. Scope fidelity

## Commit strategy

Do not commit unless the user explicitly asks. If later requested, use one commit after final verification: `feat(orchestrator): add external orchestration slice`.

## Success criteria

- `uv pip install -e ".[dev]"` succeeds.
- `python3 -m pytest` succeeds.
- `python3 -m compileall src tests scripts` succeeds.
- `python3 scripts/check_no_secrets.py README.md docs .env.example src tests scripts` succeeds.
- `python3 scripts/odl_vl_orchestrate.py --input tests/fixtures/orchestrator/sample_document.json --output-dir /tmp/odl-vl-orchestrator-qa --mode offline` succeeds and writes results/ledger/markdown.
- Output ledger contains provider/model/route/status fields and no key-like or signed URL values.
- Scope fidelity review confirms no ODL runner, PDF renderer, FastAPI, Ollama/GLM/Nemotron, or ODL Java fork was implemented.
