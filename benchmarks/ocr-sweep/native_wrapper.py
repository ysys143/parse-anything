#!/usr/bin/env python3
"""Minimal OpenAI-compatible /v1/chat/completions server wrapping a NATIVE OCR model.

Two of the seven models don't serve under vLLM on an L4, so we wrap their native inference
API behind the SAME OpenAI endpoint the shim already speaks. That keeps the shim uniform:
it always POSTs {image_url + text} to http://127.0.0.1:8000/v1/chat/completions.

native_kind:
  deepseek_infer        -> AutoModel(trust_remote_code).infer(tokenizer, prompt, image_file, **infer_kwargs)
                           (DeepSeek-OCR lineage, single image)
  deepseek_infer_multi  -> same model; .infer_multi(image_files=[...]) when >1 image is sent, else .infer()
                           (baidu/Unlimited-OCR native multi-page / long-horizon mode)
  nemotron_pipeline     -> NemotronOCRV2()(image) -> [{text,...}] joined into plain markdown
                           (nvidia/nemotron-ocr-v2; detector+recognizer, no prompt)

Reads infer_kwargs/prompt from models.json. Runs GPU-side only.

Usage:
  python native_wrapper.py --models-file models.json --model-id baidu/Unlimited-OCR --port 8000
"""
from __future__ import annotations

import argparse
import base64
import glob
import json
import os
import re
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_MODEL = None          # lazily-loaded (model, tokenizer) or pipeline
_CFG: dict = {}
_KIND = ""
_MODEL_ID = ""
_INFER_LOCK = threading.Lock()   # serialize model.infer() (single-GPU, not concurrency-safe)


def _load_cfg(models_file: str, model_id: str) -> dict:
    with open(models_file, encoding="utf-8") as fh:
        data = json.load(fh)
    for m in data.get("models", []):
        if m["id"] == model_id:
            return m
    raise SystemExit(f"model id not in registry: {model_id}")


def _ensure_loaded() -> None:
    global _MODEL
    if _MODEL is not None:
        return
    if _KIND in ("deepseek_infer", "deepseek_infer_multi"):
        import torch
        from transformers import AutoModel, AutoTokenizer
        tok = AutoTokenizer.from_pretrained(_MODEL_ID, trust_remote_code=True)
        # eager (not sdpa/flash_attention_2): UnlimitedOCRForCausalLM does NOT implement sdpa
        # (transformers raises "does not support ... scaled_dot_product_attention"), and flash_attention_2
        # needs the flash-attn wheel whose torch2.6 downgrade broke this model earlier. eager runs on
        # plain torch2.10 -- slower but correct. Override via NATIVE_ATTN_IMPL (e.g. flash_attention_2).
        attn = os.environ.get("NATIVE_ATTN_IMPL", "eager")
        model = AutoModel.from_pretrained(
            _MODEL_ID, trust_remote_code=True, use_safetensors=True,
            _attn_implementation=attn, torch_dtype=torch.bfloat16,
        ).eval().cuda()
        _MODEL = (model, tok)
    elif _KIND == "nemotron_pipeline":
        from nemotron_ocr.inference.pipeline_v2 import NemotronOCRV2
        _MODEL = NemotronOCRV2()
    else:
        raise SystemExit(f"unknown native_kind: {_KIND}")
    print(f"[native] loaded {_MODEL_ID} ({_KIND})", flush=True)


def _infer_deepseek(png_path: str, prompt: str) -> str:
    """DeepSeek-OCR-lineage .infer() has a documented DUAL output: it returns the text AND writes
    `result.mmd` to output_path (save_results=True). We prefer the return value; if a given build
    returns None/empty we read the written .mmd. VALIDATE which path this specific build uses on the
    first VM smoke run (research flagged the return contract as build-dependent)."""
    model, tok = _MODEL
    kw = dict(_CFG.get("infer_kwargs") or {})
    with tempfile.TemporaryDirectory() as out_dir:
        res = model.infer(tok, prompt=prompt, image_file=png_path, output_path=out_dir,
                          save_results=True, **kw)
        if isinstance(res, str) and res.strip():
            return res
        written = sorted(glob.glob(os.path.join(out_dir, "**", "*.mmd"), recursive=True))
        if written:
            with open(written[0], encoding="utf-8") as fh:
                return fh.read()
    return res if isinstance(res, str) else ""


