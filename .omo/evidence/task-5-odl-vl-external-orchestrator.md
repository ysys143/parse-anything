# Task 5 — Sample orchestration fixture + golden

Files: `tests/fixtures/orchestrator/sample_document.json`, `expected_results.json`, `README.md`, `tests/test_orchestrator_fixture.py`.

- Sample document has exactly three pages: `simple_text`, `merged_table`, `chart_like_page`. `page_image` values are inert `fixtures://` strings (no real artifacts).
- Golden asserts provider, route reason, fallback, status, and a markdown fragment per page; derived from manifest family metadata.

Evidence:
- `python3 -m pytest tests/test_orchestrator_fixture.py` — pass (3 tests: three named pages, offline run matches golden, no private path/signed URL/`https://` in fixture files).
