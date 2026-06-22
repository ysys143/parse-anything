# Task 4 — Offline CLI + opt-in live mode

Files: `scripts/odl_vl_orchestrate.py`, `tests/test_orchestrate_cli.py`.

- `Runtime`-injected CLI (transport/stdout/environ/sleep) mirroring smoke CLI.
- Flags: `--input`, `--output-dir`, `--mode {offline,live}` (default offline), `--manifest`, `--intent-prompt`.
- Offline: synthetic placeholder Paddle/Gemini output, no network. Live: real calls via `ProviderHttpClient` + existing request builders + smoke-style poll/extract; missing keys -> failed page (no secret leak).
- Outputs: `results.jsonl`, `pages/*.md`, `ledger.jsonl`.

Evidence:
- `python3 -m pytest tests/test_orchestrate_cli.py` — pass (4 tests: offline files, offline ledger no-secret, live via FakeTransport routes paddle+gemini, live missing-keys fails non-deterministic pages while deterministic page stays ok).
- Real run: `odl_vl_orchestrate.py --input tests/fixtures/orchestrator/sample_document.json --output-dir /tmp/odl-vl-orchestrator-qa --mode offline` -> exit 0, 3 pages, providers deterministic/paddle/gemini, ledger secret/url grep = 0. Temp dir cleaned.

## Live verification (real provider calls, 2026-06-22)

Ran `--mode live` against real Gemini and PaddleOCR official API with local `.env` keys.

First real run surfaced two bugs the offline FakeTransport tests had masked:
1. Gemini live failed `HTTPError`: the shared `build_gemini_generate_content_request` sets `Authorization: Bearer <key>`, which Google rejects for API keys. Fixed by sending the `x-goog-api-key` header (mirrors the smoke CLI override).
2. Paddle live returned `status=ok` but empty markdown: the assumption that the poll completion contains inline `result.layoutParsingResults` was false. Real shape: completion `data.resultUrl.jsonUrl` is a signed URL; the layout JSON (`result.layoutParsingResults[].markdown.text`) lives behind it. Fixed by fetching the signed URL through the same transport and normalizing the fetched doc; the signed URL/raw body are never logged.

Second real run after fixes: exit 0, 3/3 ok.
- Gemini -> real response `ok` (prompt "Return exactly: ok").
- Paddle -> 7591-byte real OCR markdown fetched from the signed result URL (demo image).
- Deterministic -> local markdown.
- Ledger grep for `api_key|x-amz|x-goog-signature|jsonUrl|token=|signed` = 0; repo secret scan still passes. Temp artifacts cleaned.

Live test coverage added: `test_live_cli_calls_providers_through_transport` now drives submit -> poll(done, signed `jsonUrl`) -> signed-URL fetch -> gemini via FakeTransport and asserts the signed URL does not leak to the ledger.
