# Task 2 — Provider output normalizers

Files: `src/odl_vl/normalizers.py`, `tests/test_normalizers.py`.

- `normalize_deterministic`, `normalize_gemini`, `normalize_paddle` -> `NormalizedPage`.
- `extract_gemini_text` walks generateContent payload; `decode_json_body` raises `ValueError` on malformed JSON.
- Paddle parser handles `layoutParsingResults[].markdown.text`, optional `markdown.images`/`outputImages`, and entry/top-level confidence; empty result and non-mapping input return empty markdown defensively.

Evidence:
- `python3 -m pytest tests/test_normalizers.py` — pass (7 tests: deterministic, gemini, gemini-extract, paddle-success, paddle-empty, paddle-non-mapping, malformed-json).
- No URL fetch or file write in module.
