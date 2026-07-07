# Relative Performance Validation Plan

> Status: validation plan, not a completed benchmark.
> Goal: prove whether the ODL-VL pipeline improves extraction quality, safety, and operating cost
> against single-tool baselines: PyMuPDF/PyMuPDF4LLM, ODL local, Tesseract OCR, PaddleOCR official
> API, and Gemini direct.

## 1. Claim Under Test

The claim is not that every component is better than every baseline in isolation. The claim is:

1. **Quality:** ODL-VL's configured pipeline (`deterministic` or `det_vlm`) produces more faithful
   document-level Markdown/JSON than each single baseline on the same corpus.
2. **Safety:** ODL-VL reduces hallucinated or unsourced values compared with VLM/OCR-only baselines,
   especially on born-digital numeric tables and degraded inputs.
3. **Structure:** ODL-VL preserves table structure, formula/text order, bbox/source provenance, and
   original table/figure labels better than text-only or model-only baselines where OmniDocBench
   labels expose those targets.
4. **Cost control:** Source-level diagnose-then-configure calls VLMs only where the source profile
   justifies it, so it should match or exceed model-only quality with fewer provider calls on
   deterministic-friendly sources.

The result must be reported as evidence, not marketing. If a baseline wins a family, the report must
say so and explain the failure mode.

## 2. Systems Compared

| System | Role in benchmark | Expected strength | Expected weakness to test |
| --- | --- | --- | --- |
| **PyMuPDF / PyMuPDF4LLM** | Fast text/Markdown baseline | Clean born-digital text and readable Markdown | Weak structured JSON, complex tables, bbox/provenance contract, AGPL/commercial constraint |
| **ODL local** | Deterministic structure baseline | Semantic elements, table candidates, bbox, cleaner headers/footers | May miss value completeness; Java 17; no VLM visual repair |
| **Tesseract** | Local OCR baseline | Offline scan text recovery, permissive license | Weak layout/table semantics, no VLM reasoning, lower scan robustness on hard pages |
| **PaddleOCR official API** | OCR/VLM provider baseline | OCR/table/structure on image-like pages; often safer abstention under degradation | URL-fetch/privacy constraints, provider-only provenance, possible structure/value mismatch |
| **Gemini direct** | General VLM baseline | Strong visual understanding, captions, chart/page descriptions | Numeric hallucination under degraded input; no deterministic value authority by itself |
| **ODL-VL deterministic** | Our cheap configured mode | ODL structure + pypdfium2 value completeness/bbox backstop; no VLM cost | Limited visual semantics on scans/figures |
| **ODL-VL det_vlm** | Our high-accuracy configured mode | ODL + pypdfium2 + VLM reconciliation, source gate, scan/input-quality guards | Higher cost/latency; still needs oracle review for irreducible residuals |

## 3. Corpus Design

The headline evidence is split by axis. A single image-only benchmark cannot prove the born-digital
value-oracle claim, and a PDF text layer cannot be the gold target for a PDF extractor.

Required corpus contract:

- **Value axis:** use upstream facts that existed before PDF rendering. SEC EDGAR 10-K/10-Q XBRL is
  the default hard-regime corpus: it has born-digital financial statements, complex tables, and
  filer-authored numeric facts independent of any PDF extraction. `benchmarks/three-way/score_value_axis.py`
  enforces this by rejecting fact files whose `source_kind` is not one of the upstream kinds
  (`xbrl`, `sec_xbrl`, `filer_xbrl`, `author_markup`, `csv`, `html`, `jats`, `publisher_xml`,
  `upstream_xbrl`).
- **Structure axis:** use OmniDocBench, hand-labeled golden pages, or other explicit table/region
  labels. Report table detection, TEDS, row/column/cell F1, merged-cell accuracy, and page-spanning
  continuation only where those labels exist.
- **Clean born-digital invariants:** run label-free checks such as run-invariance, source consistency,
  unsourced-number rate, and artifact schema round-trip. These are guarantees, not claims that one
  extractor transcribes cleaner text than another.
- **Calibration split:** keep a separate D-1 `SourceProfile` calibration split. Do not tune thresholds
  on the same documents used for final scoring.

The value-axis and structure-axis results must be reported separately:

| Axis | Valid GT | Main proof target | Invalid shortcut |
| --- | --- | --- | --- |
| Value | SEC XBRL, author CSV/HTML, publisher XML/JATS | Numeric exact recall, unsourced-number rate, silent-hallucination rate | PDF text extracted by pypdfium2, ODL, PyMuPDF, or a sibling extractor |
| Structure | OmniDocBench labels, table HTML, human golden regions | Region/table/cell structure fidelity | Treating XBRL fact recall as table structure quality |
| Clean invariants | Born-digital source text and artifact schemas | Determinism, source consistency, round-trip validity | Claiming broad quality wins without labeled targets |

