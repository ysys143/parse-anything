# Task 6 — README + secret-safe docs check

File: `README.md`.

- Added "External Orchestration (offline)" section with the offline command, output description, and explicit "not an ODL runner or PDF renderer" caveat. Documented opt-in `--mode live` key contract. Added focused-test command for the slice.
- No new dependencies (`pyproject.toml` `dependencies = []` unchanged); no unrelated docs touched.

Evidence:
- `python3 scripts/check_no_secrets.py README.md docs .env.example src tests scripts` — secret scan passed.
- `python3 -m pytest` — 58 passed.
- Scope guard grep (fastapi/ollama/nemotron/glm/subprocess/pdf-render) over new modules: none found.
