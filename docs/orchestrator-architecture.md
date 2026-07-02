# External Orchestrator — Architecture

> **REMOVED / HISTORICAL.** The page-level JSON-input orchestrator described below
> (`orchestrator.py`, `orchestrator_input.py`, `router.py`, `ledger.py`,
> `scripts/parse_anything_orchestrate.py`) has been **removed** and superseded by the PDF
> pipeline (`src/parse_anything/pipeline/`, `scripts/pdf_to_markdown.py`). Kept for history.
> The shared provider layer (`config`, `providers`, `paddle_jobs`, `normalizers`,
> `cli_support`) is retained. See `pdf-pipeline-requirements.md` and
> `measurement-findings.md` for current behavior.

Reference for the ODL-VL external orchestrator: the library + CLI that takes
ODL-like page JSON, routes each page to one provider, normalizes the output into
the internal IR, and records a per-page ledger.

**What it is:** a routing + normalization layer over three providers
(deterministic parser / PaddleOCR official API / Gemini direct), with an offline
default and an opt-in live mode.

**What it is not:** it does not execute ODL, render PDF pages, or generate
fixture artifacts. It consumes page JSON that some upstream step produces.

## Relationship to the Full PDF Contract

The mandatory full-pipeline contract lives in
[`pdf-pipeline-requirements.md`](pdf-pipeline-requirements.md), with
processing-tier boundaries and domain adaptation in
[`processing-tiers-and-adaptation.md`](processing-tiers-and-adaptation.md). This
orchestrator is a page-level scaffold for provider routing and normalization; it
does not yet satisfy the full contract.

Missing full-contract pieces include PDF input rendering with pypdfium2,
deterministic ODL extraction, page orientation correction, processing-depth
automation, page-spanning table assembly, multi-image VLM requests, numeric
source gates, arithmetic invariant checks, human-review targeting, domain
calibration tooling, asset manifests, and document-level Markdown/JSON assembly.

## Module map (`src/parse_anything/`)

| Module | Responsibility |
| --- | --- |
| `orchestrator_input.py` | Input contract: `DocumentInput` / `PageInput` and `load_document_input(path)`. Validates required fields; raises `ValueError` on malformed input. |
| `router.py` | `choose_route(task, family_metadata) -> RouteDecision(provider, reason)`. Picks exactly one provider per page. `EXPECTED_ROUTES = {deterministic_only, paddle_ocr, gemini_vlm, hybrid}`. |
| `ir.py` | Internal representation: `ProviderName` (deterministic/paddle/gemini), `NormalizedPage`, `VlmPassInput`. |
| `normalizers.py` | Provider output -> `NormalizedPage`: `normalize_deterministic`, `normalize_gemini`, `normalize_paddle`, plus `extract_gemini_text` / `try_decode_json`. |
| `orchestrator.py` | Engine: `orchestrate_document(document, config) -> list[PageResult]`. Per page: route -> run provider -> normalize -> append ledger event. |
| `ledger.py` | `LedgerEvent`, `event_payload` (faithful serializer), `append_ledger_event`. |
| `providers.py` | Live transport + request builders: `ProviderHttpClient`, `SafeTransport`, `UrllibTransport`, `build_gemini_generate_content_request`, `build_paddle_submit_request`, `build_paddle_poll_request`, `GeminiInlineImage`. |
| `paddle_jobs.py` | Paddle job lifecycle: `submit_job`, `poll_job`, `find_result_json_url` and anchored extraction helpers. |
| `config.py` | `Settings` / `load_settings` — read keys from `.env` / environment (live mode only). |
| `cli_support.py` | `Runtime` (injectable transport/stdout/environ/sleep) and `safe_client`. |

CLI entry points live in `scripts/`: `parse_anything_orchestrate.py` (the orchestrator,
offline + live) and `parse_anything_smoke.py` (single-provider dry-config / live smoke).

## Data flow

```
load_document_input(path)        # DocumentInput (tuple[PageInput, ...])
        |
   for each page:
        |
  choose_route(task, family)     # RouteDecision(provider, reason) -- one provider
        |
  run provider (offline | live)  # -> NormalizedPage
        |
  normalize -> NormalizedPage    # current: markdown (+ image_description, confidence, ...)
        |
  PageResult  ----------------->  results.jsonl, pages/page-<ordinal>-<slug>.md
        |
  LedgerEvent -> append_ledger_event -> ledger.jsonl
```

The orchestrator processes pages sequentially by default; `--max-workers N`
(N > 1) is an opt-in concurrency knob that preserves output order and serializes
ledger writes (see the note on provider rate limits in the README).

