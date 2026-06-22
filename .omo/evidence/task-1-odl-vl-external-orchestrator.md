# Task 1 — External orchestrator input contract

Files: `src/odl_vl/orchestrator_input.py`, `tests/test_orchestrator_input.py`.

- `DocumentInput`/`PageInput` dataclasses + `load_document_input`/`parse_document_input` (stdlib `json` only).
- Required page fields enforced: `page_id`, `page_index`, `first_pass_md`, `page_image`, `fixture_family`. Optional hints map to `RoutingTask` via `PageInput.routing_task()`.
- Malformed JSON, missing field, non-integer `page_index`, and empty `pages` raise clear `ValueError`.

Evidence:
- `python3 -m pytest tests/test_orchestrator_input.py` — pass (8 tests).
- `python3 -m compileall src tests` — pass.
- No provider/ODL/PDF calls in module.
