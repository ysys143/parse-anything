# Orchestrator sample fixtures

Metadata-only inputs for the external orchestration slice. No PDF or image
artifacts are generated or committed here; `page_image` values are inert
`fixtures://` reference strings only.

- `sample_document.json` — an ODL-like document with exactly three pages, one
  per routed provider path:
  - `simple_text` -> deterministic_only (deterministic route)
  - `merged_table` -> hybrid (Paddle route)
  - `chart_like_page` -> gemini_vlm (Gemini route)
- `expected_results.json` — golden expectations for an **offline** orchestration
  run: routed provider, route reason, and a markdown fragment that must appear in
  the normalized output.

The expected provider routes are derived from `tests/fixtures/manifest.json`
family metadata via `odl_vl.router.choose_route`. Offline mode uses synthetic
placeholder provider output, so no network call and no secret value is involved.
