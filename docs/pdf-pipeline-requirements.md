# PDF Pipeline Requirements

> Status: Mandatory goal contract. This is not a declaration that the current implementation is complete, but the set of PDF parsing pipeline requirements that ODL-VL must satisfy.
> Scope: An end-to-end pipeline that converts complex PDFs into Markdown, structure-preserving JSON, table/image assets, combined output, and a ledger.
> Operational boundary: The processing tier and domain adaptation requirements are governed by `.design/processing-tiers-and-adaptation.md`.

## 1. Scope and Non-Goals

This document is a goal contract that is broader than the current external orchestrator slice. The current implementation is a scaffold that receives ODL-like page JSON, routes to a provider, and writes per-page markdown/ledger. The final pipeline must cover everything from PDF input to rendering, deterministic extraction, processing-depth decisioning, VLM escalation, separation of items for human review, document-level merging, and a verification ledger.

The VLM is not the source of truth for numeric fidelity. The VLM is responsible for structure, layout, description, and filling in missing visual context; for born-digital numbers and text, the deterministic extraction result takes precedence.

## 2. Mandatory Requirements

1. Page orientation detection and correction are mandatory. Rotation, skew, and reading order in multi-column documents must be reflected in downstream markdown/json/table assembly.
2. Complex tables, merged cells, nested headers, and unit rows must not be handled by text heuristics alone. ODL's semantic table elements, row/column/cell bboxes, or an equivalent structural extraction is required.
3. Processing depth (deterministic / VLM) follows **a profile determined by per-source diagnosis, not runtime per-page auto-decisioning** (§3.4, processing tiers P7/§2.5). The set of deterministic triggers is an input signal to that diagnosis — not a fuzzy score.
4. Tables that span pages are recognized as a single logical table and reconstructed.
5. VLM input includes the deterministic parsing data, the page image, orientation correction information, and a custom prompt together. Page-spanning tables or images must automatically become multi-image input.
6. Output provides both per-page markdown/json and combined document markdown/json. The JSON must preserve tables, cells, bboxes, page references, confidence, and guard flags.
7. The ledger records per-page route, provider, cost, latency, guard flags, confidence, and escalation reason.

## 3. Input and Rendering Pipeline

1. PDF input is rendered to page images. The default renderer prefers the license-clean pypdfium2 family and must support high-DPI rendering.
2. Deterministic extraction produces text, bboxes, reading-order candidates, table regions, and semantic table elements. Exact numbers and structure of born-digital documents are preserved by this stage.
3. The scan vs. born-digital decision uses the pdf-inspector classify result together with the text character count.
4. **Processing depth is not auto-decided per page at runtime** (because deterministic structure detectors misfire differently across document types — `.design/measurement-findings.md` F16). Instead, the signals below are used as input to a **per-source diagnosis** (`.design/processing-tiers-and-adaptation.md` §2.5), which determines that source's **execution mode, risk hotspots, and applied guards**.
   - Scanned, or absence of a text layer
   - Semantic description of figures, charts, or diagrams needed
   - Broken encoding, CID/ToUnicode issues, abnormal glyphs
   - Arithmetic invariant failure
   - Incomplete deterministic table/reading-order/bbox
   - Low quality, rotation, skew, uncertain orientation
5. **Execution follows the mode specified by the source profile** (predictable, no runtime routing). There are two modes (processing tiers §2.6): **deterministic mode** (ODL + pypdfium2 combined) or **deterministic-powered VLM mode** (running ODL + pypdfium2 + VLM *both/all three* and reconciling — no routing gaps). Modes, thresholds, and guards are calibrated by diagnosis against the actual corpus/golden set. The DET/VLM/HUM tier boundaries and the domain adaptation tooling follow `.design/processing-tiers-and-adaptation.md`.

## 4. Table Policy

Complex tables are handled in two stages.

