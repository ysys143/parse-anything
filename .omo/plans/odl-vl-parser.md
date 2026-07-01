# odl-vl-parser - Work Plan

## TL;DR (For humans)

**What you'll get:** PaddleOCR 공식 API와 Gemini direct를 같은 내부 라우터 계약으로 호출할 수 있는 Python 스캐폴드, 비밀값 없는 환경 설정 계약, 그리고 변별력 있는 fixture/golden-set 설계 골격.

**Why this approach:** 이번 세션에서 PaddleOCR-VL-1.6 공식 API job 완료와 Gemini 호출이 실제로 통과했으므로, 초기 개발은 두 provider만 고정한다. Ollama/GLM/Nemotron은 접근성/구독/범위 이슈가 있어 후순위로 둔다.

**What it will NOT do:** 실제 API key를 커밋하지 않는다. ODL Java fork를 구현하지 않는다. 대량 공개 벤치 데이터를 repo에 복사하지 않는다. Ollama/GLM/Nemotron adapter를 초기 범위에 넣지 않는다.

**Effort:** Medium
**Risk:** Medium - 새 Python package와 provider 계약을 만들지만 외부 provider live smoke는 네트워크/API 상태에 의존한다.
**Decisions to sanity-check:** Runtime dependency를 최소화해 stdlib HTTP client로 시작한다. FastAPI 서버는 첫 슬라이스에서 제외하고 router/library + live-smoke CLI만 만든다. Fixture는 synthetic manifest/golden schema부터 고정하고 실제 PDF 생성기는 다음 wave로 둔다.

Your next move: `$start-work odl-vl-parser`로 실행한다. Full execution detail follows below.

---

> TL;DR (machine): Medium risk; implement Paddle+Gemini Python router/config/client scaffold, fixture manifest/golden schema, offline tests, optional live smoke with no secrets committed.

## Scope

### Must have

- Create a Python package under `src/odl_vl/` with config, provider payload/client helpers, internal IR dataclasses, provider routing, and ledger event helpers.
- Add `.env.example` using only placeholder values for `GEMINI_API_KEY`, `PADDLE_API_KEY`, `PADDLE_BASE_URL`, and optional `PADDLE_MODEL`.
- Add deterministic offline tests under `tests/` for config alias parsing, provider selection, request payload construction, IR normalization, and ledger redaction.
- Add a live smoke CLI that can verify Gemini and PaddleOCR only when local `.env`/shell keys exist; it must never print key values.
- Add fixture planning artifacts: generated fixture manifest JSON and golden schema docs for the 8 fixture families recorded in `docs/vlm-provider-and-fixture-plan.md`.
- Update README with setup/test/live-smoke commands and link to the provider/fixture decision doc.

### Must NOT have (guardrails, anti-slop, scope boundaries)

- No committed API keys, tokens, result URLs containing signed credentials, or `.env` contents.
- No Ollama/GLM/Nemotron provider implementation in this slice.
- No FastAPI/web server implementation in this slice. The first slice is library + CLI smoke only.
- No real PDF fixture generation yet; record manifest/golden schema only. Actual generated PDF files are a later task.
- No weakening of the documented Track A limitation: unmodified ODL hybrid protocol does not pass first-pass markdown or prompt to backend.
- No dependency on `requests`; use Python stdlib HTTP for runtime code unless a later approved plan changes it.

## Verification strategy

> Zero human intervention - all verification is agent-executed.
- Test decision: TDD + `pytest` for offline unit tests.
- Evidence: `.omo/evidence/task-<N>-odl-vl-parser.md` per task.
- Common automated commands:
  - `uv pip install -e ".[dev]"`
  - `python3 -m pytest`
  - `python3 -m compileall src tests scripts`
  - `python3 scripts/odl_vl_smoke.py --provider gemini --dry-config`
  - `python3 scripts/odl_vl_smoke.py --provider paddle --dry-config`
- Optional live commands only when local env has keys:
  - `python3 scripts/odl_vl_smoke.py --provider gemini --live`
  - `python3 scripts/odl_vl_smoke.py --provider paddle --live --demo-url https://paddle-model-ecology.bj.bcebos.com/paddlex/imgs/demo_image/paddleocr_vl_demo.png`
- Secret scan command:
  - `python3 scripts/check_no_secrets.py README.md docs .env.example src tests scripts`

## Execution strategy

### Parallel execution waves

- Wave 1: Project/package scaffold and config tests can run in parallel with fixture manifest/schema docs.
- Wave 2: Provider payload/client helpers depend on config scaffold; router/IR depends on provider helpers.
- Wave 3: Live smoke CLI depends on provider helpers and router; README/docs update depends on command names stabilizing.
- Final verification wave runs after all tasks.

### Dependency matrix

| Todo | Depends on | Blocks | Can parallelize with |
| --- | --- | --- | --- |
| 1 | none | 2, 3, 4 | 5 |
| 2 | 1 | 3, 4 | none |
| 3 | 2 | 4, 6 | none |
| 4 | 3 | 6 | none |
| 5 | none | 6 | 1 |
| 6 | 4, 5 | Final verification | none |

## TODOs

