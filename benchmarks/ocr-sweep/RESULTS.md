# OCR sweep — results

8 open OCR / document-VLM models self-hosted on a single NVIDIA L4 (GCP) and run through
parse-anything's `det_vlm --primary paddle` path on **one** 46-page PLOS Biology paper (born-digital
plus a rasterized image-only copy). 7 of 8 deployed. Interactive report: `report.html`.

> **Scope caveat, read first.** This is a single document, single domain (an English academic paper).
> The rankings below are the *relative* order **on this paper** — they do not generalize to tables-heavy
> docs, forms, Korean text, handwriting, or low-quality scans. Treat as a case study, not a general OCR
> benchmark.

## Ground truth

The **authoritative published full text** (PLOS JATS XML, `gt/reference.txt`, ~23k words) is the
reference. Each model's 46 pages are concatenated and compared **whole-document, order-insensitively**
(`score_vs_reference.py` -> `results/scores_vs_gt.md`).

> An earlier version scored against pypdfium2's text extraction (`results/scores.md`). **That is wrong
> and is deprecated** — pypdfium2 is itself a lossy, reading-order-scrambling extractor, so it measures
> "similarity to pypdfium2", not accuracy. It materially distorted the ranking (see olmOCR below).

## Ranking — token F1 vs the published text

| # | model | size | token_f1 | num_recall | vision judge /5 | note |
|---|---|---|---|---|---|---|
| 1 | datalab-to/chandra-ocr-2 | ~4B | **0.890** | 0.892 | 4.25 | top-cluster; strong numbers |
| 2 | zai-org/GLM-OCR | 0.9B | 0.887 | 0.892 | 4.75 | best on the vision judge; smallest + fastest |
| 2 | allenai/olmOCR-2-7B-1025-FP8 | 7B | 0.887 | 0.892 | 4.25 | **top-tier** (see correction) — best on the figure page |
| 4 | PaddlePaddle/PaddleOCR-VL · **pipeline** | 0.9B | 0.881 | 0.892 | — | layout pipeline; proper LaTeX |
| 5 | deepseek-ai/DeepSeek-OCR | 3B | 0.879 | 0.885 | 4.00 | flawless equations |
| 6 | PaddlePaddle/PaddleOCR-VL · single-shot | 0.9B | 0.876 | 0.871 | 2.75 | verbose (31k words); no LaTeX |
| 7 | nanonets/Nanonets-OCR2-3B | 3.75B | 0.875 | 0.892 | 4.75 | high judge ceiling but degenerates ("!" loop) on some pages |
| 8 | nvidia/NVIDIA-Nemotron-Parse-v1.2 | 0.9B | 0.066 | 0.022 | 0.00 | genuinely broken single-shot; needs its own postprocessor |
| — | baidu/Unlimited-OCR | 3.3B | — | — | — | did not deploy on L4 (no flash-attn wheel; vLLM path exits at startup) |

The vision judge is a 4-page (p4/p8/p12/p30), image-based, GT-free cross-check — it does **not** use
pypdfium2 or the reference text, so it validates the objective ranking independently.

Excluded: `PP-OCRv6_medium_det` and `nemotron-ocr-v2` are detection-only (boxes, not text);
Nemotron-Parse-v1.2 stood in for the NVIDIA slot.

## Findings
- **The metric changed the answer.** Against the real published text the top five (chandra, GLM, olmOCR,
  PaddleOCR-pipeline, DeepSeek) are a tight cluster (0.879–0.890), not the spread pypdfium2 implied.
- **olmOCR was a false negative.** Against pypdfium2 it looked worst (char_sim 0.812, "misses 1/3 of
  numbers", recall 0.685). Against the published text it is **top-tier (0.887, num_recall 0.892)** — its
  YAML front-matter / structure just didn't line up with pypdfium2's linearization. Numbers converged to
  ~0.892 for almost every model, i.e. pypdfium2 had been dropping numbers, not the models.
- **Size did not predict quality** — 0.9B GLM and PaddleOCR-VL sit with the 4–7B models at the top.
- **How you call the model matters as much as which model.** PaddleOCR-VL single-shot (`OCR:`) is verbose
  and LaTeX-free; its intended layout pipeline (`paddleocr doc_parser` + vLLM, via `paddle_pipeline.py`)
  gives proper LaTeX and a cleaner document — both go through parse-anything identically.
- **born − scan delta ≈ 0**: the model transcribes the same rendered image either way; parse-anything's
  value is the structured artifact it wraps around the text, not the raw characters.
- **Deployment was most of the work** — each model needed a different serving fix (vLLM version pins,
  context caps, custom images; the paddle pipeline also needed `libgl1`, backend `vllm-server`, served
  name `PaddleOCR-VL-1.6-0.9B`). See `models.json` notes and the git history.

## Files
- `results/scores_vs_gt.md` — the ranking above (vs published text). **Primary.**
- `results/scores.md`, `results/scores_pipe.md` — pypdfium2-based. **Deprecated.**
- `gt/reference.txt`, `gt/plos.xml` — the ground-truth published text and its source.
- `results/{ocr,pipe}_results.tgz` — every model's raw per-page markdown + parse-anything `document.md`.
- `results/judge_data.json` — the 4-page outputs the vision judge scored.