1. The deterministic stage collects table regions, rows, columns, cells, bboxes, and text tokens. **Role separation** (`.design/measurement-findings.md` F16/F17): *structure* (grid/merges/headers) is a candidate from **ODL** (or pdf-inspector) — but *not authoritative* (both are document-dependent and misfire). *Values and cell text* are authoritative from **pypdfium2** (completeness: ODL may drop real numbers, so pypdfium2 backstops and flags). That is, the ODL table grid is filled with pypdfium2 text/values.
2. The VLM stage (deterministic-powered VLM mode) augments merged-cell structure, header hierarchy, visual grouping, and continuation status, and reconciles with the deterministic result (ODL + pypdfium2) (processing tiers §2.6, R-M1: structure = VLM/ODL, values = pypdfium2 + value oracle).

Page-spanning tables are recognized by the following rules.

1. Compare the table bbox column coordinates, column count, header or continuation caption, and y-position pattern across consecutive pages.
2. When continuity is high, send those pages as a single multi-image VLM request.
3. Attach the merged logical table to the starting page. Leave a folded reference on continuation pages and do not create duplicate tables.
4. Tables of three or more pages are split into overlapping chunks. Each chunk is sent with adjacent pages overlapped, and chunk results are merged by table id and column signature.
5. After merging, the JSON must preserve provenance such as `source_pages`, `source_regions`, `continued_from`, `continued_to`, `cells[].bbox`, and `cells[].source_text`.

## 5. VLM Call Recipe

The deterministic-powered VLM mode **reconciles all three sources — ODL + pypdfium2 + VLM — as input** (no routing). A VLM request includes the following inputs.

- Deterministic text/structure candidates: **ODL** (table grid, reading order, clean text) + **pypdfium2** (value completeness, char bbox)
- Deterministic JSON candidates: text tokens, bboxes, table regions, cell candidates, source page ids
- Orientation detection/correction results: rotation, skew, corrected image metadata
- Page image: single page or automatic multi-image
- Custom prompt: structured instructions per document/user objective
- Guard policy: numeric oracle, source gate, arithmetic invariant

VLM output is treated as a structural augmentation result. Numeric values are trusted only when matched to deterministic source text. If the VLM produces a number that is not in the source, it is rejected or flagged.

## 6. Numeric Accuracy and Hallucination Guards

Born-digital documents inject a numeric oracle. Values extracted from the text layer are placed into cell candidates so that the VLM does not newly read or guess numbers.

The mandatory guards are as follows.

1. Source gate: If a VLM output number is not in the deterministic source text, reject or flag it.
2. Arithmetic invariant: Verify per-document invariants such as subtotal = sum of lines, VAT = subtotal x 1.1, quantity x unit price = total.
3. Escalation gate: If the deterministic result breaks an arithmetic invariant, send it to VLM/OCR or human review.
4. Scan guard: For scanned documents without an oracle, apply prompt abstention, a dual-provider pass, and input-quality gating together.
5. Human review: Leave only the residual risk cells from a scan as human-review targets. Do not promise fully automatic numeric trust.

The verification goals are blocking hallucinated numbers, a low false-reject rate, and separating the confidence of flagged versus unflagged cells.

## 7. Output Contract

The final deliverables include at minimum the following.

- `pages/`: per-page markdown
- `document.md`: combined document markdown
- `document.json`: loss-aware structural JSON
- `tables/`: per-logical-table JSON/HTML/Markdown view
- `assets/`: extracted or rendered image/table crop metadata
- `results.jsonl`: per-page route/provider/status/output pointers
- `ledger.jsonl`: route, provider, cost, latency, guard flags, confidence, escalation reason

Markdown is a human-readable view. JSON is the source of truth and must preserve element id, page id, bbox, table/cell hierarchy, source text, asset pointer, and continuation relations.

- **Source-level metadata (addition).** In addition to page metadata, `document.json` records **source identification, profile, and diagnostic provenance** (source id, the applied source profile and execution mode, the diagnostic grade D-1/D-2 and timestamp) (processing tiers §2.5). It must be possible to trace that documents from the same source were processed with the same profile.
- **Mode mapping.** Both execution modes produce this contract — the structure of `tables/` and `assets/` comes from ODL, values/`cells[].source_text` from pypdfium2, and the deterministic-powered VLM mode reconciles in the VLM augmentation (with provenance labeling the source).
- **Current implementation gap.** `src/parse_anything/pipeline/output.py` currently writes only `pages/`, `document.md`, `ledger.jsonl`, and `results.jsonl`; `document.json` (loss-aware), `tables/`, `assets/`, and source metadata are not yet implemented. The gap versus the goal contract is summarized in §10.

