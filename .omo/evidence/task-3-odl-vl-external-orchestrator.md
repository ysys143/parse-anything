# Task 3 — Orchestration engine + redacted per-page ledger

Files: `src/odl_vl/orchestrator.py`, `tests/test_orchestrator.py`.

- `orchestrate_document(document, config)` routes each page via `choose_route`, runs deterministic default or injected Paddle/Gemini callables, returns `PageResult` list, appends redacted `LedgerEvent` via `append_ledger_event`.
- Provider exceptions become `status="failed"` page results without aborting the run.
- Injectable `clock` gives deterministic latency in tests.

Evidence:
- `python3 -m pytest tests/test_orchestrator.py` — pass (4 tests: three-provider route incl. merged_table hybrid->paddle fallback=True; provider failure; ledger redaction of api_key/signed URL/long token; non-negative latency).
- Ledger assertion: no `api_key`, no `X-Amz-Signature`, no 40+ char token in output.