- [x] 1. Bootstrap Python package and environment contract
  What to do / Must NOT do: Create `pyproject.toml`, `.env.example`, `src/odl_vl/__init__.py`, `src/odl_vl/config.py`, and `tests/test_config.py`. Implement config loading from shell plus optional `.env`, using canonical names `GEMINI_API_KEY`, `PADDLE_API_KEY`, `PADDLE_BASE_URL`, optional `PADDLE_MODEL`. Support aliases only for already observed names if needed: `PADDLEOCR_API_KEY` and `PADDLEOCR_BASE_URL` as fallbacks. Must not read or print secret values in tests or docs. Runtime code must use stdlib only.
  Parallelization: Wave 1 | Blocked by: none | Blocks: 2, 3, 4
  References (executor has NO interview context - be exhaustive): `docs/vlm-provider-and-fixture-plan.md:15`, `docs/vlm-provider-and-fixture-plan.md:28`, `.gitignore:1`
  Acceptance criteria (agent-executable): `python3 -m pytest tests/test_config.py` passes; `.env.example` contains placeholders only; `python3 -m compileall src tests` passes.
  QA scenarios (name the exact tool + invocation): CLI surface: `python3 - <<'PY'` imports `odl_vl.config`, loads a temporary `.env` with placeholder test values, prints only provider presence booleans, and verifies no value substring is printed. Evidence `.omo/evidence/task-1-odl-vl-parser.md`.
  Commit: N | feat(config): add Paddle/Gemini env contract

- [x] 2. Add provider request builders and offline client seams
  What to do / Must NOT do: Create `src/odl_vl/providers.py` and `tests/test_providers.py`. Implement typed request builders for Gemini `generateContent` and PaddleOCR official `/api/v2/ocr/jobs` submit/poll URLs. Add small transport seam so tests can run without network. Must not perform live network calls in unit tests. Must not include real key values.
  Parallelization: Wave 2 | Blocked by: 1 | Blocks: 3, 4
  References (executor has NO interview context - be exhaustive): `docs/vlm-provider-and-fixture-plan.md:8`, `docs/vlm-provider-and-fixture-plan.md:32`, `docs/vlm-provider-and-fixture-plan.md:33`
  Acceptance criteria (agent-executable): `python3 -m pytest tests/test_providers.py` passes and asserts Paddle model default is `PaddleOCR-VL-1.6`, Gemini default is `gemini-3.1-flash-lite`, Authorization headers are constructed but never logged.
  QA scenarios (name the exact tool + invocation): CLI surface: run a Python snippet that builds one Gemini request and one Paddle submit request using fake keys, serializes only URL host/path and model names, and confirms no fake secret appears in stdout. Evidence `.omo/evidence/task-2-odl-vl-parser.md`.
  Commit: N | feat(providers): add Paddle and Gemini provider seams

- [x] 3. Add internal IR, routing policy, and ledger redaction helpers
  What to do / Must NOT do: Create `src/odl_vl/ir.py`, `src/odl_vl/router.py`, `src/odl_vl/ledger.py`, and tests `tests/test_router.py`, `tests/test_ledger.py`. Router chooses `deterministic`, `paddle`, or `gemini` from task hints and fixture family metadata. Ledger events include provider, model alias, route reason, latency, status, fallback, and cost estimate fields, but redact secrets and omit raw signed URLs.
  Parallelization: Wave 2 | Blocked by: 2 | Blocks: 4, 6
  References (executor has NO interview context - be exhaustive): `docs/vlm-provider-and-fixture-plan.md:37`, `docs/vlm-provider-and-fixture-plan.md:41`, `docs/vlm-provider-and-fixture-plan.md:47`, `docs/parsing-engine-tracks-pdf.md:26`
  Acceptance criteria (agent-executable): `python3 -m pytest tests/test_router.py tests/test_ledger.py` passes; tests cover all three routes and assert long token-like strings are redacted.
  QA scenarios (name the exact tool + invocation): CLI surface: run a Python snippet that routes `simple_text`, `merged_table`, and `chart_like_page`, writes JSONL ledger to a temp file, then asserts no `API_KEY`, `TOKEN`, or 32+ hex token appears. Evidence `.omo/evidence/task-3-odl-vl-parser.md`.
  Commit: N | feat(router): add IR routing and redacted ledger