## 8. Verification Contract

Verification is done with 30-50 pages of the actual corpus and a golden set. Quality is not claimed from just a few samples at present.

Mandatory metrics:

- reading order accuracy
- page orientation correction accuracy
- complex table fidelity / TEDS
- page-spanning table reconstruction accuracy
- numeric accuracy
- hallucination rate
- source-gate false reject rate
- routing / processing-depth accuracy
- provider cost and latency
- guard flag precision/recall
- human-review volume and precision
- domain adaptation before/after error and cost deltas

The corpus must include born-digital, scan, multi-column, rotated/skewed, complex tables, page-spanning tables, figures/charts, documents with arithmetic invariants, and sensitive-document constraint cases.

## 9. Licensing and Privacy Constraints

Prefer a license-clean path.

- Prefer: pypdfium2, pdf-inspector, OpenDataLoader/ODL
- Avoid by default: PyMuPDF / PyMuPDF4LLM, unless AGPL or commercial-license implications are explicitly accepted

Sensitive documents reflect provider I/O constraints in the route decision. If a path such as the PaddleOCR official API supports only image URL fetch and not base64 inline images, it is unsuitable for sensitive documents that would require public hosting. Such documents are sent only to a provider path with inline image support, private network hosting, or a local/self-hosted provider.

## 10. Implementation Status

The goal architecture (this document + processing tiers P7/§2.5-2.6) is **implemented as R1-R8**. What is implemented:

- **Architecture (R1):** Runtime per-page auto-routing is abolished — `decide_route` is demoted to a diagnostic signal (zero runtime calls). Per-source **diagnosis-configuration** + mode-driven (`run.py`/`assemble.py`). Mode is the lever (no silent downgrade when a key is missing).
- **Deterministic base (R1):** ODL (`odl_extract.py`; structure, clean text, paragraphs, table grid, cell bbox) + pypdfium2 (value completeness/position) **combined**. `deterministic` mode (ODL + pypdfium2 completeness backstop), `det_vlm` mode (+ VLM reconciliation, R-M1).
- **det_vlm guards/augmentation (R8):** ODL + pypdfium2 **dual-injection grounding** (`grounding.py`), multi-image reconstruction of spanning tables (`previous_table_id` grouping), value oracle (`oracle.py`), arithmetic invariant (`arithmetic.py`), scan **dual pass** (Gemini + Paddle, `paddle_vlm.py`), input-quality and legibility guards. All opt-out.
- **Diagnostic tooling (R3-R4):** D-1 built-in VLM (`diagnose.py`; measurement-based, structure-aware sampling) + D-2 agent bundle/skill (`diagnose_prepare.py`, `docs/.design/diagnostic-d2.md`) -> `SourceProfile` persisted/reused (including a per-source threshold loop).
- **Rich output (R2):** `document.json` (loss-aware: content-hash id, provenance, page blocks, table/figure bbox, original labels, arithmetic), `tables/`, `assets/`, `pages/`, `ledger.jsonl` under `<out>/<source_id>/<document_id>/`. Content-hash idempotency + reprocessing skip. SQLite-derived catalog (`catalog.py`).
- Measurement basis: F16-F21 (measurement-findings). 164 tests (isolated uv environment).

**What remains:**

- **§8 golden-corpus quantitative verification (not done, core):** Measure reading order, TEDS, numeric accuracy, hallucination rate, source-gate false-reject rate, guard precision/recall, human-review volume, and more with a 30-50 page golden set. Calibration (F18/F19, ~36 documents) is a *mode-label oracle decision*, not per-element golden scoring -> **golden label generation must come first.**
- **enhancement:** oracle bbox **value substitution** (currently *flagging* only; exact-position *substitution* not yet started); noise-aware input-quality metric (F21); Paddle double pass on spans.
- **Deliberately on hold (by design):** service layer (FastAPI) — after the CLI/library prove the contract; additional providers (Ollama/GLM-OCR/Nemotron).