Do not claim improvement on arithmetic invariants, private-document privacy, page-spanning table
continuation, or complex-form structure unless the selected labels support that claim directly.

## 4. Baseline Execution Rules

All systems run on the same input PDFs and the same rendered page images where applicable. Do not
give a baseline extra information that another system cannot access, except where that information is
the baseline's normal API contract.

### PyMuPDF / PyMuPDF4LLM

- Run plain text extraction and PyMuPDF4LLM Markdown export separately.
- Score the better of the two for readable Markdown, but do not invent structured table JSON that the
  baseline did not emit.
- Record license status separately; license is an operational metric, not a quality score.

### ODL local

- Run ODL without live VLM/OCR backend.
- Export ODL JSON/Markdown and preserve bbox/table metadata where available.
- Score ODL as a standalone baseline before ODL-VL adds pypdfium2 value backstop or VLM reconciliation.

### Tesseract

- Render every page at the same DPI used by ODL-VL.
- Run OCR with fixed language packs per document family.
- Score text recovery separately from structure, because Tesseract does not own table semantics.

### PaddleOCR official API

- Use the documented Paddle provider path only.
- Record submit/poll latency, model alias, status, cost estimate if available, and whether public URL
  hosting was required.
- If Paddle only supports URL fetch, use a stable public OmniDocBench artifact URL or a benchmark
  hosting mirror recorded in the run manifest. If that is unavailable, mark Paddle `not_eligible_io`
  for that slice rather than changing the input contract.

### Gemini direct

- Send the same rendered page image(s) used by ODL-VL.
- Use a fixed prompt family for extraction, plus a separate fixed prompt for figure description when
  the benchmark requires it.
- Do not inject deterministic source values into the Gemini-only baseline; that is the ODL-VL
  pipeline advantage being tested.

### ODL-VL

- Run `--diagnose` once per source to produce a `SourceProfile`.
- Re-run documents with `--use-profile` and record the recommended mode, thresholds, evidence, and
  final artifacts.
- Include two ablations:
  - `deterministic` forced, to isolate deterministic fusion gains.
  - `det_vlm` forced, to isolate reconciliation/guard gains independent of D-1 mode selection.

## 5. Metrics

### Document and Text

| Metric | Measurement |
| --- | --- |
| Text recall / precision | Normalized token match against golden text anchors |
| Reading-order accuracy | Pairwise order accuracy or normalized inversion distance |
| Heading/list fidelity | Precision/recall for headings, list items, and caption elements |
| Markdown usability | Human/oracle rating on readability, without letting it override JSON truth |

### Tables and Structure

| Metric | Measurement |
| --- | --- |
| Table detection F1 | Match table regions by page + IoU or label |
| Table structure score | TEDS where HTML/golden table exists; otherwise row/column/cell F1 |
| Merged-cell accuracy | Header hierarchy and spanning-cell match |
| Page-spanning table F1 | Correct logical table id, `source_pages`, continuation edges |
| Cell bbox/provenance coverage | Percent of cells with bbox/source page/source text |

### Values and Hallucination

| Metric | Measurement |
| --- | --- |
| Numeric exact accuracy | Exact normalized value match against source oracle/golden |
| Unsourced number rate | Output numbers absent from born-digital source text |
| Source-gate precision/recall | Whether flags correspond to true unsourced or suspect values |
| Conditional arithmetic invariant pass rate | Pass/fail only where labels or source metadata define equations |
| Silent hallucination rate | Wrong value emitted without a guard flag |

### Visual/OCR Cases

| Metric | Measurement |
| --- | --- |
| OCR text recovery | Character/word accuracy on scan-only pages |
| Low-quality abstention | Correct `illegible_low_quality` or equivalent review signal |
| Figure handling | Caption/placeholder/description correctness against page oracle |
| Orientation robustness | Correct text/structure after rotation/skew |

### Operations

| Metric | Measurement |
| --- | --- |
| VLM call count | Calls per page and per document |
| Latency | End-to-end wall time and provider wait time |
| Cost estimate | Provider-reported or modeled cost per document |
| Provider eligibility | Whether the system can run on the selected OmniDocBench pages without unsafe or unsupported I/O |
| Human-review volume | Count of flagged cells/pages sent to oracle review |

## 6. Relative Improvement Criteria

Report improvement with paired comparisons. Each document page is a paired sample across systems.

Required reporting:

1. **Composite score:** OmniDocBench-native weighted score, with any local reweighting published
   before the run.
2. **Best-baseline delta:** ODL-VL score minus the best single baseline for each OmniDocBench
   document type and element category.
3. **Win/tie/loss table:** page-level and document-level counts.
4. **Bootstrap confidence interval:** 95% CI for the composite and major family deltas.
5. **Failure-mode ledger:** every loss must map to a concrete cause, not a generic "model error".

Default acceptance gates:

| Gate | Pass condition |
| --- | --- |
| Overall quality | ODL-VL beats the best single baseline on composite score with positive 95% CI |
| Numeric safety | Where OmniDocBench pages expose numeric table/text labels and reliable text-layer oracles, ODL-VL has lower silent hallucination rate than Paddle/Gemini |
| Table structure | ODL-VL beats PyMuPDF, Tesseract, Paddle, and Gemini on OmniDocBench table metrics; ODL is allowed to tie or win on pure structure, but ODL-VL must improve value completeness/provenance in secondary analysis |
| Page-spanning tables | Conditional: only asserted if the selected OmniDocBench labels support logical continuation scoring |
| Cost control | On deterministic-friendly sources, ODL-VL uses fewer VLM calls than Paddle/Gemini-only while staying non-inferior on quality |
| Provider eligibility | Any baseline that cannot process the selected OmniDocBench inputs under its supported I/O contract is reported as ineligible for that slice, not force-run |

If a gate fails, the validation report must either reject the improvement claim for that document
type/element category or create a concrete follow-up issue.

## 7. Required Ablations

These ablations prove which part of the pipeline created the gain.

| Ablation | Purpose |
| --- | --- |
| ODL only vs ODL-VL deterministic | Measures pypdfium2 value-completeness backstop and output contract gain |
| ODL-VL deterministic vs det_vlm | Measures VLM reconciliation gain and cost |
| det_vlm without source gate | Measures hallucination guard impact |
| det_vlm without scan/input-quality gate | Measures low-quality abstention impact |
| D-1 profile vs forced det_vlm | Measures diagnose-then-configure cost/quality tradeoff |
| Per-page route simulation vs source profile | Confirms why runtime auto-routing was removed |

## 8. Output Artifacts

Each benchmark run must write a reproducible directory:

```text
benchmark-runs/<run_id>/
  manifest.json
  corpus/
    documents.jsonl
    labels/
  systems/
    pymupdf/
    odl/
    tesseract/
    paddle/
    gemini/
    parse_anything_deterministic/
    parse_anything_det_vlm/
  scores/
    page_scores.jsonl
    document_scores.jsonl
    family_summary.csv
    deltas.csv
  reports/
    relative-performance.md
    failures.md
```

The committed repository should keep only non-sensitive manifests, scripts, schemas, and aggregate
reports. Provider response bodies, signed URLs, API keys, and raw benchmark outputs stay outside git.

## 9. Manual Oracle Review

Automatic metrics are not enough for complex structure and figures. Use the review/oracle position
defined in `processing-tiers-and-adaptation.md`:

- sample all ODL-VL losses and all cases where ODL-VL wins only by guard flags;
- review every page with silent hallucination candidates;
- review every page-spanning table prediction only when continuation labels exist;
- review at least 10% of unflagged high-risk numeric pages to estimate false negatives;
- capture `correct`, `incorrect`, `needs_human`, and corrected value/structure fields.

The oracle output becomes an adjudication log and, if needed, a label-mapping update. It must not
silently rewrite OmniDocBench labels.

## 10. Execution Phases

1. **Harness readiness:** add baseline runners and normalize each system into the common scoring IR.
2. **OmniDocBench scorer dry run:** run a small pinned subset through every baseline and verify that
   normalization into the scoring IR preserves OmniDocBench labels.
3. **Full or stratified OmniDocBench run:** run eligible systems on the pinned evaluation set.
4. **Ablation run:** run required ODL-VL ablations on the same document ids.
5. **Oracle review:** adjudicate sampled wins/losses and all high-risk cells/tables.
6. **Report:** publish OmniDocBench-native scores, family/type deltas, confidence intervals,
   cost/latency, and failure taxonomy.

## 11. Decision Outcomes

| Outcome | Meaning |
| --- | --- |
| **Promote claim** | ODL-VL passes the gates and failure modes are understood |
| **Narrow claim** | ODL-VL wins specific families but not all; README/docs must state the narrower scope |
| **Revise pipeline** | A failed gate maps to an implementation gap, e.g. table merge, source gate, OCR scan handling |
| **Revise corpus mapping** | OmniDocBench labels are ambiguous for the claimed local metric, or the selected subset is not discriminative enough |
| **Reject claim** | A baseline is better under the target constraints and the pipeline should not claim improvement |

## 12. Links to Existing Contracts

- `pdf-pipeline-requirements.md`: target artifact contract and validation metric categories.
- `processing-tiers-and-adaptation.md`: DET/VLM/HUM boundary, source profiles, and oracle position.
- `measurement-findings.md`: prototype evidence that motivated guards, D-1/D-2, and source-level
  diagnose-then-configure.
- `vlm-provider-and-fixture-plan.md`: provider choices and privacy/provider constraints; generated
  fixtures are not the headline benchmark data for this plan.