def _infer_deepseek_multi(png_paths: list[str], prompt: str) -> str:
    """Multi-image path: DeepSeek-OCR-lineage .infer_multi() transcribes N page images in ONE call
    (Unlimited-OCR's native multi-page / long-horizon mode, 32k ctx). Same DUAL-output contract as
    .infer(): prefer the returned string; else read the written .mmd file(s), joined in page order."""
    model, tok = _MODEL
    kw = dict(_CFG.get("infer_kwargs") or {})
    with tempfile.TemporaryDirectory() as out_dir:
        res = model.infer_multi(tok, prompt=prompt, image_files=list(png_paths),
                                output_path=out_dir, save_results=True, **kw)
        if isinstance(res, str) and res.strip():
            return res
        written = sorted(glob.glob(os.path.join(out_dir, "**", "*.mmd"), recursive=True))
        if written:
            return "\n\n".join(open(w, encoding="utf-8").read() for w in written)
    return res if isinstance(res, str) else ""


def _infer_nemotron(png_path: str, _prompt: str) -> str:
    preds = _MODEL(png_path)
    parts = []
    for p in preds:
        t = p.get("text") if isinstance(p, dict) else getattr(p, "text", None)
        if t and t.strip():
            parts.append(t.strip())
    return "\n\n".join(parts)


def _run(pngs: list[bytes], prompt: str) -> str:
    _ensure_loaded()
    paths: list[str] = []
    try:
        for png in pngs:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
                tf.write(png)
                paths.append(tf.name)
        # native inference is not concurrency-safe on one GPU. The prewarm fires many requests at
        # once (fine for vLLM batching); here we serialize so they queue instead of racing the model
        # (OOM / corrupt state).
        with _INFER_LOCK:
            if _KIND == "nemotron_pipeline":
                return _infer_nemotron(paths[0], prompt)
            if _KIND == "deepseek_infer_multi" and len(paths) > 1:
                return _infer_deepseek_multi(paths, prompt)   # native multi-page
            return _infer_deepseek(paths[0], prompt)          # single image (deepseek_infer or 1-img multi)
    finally:
        for p in paths:
            try:
                os.unlink(p)
            except OSError:
                pass


def _extract(messages: list) -> tuple[list[bytes], str]:
    pngs: list[bytes] = []
    prompt = ""
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str):
            prompt = content
            continue
        for part in content or []:
            if part.get("type") == "text":
                prompt = part.get("text", "")
            elif part.get("type") == "image_url":
                url = (part.get("image_url") or {}).get("url", "")
                m = re.match(r"data:[^;]+;base64,(.*)", url, re.DOTALL)
                if m:
                    pngs.append(base64.b64decode(m.group(1)))   # collect ALL images (multi-page)
    return pngs, prompt


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):  # noqa: A002 — match base signature; stay quiet
        return

    def _json(self, code: int, obj: dict) -> None:
        payload = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/v1/models"):
            self._json(200, {"data": [{"id": _MODEL_ID, "object": "model"}]})
        elif self.path.rstrip("/").endswith("/health"):
            self._json(200, {"status": "ok"})
        else:
            self._json(404, {"error": "not_found"})

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/v1/chat/completions"):
            self._json(404, {"error": "not_found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            req = json.loads(self.rfile.read(length))
            pngs, prompt = _extract(req.get("messages", []))
            if not pngs:
                self._json(400, {"error": {"message": "no image"}})
                return
            text = _run(pngs, prompt or (_CFG.get("prompt") or ""))
        except Exception as exc:  # noqa: BLE001
            print(f"[native] inference error: {exc!r}", flush=True)
            self._json(500, {"error": {"message": repr(exc)}})
            return
        self._json(200, {
            "id": f"chatcmpl-{uuid.uuid4().hex}", "object": "chat.completion",
            "model": _MODEL_ID,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                         "finish_reason": "stop"}],
        })


def main() -> None:
    global _CFG, _KIND, _MODEL_ID
    ap = argparse.ArgumentParser()
    ap.add_argument("--models-file", required=True)
    ap.add_argument("--model-id", required=True)
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--preload", action="store_true", help="load weights at startup (else on first request)")
    args = ap.parse_args()
    _CFG = _load_cfg(args.models_file, args.model_id)
    _KIND = _CFG.get("native_kind", "")
    # registry id (args.model_id) may be a synthetic variant like "baidu/Unlimited-OCR__multi";
    # the actual HF repo to load comes from hf_id when present (both variants share one HF model).
    _MODEL_ID = _CFG.get("hf_id") or args.model_id
    if args.preload:
        _ensure_loaded()
    print(f"[native] serving {_MODEL_ID} ({_KIND}) on :{args.port}/v1/chat/completions", flush=True)
    ThreadingHTTPServer(("0.0.0.0", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
