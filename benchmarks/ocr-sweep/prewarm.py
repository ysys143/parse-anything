#!/usr/bin/env python3
"""Batched pre-transcription: render ALL pages and fire them CONCURRENTLY at the vLLM server so
its continuous batching keeps the GPU busy (vs parse-anything's one-page-at-a-time, batch=1).

Writes, for one (model, doc):
  raw_<doc>/<sanitized-model>/NNNN.md   one file per page (1-based) = the model's transcription
  <cache_file>  JSON: {"texts": ["page0", "page1", ...], "meta": {...}}  -> replayed by the shim
  <metrics_file>  one JSONL row/page (per-request latency) + a final {"seq":0,...,"wall_s":T} total row

Renders identically to parse-anything (pypdfium2 render(scale=2.0) -> PNG), so the model sees the
same input. The shim later replays cache[i] for parse-anything's i-th sequential page request.

Usage:
  python prewarm.py --models-file models.json --model-id <id> --pdf doc.pdf \
      --openai-base http://127.0.0.1:8000/v1 --served model \
      --raw-dir raw_born --cache-file cache_born.json --metrics-file metrics_born.jsonl \
      [--concurrency 16]
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import pypdfium2 as pdfium

_SENTINELS = {"{U2610}": chr(0x2610), "{U2611}": chr(0x2611)}


def _desentinel(t: str) -> str:
    for k, v in _SENTINELS.items():
        t = t.replace(k, v)
    return t


def load_cfg(models_file: str, model_id: str) -> dict:
    with open(models_file, encoding="utf-8") as fh:
        for m in json.load(fh)["models"]:
            if m["id"] == model_id:
                return m
    raise SystemExit(f"model not in registry: {model_id}")


def render_all_pngs(pdf: str, scale: float = 2.0) -> list[bytes]:
    """Render every page to PNG bytes, SEQUENTIALLY in the caller thread. pypdfium2 is not
    thread-safe, so we must not render concurrently (that segfaults the whole process); rendering
    is cheap, only the network transcription needs concurrency. Matches render_page_png(scale=2.0)."""
    doc = pdfium.PdfDocument(pdf)
    out: list[bytes] = []
    for i in range(len(doc)):
        buf = io.BytesIO()
        doc[i].render(scale=scale).to_pil().save(buf, format="PNG")
        out.append(buf.getvalue())
    return out


def transcribe(png: bytes, base: str, served: str, prompt: str, extra: dict, max_tokens: int) -> str:
    b64 = base64.b64encode(png).decode("ascii")
    payload = {
        "model": served,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            {"type": "text", "text": prompt},
        ]}],
        "max_tokens": max_tokens, "temperature": 0.0,
    }
    payload.update(extra)
    req = urllib.request.Request(f"{base.rstrip('/')}/chat/completions",
                                data=json.dumps(payload).encode(),
                                headers={"Content-Type": "application/json", "Authorization": "Bearer EMPTY"},
                                method="POST")
    with urllib.request.urlopen(req, timeout=3600) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def transcribe_multi(pngs: list[bytes], base: str, served: str, prompt: str, extra: dict,
                     max_tokens: int) -> str:
    """whole-doc mode: send ALL page images in ONE request (multiple image_url parts) so the model
    transcribes the whole document in a single native multi-page pass (Unlimited-OCR infer_multi)."""
    content: list[dict] = [
        {"type": "image_url",
         "image_url": {"url": f"data:image/png;base64,{base64.b64encode(p).decode('ascii')}"}}
        for p in pngs
    ]
    content.append({"type": "text", "text": prompt})
    payload = {"model": served, "messages": [{"role": "user", "content": content}],
               "max_tokens": max_tokens, "temperature": 0.0}
    payload.update(extra)
    req = urllib.request.Request(f"{base.rstrip('/')}/chat/completions",
                                data=json.dumps(payload).encode(),
                                headers={"Content-Type": "application/json", "Authorization": "Bearer EMPTY"},
                                method="POST")
    with urllib.request.urlopen(req, timeout=7200) as r:   # whole-doc pass is slow; generous timeout
        return json.loads(r.read())["choices"][0]["message"]["content"]


def sanitize(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-._" else "_" for c in s)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models-file", required=True)
    ap.add_argument("--model-id", required=True)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--openai-base", required=True)
    ap.add_argument("--served", default="model")
    ap.add_argument("--raw-dir", required=True)
    ap.add_argument("--cache-file", required=True)
    ap.add_argument("--metrics-file", required=True)
    ap.add_argument("--concurrency", type=int, default=16)
    ap.add_argument("--pipeline", choices=["per_page", "whole_doc"], default="per_page",
                    help="per_page: one request/page (default); whole_doc: all pages in ONE request "
                         "(native multi-page, e.g. Unlimited-OCR infer_multi)")
    args = ap.parse_args()

    cfg = load_cfg(args.models_file, args.model_id)
    prompt = _desentinel(cfg.get("prompt") or "Convert this document page to Markdown.")
    extra = cfg.get("extra_body") or {}
    max_tokens = int(cfg.get("max_tokens") or 8192)
    pngs = render_all_pngs(args.pdf)          # SEQUENTIAL render (pypdfium2 not thread-safe -> segfault)
    n = len(pngs)
    raw_model_dir = os.path.join(args.raw_dir, sanitize(args.model_id))
    os.makedirs(raw_model_dir, exist_ok=True)
    os.makedirs(os.path.dirname(args.metrics_file) or ".", exist_ok=True)

    if args.pipeline == "whole_doc":
        # ONE multi-image request -> one document. Written as a single 0001.md (the scorer concatenates
        # every *.md in the dir, so one file == whole doc). No cache/parse-anything step for this path.
        t0 = time.monotonic()
        try:
            doc_text = transcribe_multi(pngs, args.openai_base, args.served, prompt, extra, max_tokens)
            state = "done"
        except Exception as exc:  # noqa: BLE001
            doc_text, state = "", f"failed:{type(exc).__name__}"
        wall = time.monotonic() - t0
        with open(os.path.join(raw_model_dir, "0001.md"), "w", encoding="utf-8") as fh:
            fh.write(doc_text)
        with open(args.metrics_file, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"model": args.model_id, "seq": 1, "latency_ms": round(wall * 1000, 1),
                                 "chars": len(doc_text), "state": state,
                                 "pipeline": "whole_doc", "pages": n}) + "\n")
        with open(args.cache_file, "w", encoding="utf-8") as fh:
            json.dump({"texts": [doc_text]}, fh)
        print(f"[prewarm] {args.model_id}: whole-doc {n} pages -> {len(doc_text)} chars "
              f"in {wall:.0f}s [{state}] -> {args.cache_file}")
        return

    def work(i: int) -> tuple[int, str, float, str]:
        t0 = time.monotonic()
        try:
            text = transcribe(pngs[i], args.openai_base, args.served, prompt, extra, max_tokens)
            return i, text, (time.monotonic() - t0) * 1000, "done"
        except Exception as exc:  # noqa: BLE001
            return i, "", (time.monotonic() - t0) * 1000, f"failed:{type(exc).__name__}"

    texts: list[str] = [""] * n
    rows: list[dict] = []
    wall0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        for i, text, ms, state in ex.map(work, range(n)):
            texts[i] = text
            with open(os.path.join(raw_model_dir, f"{i + 1:04d}.md"), "w", encoding="utf-8") as fh:
                fh.write(text)
            rows.append({"model": args.model_id, "seq": i + 1, "latency_ms": round(ms, 1),
                         "chars": len(text), "state": state})
    wall = time.monotonic() - wall0

    rows.sort(key=lambda r: r["seq"])
    with open(args.metrics_file, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
        fh.write(json.dumps({"model": args.model_id, "seq": 0, "batched_wall_s": round(wall, 1),
                             "pages": n, "throughput_pages_per_min": round(n / (wall / 60), 2)}) + "\n")
    with open(args.cache_file, "w", encoding="utf-8") as fh:
        json.dump({"texts": texts}, fh)
    ok = sum(1 for r in rows if r["state"] == "done")
    print(f"[prewarm] {args.model_id}: {ok}/{n} pages in {wall:.0f}s "
          f"({n / (wall / 60):.1f} pages/min) -> {args.cache_file}")


if __name__ == "__main__":
    main()
