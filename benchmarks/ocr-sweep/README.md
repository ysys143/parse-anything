# OCR model sweep for parse-anything

Runs 7 open OCR / document-VLM models through parse-anything's `det_vlm --primary paddle`
path on ONE L4 GPU, one model at a time, and compares them on the same documents.

## How it plugs in (no parse-anything code change)

parse-anything's `--primary paddle` transcriber speaks a tiny 3-endpoint PaddleOCR jobs API.
`shim_server.py` emulates that API and, per request, injects each model's own OCR prompt +
knobs and forwards to a local OpenAI-compatible server (`localhost:8000/v1`). So swapping models
is just "start a different runner + set `PADDLE_BASE_URL` to the shim."

```
parse-anything --primary paddle -> shim (paddle API) -> shim (openai backend) -> model /v1
                                                      -> raw_<doc>/<model>/NNNN.md  (raw per-page OCR)
                                                      -> metrics_<doc>.jsonl        (latency / chars / state)
```

## Models

| backend | model | serving |
|---|---|---|
| vllm_docker | zai-org/GLM-OCR | `vllm-openai:v0.12.0` |
| vllm_docker | nanonets/Nanonets-OCR2-3B | `vllm-openai:v0.11.0` |
| vllm_docker | deepseek-ai/DeepSeek-OCR | `vllm-openai:latest` (validate) |
| vllm_docker | allenai/olmOCR-2-7B-1025-FP8 | `vllm-openai:v0.11.2` (FP8 on Ada) |
| vllm_docker | datalab-to/chandra-ocr-2 | `vllm-openai:v0.17.0` |
| custom_docker | baidu/Unlimited-OCR | `docker/Dockerfile.native` -> native_wrapper.py |
| custom_docker | nvidia/NVIDIA-Nemotron-Parse-v1.2 | `docker/Dockerfile.nemotron-parse` (vLLM + extras) |

`models.json` is the single source of truth (image, serve args, verbatim prompt, extra_body).

## Two test documents

- `document.pdf` (born-digital, 46p) - parse-anything runs in its strong, structure-preserving mode.
- `scan.pdf` - `make_scan_pdf.py` rasterizes it to an image-only PDF (no text layer) so grounding is
  disabled and each model must do unaided OCR (the discriminating signal).

## Run (on the VM)

```bash
# 1. provision an on-demand L4 in the existing project
./provision_vm.sh
# 2. bootstrap from canonical sources (install.sh + git clone), build scan, run sweep, pull results
./deploy_and_run.sh
# 3. stop billing
./teardown.sh
```

`run_bench.py` drives the sweep; `make_report.py` writes `results/report.md`
(status/timing table + parse-anything artifact stats + raw side-by-side excerpts).
