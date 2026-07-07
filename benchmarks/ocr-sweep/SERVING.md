# Model serving guide — ocr-sweep

How to actually get each OCR / document-VLM running on a single NVIDIA L4 (24 GB, GCP `g2-standard-8`,
CUDA 12.9), and the gotcha that cost time for each. `models.json` is the machine-readable source of truth
(each entry drives both the runner and the shim); this doc is the **why**, so the next person doesn't
re-derive it. Deployment was most of the work — every model needed a different fix.

> **Meta-lesson (read first).** The model **card** gives a happy-path recipe; the **ground truth is in
> the model code** (`modeling_*.py`, the processor, the logits-processor module) + empirical testing.
> Every hard bug this session was invisible in the card and only visible in the source or in the actual
> per-page output. When a model misbehaves: compare its output across different pages, read its
> `modeling_*.py`, and test one request directly — don't trust the card.

---

## Four serving strategies (decision tree)

| Strategy | When | How | Models |
|---|---|---|---|
| **A. vLLM, generic image** | arch recognized by `vllm/vllm-openai:latest` | `docker run vllm-openai:latest --model <id> …` | GLM-OCR, DeepSeek-OCR, PaddleOCR-VL (single-shot) |
| **B. vLLM, PINNED version** | arch needs a specific vLLM build | pin the image tag | Nanonets (`v0.11.2`), olmOCR (`v0.11.2`), chandra (needs `0.17.0`) |
| **C. vLLM, model's OFFICIAL image** | arch not in generic vLLM; vendor ships an image | use the vendor tag, not the generic one | Unlimited-OCR (`vllm/vllm-openai:unlimited-ocr-cu129`) |
| **D. Native transformers** | vLLM can't serve it correctly | `custom_docker` → `native_wrapper.py` wraps `model.generate`/`.infer_multi` behind OpenAI `/v1` | Nemotron-Parse (vLLM serves it blind), Unlimited-OCR **whole-doc** (`infer_multi` is transformers-only) |

The harness (`run_bench.py`) launches `vllm_docker` = `docker run <vllm_image> …`; `custom_docker` =
`docker build -f <dockerfile>` then run. Either way it serves OpenAI `/v1/chat/completions`, and the
shim (`shim_server.py`) routes parse-anything's `--primary paddle` calls to whichever is up — so
parse-anything itself is unchanged.

---

## Per-model

### GLM-OCR — `zai-org/GLM-OCR` (0.9B, glm_ocr arch)
- **Strategy A.** `vllm/vllm-openai:latest`, `--dtype bfloat16 --max-model-len 16384 --gpu-memory-utilization 0.85`. `trust_remote_code` not needed.
- **Prompt:** `Text Recognition:`
- **Gotcha:** none — fits the L4 trivially. Best all-rounder (0.887 objective, top of the vision judge). A full-page document model, so it handles figures by capturing labels and moving on.

### Nanonets-OCR2-3B — `nanonets/Nanonets-OCR2-3B` (Qwen2.5-VL-3B)
- **Strategy B — PIN `vllm/vllm-openai:v0.11.2`.** `--max-model-len 32768 --gpu-memory-utilization 0.90 --limit-mm-per-prompt '{"image": 1}'`.
- **Prompt:** long instruction ("Extract the text … tables in HTML … equations in LaTeX …"). Checkbox glyphs are stored as ASCII sentinels `{U2610}`/`{U2611}` in `models.json`; the shim restores `chr(0x2610)`/`chr(0x2611)` before sending (keeps the JSON ASCII-clean).
- **Gotcha:** on `:latest` it emits **pure `!` garbage** (a Qwen2.5-VL regression); `v0.11.2` fixes it. `max_tokens 15000`. Still degenerates into a `!`-loop on some pages.

### DeepSeek-OCR — `deepseek-ai/DeepSeek-OCR` (3B MoE, ~570M active)
- **Strategy A**, but needs the model's **no-repeat n-gram logits processor**:
  `--logits_processors vllm.model_executor.models.deepseek_ocr:NGramPerReqLogitsProcessor --no-enable-prefix-caching --mm-processor-cache-gb 0 --max-model-len 8192 --dtype bfloat16`.