- [x] 4. Add live smoke CLI for Gemini and PaddleOCR
  What to do / Must NOT do: Create `scripts/odl_vl_smoke.py` and `tests/test_smoke_cli.py`. CLI supports `--provider gemini|paddle`, `--dry-config`, and `--live`. Dry-config only reports presence/absence and selected model/base URL host without values. Live Gemini sends a minimal `Return exactly: ok` request. Live Paddle submits the public Paddle demo image URL and polls until done or timeout. Must not download result files in this slice. Must not print keys, signed URLs, full response bodies, or `.env` values.
  Parallelization: Wave 3 | Blocked by: 3 | Blocks: 6
  References (executor has NO interview context - be exhaustive): `docs/vlm-provider-and-fixture-plan.md:28`, `docs/vlm-provider-and-fixture-plan.md:32`, `docs/vlm-provider-and-fixture-plan.md:33`
  Acceptance criteria (agent-executable): `python3 -m pytest tests/test_smoke_cli.py` passes; `python3 scripts/odl_vl_smoke.py --provider gemini --dry-config` exits 0; `python3 scripts/odl_vl_smoke.py --provider paddle --dry-config` exits 0.
  QA scenarios (name the exact tool + invocation): CLI surface: with current local `.env`, run `python3 scripts/odl_vl_smoke.py --provider gemini --live` and `python3 scripts/odl_vl_smoke.py --provider paddle --live --demo-url https://paddle-model-ecology.bj.bcebos.com/paddlex/imgs/demo_image/paddleocr_vl_demo.png`; expected output includes pass/fail status and no secret values. Evidence `.omo/evidence/task-4-odl-vl-parser.md`.
  Commit: N | feat(smoke): add Paddle and Gemini live checks

- [x] 5. Add fixture manifest and golden schema docs
  What to do / Must NOT do: Create `tests/fixtures/manifest.json`, `tests/fixtures/golden_schema.json`, `tests/fixtures/README.md`, and `tests/test_fixture_manifest.py`. Manifest must list the 8 fixture families from `docs/vlm-provider-and-fixture-plan.md` with expected challenge, expected route, and discriminative metric. It must not include private document paths, downloaded benchmark files, or generated PDFs yet.
  Parallelization: Wave 1 | Blocked by: none | Blocks: 6
  References (executor has NO interview context - be exhaustive): `docs/vlm-provider-and-fixture-plan.md:53`, `docs/vlm-provider-and-fixture-plan.md:60`, `docs/vlm-provider-and-fixture-plan.md:75`, `docs/vlm-provider-and-fixture-plan.md:85`
  Acceptance criteria (agent-executable): `python3 -m pytest tests/test_fixture_manifest.py` passes; manifest contains exactly the 8 initial families; each family has `expected_route`, `primary_metric`, and `mutation_strategy`.
  QA scenarios (name the exact tool + invocation): Data surface: run a Python snippet that loads manifest/golden schema and prints only family count, route distribution, and missing-field list; expected missing-field list is empty. Evidence `.omo/evidence/task-5-odl-vl-parser.md`.
  Commit: N | test(fixtures): add fixture manifest contract

- [x] 6. Update README and add secret-scan utility
  What to do / Must NOT do: Update `README.md` with setup commands, offline test commands, dry-config commands, and optional live smoke commands. Create `scripts/check_no_secrets.py` with conservative regex checks for Google API keys, HF tokens, 32+ hex tokens, and assigned secret-looking values in tracked docs/code. Must not include real key examples. Must not claim production readiness.
  Parallelization: Wave 4 | Blocked by: 4, 5 | Blocks: Final verification
  References (executor has NO interview context - be exhaustive): `README.md:1`, `docs/vlm-provider-and-fixture-plan.md:3`, `docs/vlm-provider-and-fixture-plan.md:15`, `docs/vlm-provider-and-fixture-plan.md:94`
  Acceptance criteria (agent-executable): `python3 scripts/check_no_secrets.py README.md docs .env.example src tests scripts` exits 0; README includes provider decision, install/test commands, dry-config commands, optional live commands, and fixture plan link.
  QA scenarios (name the exact tool + invocation): CLI surface: intentionally create a temp file under `/tmp` with a fake token-like string, run `python3 scripts/check_no_secrets.py /tmp/<file>`, expect non-zero; then delete temp file and run the normal repo scan, expect zero. Evidence `.omo/evidence/task-6-odl-vl-parser.md`.
  Commit: N | docs(setup): document Paddle and Gemini development workflow

## Final verification wave

> Runs in parallel after ALL todos. ALL must APPROVE. Surface results and wait for the user's explicit okay before declaring complete.
- [x] F1. Plan compliance audit: independent reviewer checks every Must have/Must NOT have against diff and ledger evidence.
- [x] F2. Code quality review: independent reviewer checks type clarity, no secret logging, no unnecessary dependencies, and no overbroad scope.
- [x] F3. Real manual QA: agent executes offline tests, compileall, dry-config commands, optional live smoke if env keys are present, and records outputs with secrets redacted.
- [x] F4. Scope fidelity: independent reviewer verifies Ollama/GLM/Nemotron/FastAPI/ODL fork/real PDF generation were not implemented in this slice.

## Commit strategy

Do not commit unless the user explicitly asks. If later requested, use one commit after final verification: `feat(parser): add Paddle and Gemini routing scaffold`.

## Success criteria

- `uv pip install -e ".[dev]"` succeeds.
- `python3 -m pytest` succeeds.
- `python3 -m compileall src tests scripts` succeeds.
- `python3 scripts/check_no_secrets.py README.md docs .env.example src tests scripts` succeeds.
- Dry-config commands for Gemini and Paddle exit 0 and print no secret values.
- Optional live smoke commands pass when local keys are present; if external APIs fail, the failure is reported as provider/network/auth specific without leaking response bodies or secrets.
- Fixture manifest covers exactly the 8 initial families and includes enough metadata to drive future fixture generation and scoring.