## Input contract

`PageInput` (one per page; `document_id` lives on `DocumentInput`):

| Field | Meaning |
| --- | --- |
| `page_id`, `page_index` | Page identity / order. |
| `first_pass_md` | Deterministic first-pass markdown for the page. |
| `page_image` | Reference to the page image (http(s) URL in live mode). |
| `fixture_family` | Selects expected routing + golden family. |
| `intent_prompt` (opt) | Per-page VLM prompt override. |
| `has_text_layer`, `needs_table_structure`, `needs_image_description`, `is_rotated_or_scan`, `is_low_quality_scan` | Routing hints mapped onto `RoutingTask`. |

This contract is intentionally narrower than the final PDF contract. Future
inputs must add deterministic JSON/bbox/table candidates, orientation metadata,
processing-depth signals, numeric oracle data, page-spanning table groups, and
privacy/provider constraints.

## Providers and modes

One provider runs per page (no cross-provider fallback this slice — a failed page
is reported failed, not silently re-run elsewhere).

- **deterministic**: `first_pass_md` -> `normalize_deterministic`. No network in
  either mode.
- **offline** (`--mode offline`, default): the Paddle/Gemini routes synthesize a
  placeholder response derived from the input and normalize it. Zero network,
  deterministic — this is what the test suite exercises.
- **live** (`--mode live`, opt-in): real authenticated calls.
  - Gemini: `x-goog-api-key` header; the page image is fetched and sent as
    base64 `inlineData` alongside the prompt, so the VLM actually sees the page.
  - Paddle: submit job -> poll until complete (or `paddle_poll_timeout`) ->
    fetch the completed layout result from the job's signed result URL.

## Outputs

Written under `--output-dir`:

- `results.jsonl` — per page: route, provider, status, `markdown_chars`,
  `image_description`, `confidence`, and a `markdown_file` pointer.
- `pages/page-<ordinal>-<slug>.md` — the normalized page markdown (the parsed
  document content); `<slug>` is derived from `page_id`.
- `ledger.jsonl` — per page: provider, model alias, route reason, latency,
  status, and non-secret metadata.

These are current slice outputs, not the final parser artifact set. The full
contract adds page JSON, `document.md`, `document.json`, logical table exports,
asset metadata, guard flags, source provenance, provider cost, and
processing-depth evidence.

## Contract verification

Correctness is verified as a response **contract**, independent of whether the
response is real or canned — so it needs no keys:

1. **Timeliness** — Paddle polling enforces a deadline; an overrun is
   `paddle_poll_timeout`.
2. **Conformance** — a response that does not match the expected shape becomes a
   failed page with a specific reason: `gemini_empty_text`,
   `paddle_result_not_json`, `paddle_empty_result`, `paddle_result_url_missing`,
   etc.

The offline + `FakeTransport` tests assert this contract end to end without any
network or credentials.

## Security posture

Secrets are kept out of artifacts by two controls — **not** by a runtime
scrubber or a commit-time scanner (both were intentionally removed):

1. **Source-no-contamination.** Provider errors surface as opaque codes
   (`gemini_http_429`, `paddle_result_0`, ...), never URL/key/body text. The
   `SafeTransport` wrapper converts every transport-layer exception
   (HTTP/URL/timeout, and malformed-URL `InvalidURL` / `ValueError`) into a
   status code, so no URL-bearing exception string can reach an error field.
   Keys live only in `repr=False` dataclass fields and request headers.
2. **`.gitignore`.** The run artifacts (`results.jsonl`, `ledger.jsonl`, `out/`)
   are git-ignored so a run is never committed.

The ledger is therefore written **faithfully** (no field-by-field redaction);
nothing secret reaches it to begin with.

## Tests

| Test | Covers |
| --- | --- |
| `test_orchestrator_input.py` | Input parsing + malformed-input errors. |
| `test_router.py` | Route selection + `EXPECTED_ROUTES` validation. |
| `test_normalizers.py` | deterministic / Gemini / Paddle / empty / malformed normalization. |
| `test_orchestrator.py` | Engine: routing, failure-to-failed, faithful ledger recording. |
| `test_orchestrate_cli.py` | CLI offline + live (via `FakeTransport`), output files, error codes. |
| `test_orchestrator_fixture.py` | Sample document golden. |
| `test_providers.py` / `test_paddle_jobs.py` | Transport contract (incl. `SafeTransport` exception funnel) + Paddle job extraction. |
