# OCR sweep — results

8 open OCR / document-VLM models self-hosted on a single NVIDIA L4 (GCP) and run through
parse-anything's `det_vlm --primary paddle` path on a 46-page PLOS Biology paper (born-digital + a
rasterized image-only copy). 7 of 8 deployed; scored vs the born-digital text layer + a page-by-page
vision judge. Interactive report: `report.html`.

## Ranking (objective text fidelity + vision judge)

| # | model | size | char_sim (born) | judge avg /5 | note |
|---|---|---|---|---|---|
| 1 | zai-org/GLM-OCR | 0.9B | **0.881** | **4.75** | best on both axes; clean LaTeX. smallest + fastest |
| 2 | deepseek-ai/DeepSeek-OCR | 3B | 0.858 | 4.00 | flawless equations, low hallucination |
| 3 | datalab-to/chandra-ocr-2 | ~4B | 0.857 | 4.25 | best number recall (0.998) |
| 4 | nanonets/Nanonets-OCR2-3B | 3.75B | 0.823 | 4.75 | high ceiling but degenerates ("!" loop) on some pages (coverage 1.9×) |
| 5 | allenai/olmOCR-2-7B-1025-FP8 | 7B | 0.812 | 4.25 | best on figures; misses 1/3 of numbers (recall 0.685) |
| 6 | PaddlePaddle/PaddleOCR-VL (single-shot `OCR:`) | 0.9B | 0.859 | 2.75 | element-level single-shot: no LaTeX, loops on figures — understates the model |
| 1* | PaddlePaddle/PaddleOCR-VL (**full pipeline**) | 0.9B | **0.889** | — | layout->recognition->assembly (paddleocr doc_parser + vLLM): **tops char_sim, above GLM (0.881)**; proper LaTeX, coverage 1.53->1.04 |
| 7 | nvidia/NVIDIA-Nemotron-Parse-v1.2 | 0.9B | 0.005* | 0.00 | *raw bbox format; unusable single-shot, needs its postprocessor |
| — | baidu/Unlimited-OCR | 3.3B | — | — | did not deploy on L4 (no flash-attn wheel; vLLM path exits at startup) |

Excluded: `PP-OCRv6_medium_det` and `nemotron-ocr-v2` are detection-only (boxes, not text);
Nemotron-Parse-v1.2 stood in for the NVIDIA slot.

## Findings
- **Size did not predict quality** — the two 0.9B models (GLM-OCR, PaddleOCR-VL) top the objective text
  fidelity; the 7B olmOCR is middling and weak on numbers.
- **born − scan delta ≈ 0**: the model transcribes the same rendered image either way; parse-anything's
  value is the structured artifact wrapped around the text, not the raw characters.
- **How you call the model matters as much as which model.** PaddleOCR-VL run single-shot (`OCR:` on the
  full page) scores 0.859 with no LaTeX; run in its intended layout pipeline (`paddleocr doc_parser` +
  vLLM recognition, via `paddle_pipeline.py`) it jumps to **0.889 — the top objective score** — with proper
  LaTeX equations and coverage back to 1.04. Both go through parse-anything identically; only the client differs.
- **Deployment was most of the work** — each model needed a different serving fix (vLLM version pins,
  context caps, custom images; the paddle pipeline also needed `libgl1`, backend `vllm-server`, and served
  name `PaddleOCR-VL-1.6-0.9B`). See `models.json` notes and the git history.