- **Prompt:** `<|grounding|>Convert the document to markdown.` **extra_body:** `skip_special_tokens: false`, plus `vllm_xargs: {ngram_size: 30, window_size: 90, whitelist_token_ids: [128821,128822]}`.
- **Gotcha:** model context caps at **8192** — keep `--max-model-len 8192` **and** `max_tokens 4096` so `vision_tokens + output ≤ 8192` (larger `max_tokens` → HTTP 400). Hardcodes GUNDAM mode. Without the ngram processor it repetition-collapses (DeepSeek-OCR lineage trait — see also Unlimited).

### olmOCR-2-7B-FP8 — `allenai/olmOCR-2-7B-1025-FP8` (7B FP8, Qwen2.5-VL)
- **Strategy B — `vllm/vllm-openai:v0.11.2`.** `--max-model-len 16384 --gpu-memory-utilization 0.85 --limit-mm-per-prompt '{"video": 0}' --disable-log-requests`.
- **Gotcha:** FP8 W8A8 is **auto-detected**; L4 (sm89 / Ada) runs it natively — **do NOT pass `--quantization`**. olmocr renders pages at longest-dim **1288**. Returns YAML front-matter (`is_diagram`, …) — good for figures, but that front-matter is a non-clean-markdown format (see issue #17).

### chandra-2 — `datalab-to/chandra-ocr-2` (4–5B, Qwen3.5 hybrid)
- **Strategy B — needs `vllm 0.17.0` (qwen3_5 arch).** `--max-model-len 18000 --max-num-seqs 16 --max-num-batched-tokens 2048 --enable-prefix-caching --mm-processor-kwargs '{"min_pixels": 3136, "max_pixels": 6291456}'`, `extra_body: {top_p: 0.1}`.
- **Prompt:** a layout-block instruction ("OCR this image to HTML, arranged as layout blocks … `data-bbox` … `data-label`: Caption/Equation-Block/Figure/Diagram/…").
- **Gotcha:** **outputs HTML** (`<div data-bbox data-label>`), not markdown → post-convert to markdown in the report. The layout-block prompt is *why* it handles figures well (it classifies the region as `Diagram` and describes it) — but HTML is a non-clean-markdown format (issue #17).

### PaddleOCR-VL — `PaddlePaddle/PaddleOCR-VL` (0.9B, ERNIE-4.5-VL) — THREE ways
The vLLM `/v1` endpoint is **ELEMENT-level recognition** (built to OCR one cropped region), not a
full-page model. That distinction is the whole story:
1. **single-shot (Strategy A):** `vllm/vllm-openai:latest --trust-remote-code`, prompt `OCR:`. Fast, but it is the element recognizer fed a **whole page** → on a complex figure page it **repetition-collapses** (e.g. `0.3s|0.9s|0.5s` ×51 on Fig 2, `D` ×3957 on Fig 6) because there is no layout stage and no no-repeat-ngram guard (`extra_body {}`). 0.876 objective, but 3.50 on the vision judge.
2. **layout pipeline (intended):** `PaddleOCRVL(vl_rec_backend="vllm-server", vl_rec_server_url=…)` (`paddle_pipeline.py`), needs `libgl1`, served name `PaddleOCR-VL-1.6-0.9B`. A layout detector crops the page and gates figures out as `<img>` regions **before** recognition, so it **never loops** (checked all 46 pages) and gives proper LaTeX. 0.881 objective, 4.50 vision judge.
3. **official hosted API:** the aistudio jobs API (`PADDLE_BASE_URL` / `PADDLE_API_KEY`, model `PaddleOCR-VL-1.6`) — this is parse-anything's native `--primary paddle` backend. Byte-similar to the self-hosted pipeline (same `doc_parser`); it even fixes a couple of self-hosted OCR slips. The pipeline↔API gap is ~90–98% word-identical and is mostly LaTeX-delimiter / citation-formatting convention (different recognition deployments), not accuracy.
- **Takeaway:** "PaddleOCR collapses" is wrong — *only the self-hosted single-shot call on a figure page* collapses. Use the pipeline or the hosted API.

### Nemotron-Parse-v1.2 — `nvidia/NVIDIA-Nemotron-Parse-v1.2` (885M, ViT-H enc + mBart dec)
- **Strategy D — NATIVE transformers only.** `custom_docker` → `docker/Dockerfile.nemotron-native`
  (FROM `vllm/vllm-openai:v0.14.1` for its torch/transformers + `pip install albumentations timm open_clip_torch`) → `native_wrapper.py` `native_kind: nemotron_parse` runs `AutoModel` + `AutoProcessor` + `GenerationConfig`, `model.generate`.
- **Prompt (4-token, verbatim):** `</s><s><predict_bbox><predict_classes><output_markdown><predict_no_text_in_pic>`.
- **Gotcha (the big one):** **vLLM serves this encoder-decoder VLM BLIND** — pages 10/20/30 gave byte-similar hallucinated `**100.05**` tables because the image never reached the ViT-H encoder (vLLM's enc-dec multimodal path is broken here; L4 is not on NVIDIA's validated list). We chased the *symptom* (repetition) through the wrong fix — the model's repetition-stop logits processor (`nemotron_parse_vllm_logitprocs:NemotronParseRepetitionStopLogitsProcessor`, note the exact class name; the card's `…StopProcessor` is wrong) — before realizing the disease was image-blindness. **Native transformers reads the page correctly: 0.066 → 0.881, num_halluc 0.979 → 0.247.** Note `<predict_no_text_in_pic>` makes it emit figures AND display equations as bare `<class_Picture>` boxes → top on objective text but last on the vision judge (3.25).

### Unlimited-OCR — `baidu/Unlimited-OCR` (3.3B, DeepSeek-OCR lineage) — TWO paths
**per-page (Strategy C):**
- **Baidu's OFFICIAL vLLM image** `vllm/vllm-openai:unlimited-ocr-cu129` (CUDA 12.9; there is also `:unlimited-ocr` for CUDA 13). The **generic** `vllm-openai` image exits at startup — that was the original "did not deploy". `--trust-remote-code --dtype bfloat16 --max-model-len 16384 --gpu-memory-utilization 0.85`, `extra_body: {skip_special_tokens: false}`.
- **Prompt MUST start with `<image>`:** `<image>document parsing.` — `document parsing.` alone returns **empty output** (vLLM loads a fallback chat template, so the explicit `<image>` in the text is what places the image).
- **Gotcha:** `--max-model-len 16384`, not 8192 — with `max_tokens 8192`, an 8192-len context leaves **0** budget for the ~3.5k image tokens → HTTP 400.

**whole-doc (Strategy D — native only; vLLM can't do multi-page):**
- `docker/Dockerfile.native`: `FROM nvidia/cuda:12.9.1-cudnn-devel-ubuntu22.04`, `torch==2.10.0` (cu129), `transformers==4.57.1`, **`matplotlib`** (the model's remote code imports it), pillow/einops/addict/easydict/pymupdf. `native_wrapper.py` `native_kind: deepseek_infer_multi`, `pipeline: whole_doc` sends ALL page images in one request → `model.infer_multi`.
- **Attention = `eager`.** The model implements **no sdpa** (transformers raises "does not support scaled_dot_product_attention"); and there is **no torch2.10 flash-attn prebuilt wheel** (flash-attn ships wheels only up to torch2.8) and the source build OOMs the 32 GB builder at `MAX_JOBS≥4`. eager works on plain torch2.10.
- **`infer_multi` contract (from the code, not the card):** prompt needs a **single** `<image>` token (`<image>Multi page parsing.`) — it packs all page images at that one position; a prompt without it → `IndexError`. It **returns a tuple `(outputs, output_tokens)`** and **saves `result.md`** (not `.mmd`) — the wrapper must take `res[0]` / glob `*.md`. `infer_kwargs: {image_size: 640, no_repeat_ngram_size: 35, ngram_window: 1024}` — `no_repeat_ngram` is required (DeepSeek-lineage loop otherwise), and `image_size=640` (not the card's 1024) so eager's O(N²) attention over 46 pages fits the L4 (1024 OOMs).
- **Known limitation:** whole-doc at 640 under-reads (born doc early-stopped at 401 words). Doing it *properly* needs `image_size=1024` → needs flash-attn (`MAX_JOBS=2` source build). Not yet fairly measured.

---

## Cross-cutting gotchas

1. **vLLM version is not fungible.** Nanonets needs `v0.11.2` (`:latest` → `!` garbage), chandra needs `0.17.0` (qwen3_5 arch), olmOCR `v0.11.2`, DeepSeek/GLM/Paddle `:latest`. Pin per model.
2. **Repetition collapse is the recurring failure.** DeepSeek-lineage (DeepSeek-OCR, Unlimited), Nanonets (`!`), and any greedy VLM on ambiguous/dense input will loop **without a no-repeat-ngram guard**. Provide the model's ngram processor (DeepSeek), `no_repeat_ngram_size` (Unlimited native), or use a layout pipeline that gates figures out (Paddle).
3. **Context budget:** `image_tokens + max_tokens ≤ max-model-len`. Bit DeepSeek (8192/4096) and Unlimited (needed 16384 to fit ~3.5k image tokens + 8192 output).
4. **Some models can't be vLLM-served.** Encoder-decoder VLMs (Nemotron-Parse) go blind under vLLM's mm path on non-validated GPUs. Transformers-only APIs (Unlimited `infer_multi`) have no vLLM equivalent. → native transformers via `native_wrapper.py`.
5. **Prompt shape matters as much as weights.** `<image>` placement (Unlimited), element-`OCR:` vs full-page (Paddle), layout-block instruction (chandra), figure-placeholder instruction (olmOCR).
6. **Official image ≠ generic image.** Unlimited's generic `vllm-openai` exits; the vendor tag works.
7. **FP8 on Ada** (olmOCR) is auto-detected — don't pass `--quantization`.
8. **Output format leaks downstream.** Grounded (`<x_>`, `<|ref|>`), HTML (chandra), YAML front-matter (olmOCR) are not normalized by parse-anything's substrate → see **issue #17** (per-model adapter layer).

---

## Harness mechanics

- **`shim_server.py`** — mimics the PaddleOCR jobs API (submit / poll / fetch JSONL) so parse-anything's
  `--primary paddle` path routes to whatever model is up, with **zero parse-anything changes**. Injects
  the per-model prompt (paddle path drops the grounding prompt).
- **`prewarm.py`** — batched pre-transcription: fires all 46 pages concurrently so vLLM continuous-batches
  them (~5× faster than parse-anything's 1-page-at-a-time), writes a cache the shim replays. `--pipeline
  whole_doc` sends all pages in one request (native `infer_multi`).
- **`native_wrapper.py`** — wraps native models (`deepseek_infer` / `deepseek_infer_multi` / `nemotron_parse`)
  behind OpenAI `/v1`, so the shim treats them like a vLLM server. `hf_id` lets one HF model back two
  registry ids (Unlimited per-page + `__multi`).
- **`run_bench.py`** — one model in VRAM at a time: start runner → wait `/v1/models` (fails fast if the
  container exits) → prewarm + parse-anything (`--force`) per doc → tear down. `pipeline: whole_doc`
  also runs `parse-anything --whole-doc` against the runner.
- **`deploy_and_run.sh`** — installs parse-anything **from source** (uv py3.12 venv + Java 17 for ODL) so
  branch-only features (`--whole-doc`) reach the VM; the release-bundle install would not. Clones the
  harness branch, builds the scan PDF, runs the sweep, pulls results.
- **`provision_vm.sh`** — one on-demand L4 (`common-cu129-ubuntu-2204-nvidia-580` DLVM) + Docker + nvidia
  runtime. **L4 is frequently STOCKOUT** on-demand — sweep zones across regions (quota is regional =8;
  `us-west1-a` had capacity when `us-central1` was dry). Spot is a fallback but risks preemption mid-run.
