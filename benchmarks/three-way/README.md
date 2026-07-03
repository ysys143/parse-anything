# Three-way PDF parser comparison

Compares **parse-anything** against its two raw ingredients, head-to-head on the same corpus:

| parser | what it is | how it's run |
|---|---|---|
| `odl` | **opendataloader-pdf** — the deterministic Java extractor, ALONE | `java -jar opendataloader-pdf-cli.jar <pdf> --format markdown` |
| `paddle` | **PaddleOCR-VL-1.6** — the document VLM, ALONE | rasterize each page → hosted jobs API (`PADDLE_BASE_URL`) |
| `pa` | **parse-anything** — the FULL pipeline | `cli --mode det_vlm --primary paddle` (ODL grounding + VLM + value-oracle gate + structure) |

The benchmark measures the **marginal value of orchestration**: parse-anything is built *on top of*
the other two, so the honest question is whether `pa` beats `max(odl, paddle)` — not "which tool wins".

## Corpus (`corpus/`)

- `born.pdf` — born-digital, 46p. Its text layer is the ground truth (via pypdfium2).
- `scan.pdf` — the same document rasterized to image-only (no text layer, `make_scan_pdf.py`).
  This isolates the OCR/VLM regime: ODL and parse-anything-deterministic have nothing to anchor to,
  so the VLM must carry. That born→scan collapse is exactly the gap orchestration is meant to fill.

## Run

```bash
PY=../../.venv/bin/python

# 1. dry-run (no API spend): odl + pa(deterministic) real, paddle stubbed. Validates the toolchain.
$PY run_compare.py --corpus corpus --results results --run dryrun

# 2. LIVE (real PaddleOCR-VL calls; needs PADDLE_BASE_URL + PADDLE_API_KEY in ../../.env):
$PY run_compare.py --corpus corpus --results results --run live --live

# 3. score (whole-doc = fair, pagination-invariant; --granularity page for per-page)
$PY score_compare.py --run-dir results/<run> --born corpus/born.pdf --out results/<run>/scores.json

# 4. cost-vs-quality Pareto frontier (quality axis defaults to num_recall)
$PY pareto.py --run-dir results/<run> --scores results/<run>/scores.json --quality num_recall

# 5. report (embeds the Pareto section + cost table if --pareto is passed)
$PY make_report.py --run-dir results/<run> --scores results/<run>/scores.json --pareto results/<run>/pareto.json
```

## Why a Pareto curve (the point of the whole benchmark)

parse-anything is built ON TOP of the other two, so the honest question is not "who wins" but
**"does the orchestration overhead buy quality the raw ingredients can't reach at the same cost?"**
That is a cost-vs-quality trade-off, so we measure BOTH:

| cost axis | meaning | why it separates the three |
|---|---|---|
| `wall_s` | end-to-end latency | pa runs ODL *and* the VLM *and* gating -> strictly more wall-clock |
| `vlm_calls` | VLM API invocations (**$ proxy**) | **the crux**: paddle calls the VLM on every page; pa's value-oracle GATES it (0 on born-digital, only flagged pages on scan) -> pa can match quality at a fraction of the VLM spend |
| `cpu_s` / `peak_rss_mb` | compute / memory | JVM (ODL) + Python (pa) footprint |

`pareto.py` computes the non-dominated frontier per regime: a parser is **on the frontier** if no
other parser gives more quality (default `num_recall`) at equal-or-lower cost. Off-frontier =
strictly dominated = its extra cost bought nothing. Note the frontier can flip with the quality
metric (on born-digital, ODL wins `num_recall` but pa wins `token_f1`) -- `--quality` selects it.

## Metrics (reused from `../ocr-sweep/score.py`)

`char_sim` (order-sensitive fidelity), `token_f1` (order-insensitive recall), `num_recall`
(≥4-digit numbers present — document-critical), `num_halluc` (fabricated numbers, lower better),
`coverage` (word count vs GT, ~1 ideal). Scored against the born text layer; the scan is scored
against the SAME GT (it's the same document).

## Verdict (`marginal_value_verdict` in `score_compare.py`)

Declares whether orchestration added value per regime. Default policy: `num_recall` arbiter, `pa`
must beat `max(odl, paddle)` by ≥ 0.02, with a `num_halluc > 0.15` veto. This is the one subjective
knob — swap the arbiter metric / margin / veto to match what "winning" should mean for your use case.

## Caveats

- **Bundled vs local ODL jar.** The `pa` path uses the *released* jar shipped inside the
  `opendataloader_pdf` Python package, NOT the locally-built `.local/workspace` jar carrying the
  triage-scan fix (PR #620). The `odl` column also uses a jar from `.local/workspace`. So the two
  "ODL" surfaces are not byte-identical; treat `odl` as "standalone ODL", `pa` as "the pipeline".
- **Whole-doc scoring is the fair default.** Parsers paginate differently (ODL emits one blob),
  so per-page scoring penalizes page-count offsets as if they were quality gaps. `--granularity doc`
  concatenates before scoring and is pagination-invariant.
