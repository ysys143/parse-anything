#!/usr/bin/env python3
"""PaddleOCR-jobs-API shim for parse-anything `--primary paddle`.

parse-anything's paddle transcriber (src/parse_anything/pipeline/paddle_vlm.py) speaks
exactly three HTTP moves. This server emulates them, backed by a swappable OCR model:

  POST {base}/api/v2/ocr/jobs   multipart: fields `model`, `optionalPayload`, file `page.png`
        -> 200 {"data": {"jobId": "<id>"}}
  GET  {base}/api/v2/ocr/jobs/<id>
        -> 200 {"data": {"state": "processing|done|failed",
                          "resultUrl": {"jsonUrl": "<SHIM_PUBLIC_URL>/results/<id>.jsonl"}}}
  GET  {SHIM_PUBLIC_URL}/results/<id>.jsonl   (JSONL, one line)
        -> {"result": {"layoutParsingResults": [{"markdown": {"text": "<md>"}}]}}

The page image is submitted with NO prompt (paddle path drops grounding), so the shim injects
the per-model OCR prompt itself (from a prompts JSON or built-in defaults). Inference runs in a
worker thread; POST returns immediately and parse-anything polls.

Backend (env SHIM_BACKEND):
  stub    -> deterministic echo, for local contract tests (no GPU, no deps)
  openai  -> forward to a local OpenAI-compatible server (e.g. vLLM) at OPENAI_BASE

Env:
  SHIM_PORT          (default 8099)
  SHIM_PUBLIC_URL    (default http://127.0.0.1:$SHIM_PORT) — must be reachable by parse-anything
  SHIM_BACKEND       stub | openai   (default stub)
  SHIM_PROMPTS_FILE  optional JSON {"<model-id>": "<prompt>", "_default": "..."}
  OPENAI_BASE        (default http://127.0.0.1:8000/v1)  — used by the openai backend
  OPENAI_MODEL       served-model-name to call (default: whatever `model` field arrives)
  SHIM_MAX_TOKENS    (default 8192)
"""
from __future__ import annotations

import base64
import json
import os
import threading
import time
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("SHIM_PORT", "8099"))
PUBLIC_URL = os.environ.get("SHIM_PUBLIC_URL", f"http://127.0.0.1:{PORT}").rstrip("/")
BACKEND = os.environ.get("SHIM_BACKEND", "stub")
OPENAI_BASE = os.environ.get("OPENAI_BASE", "http://127.0.0.1:8000/v1").rstrip("/")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "")
MAX_TOKENS = int(os.environ.get("SHIM_MAX_TOKENS", "8192"))
# Optional: capture raw per-page model output + per-job metrics (the fair, assembly-independent signal).
RAW_DIR = os.environ.get("SHIM_RAW_DIR", "")
METRICS_FILE = os.environ.get("SHIM_METRICS_FILE", "")

_DEFAULT_PROMPT = ("Convert this document page to clean GitHub-flavored Markdown. "
                   "Render equations as LaTeX ($...$), tables as Markdown tables, and preserve reading order.")

# ASCII sentinels -> real glyphs, applied to prompts at send time (keeps models.json ASCII-clean).
_SENTINELS = {"{U2610}": chr(0x2610), "{U2611}": chr(0x2611)}


def _desentinel(text: str) -> str:
    for k, v in _SENTINELS.items():
        text = text.replace(k, v)
    return text


def _load_registry() -> dict[str, dict]:
    """models.json (SHIM_MODELS_FILE) -> {model_id: {prompt, extra_body, max_tokens}}."""
    reg: dict[str, dict] = {}
    path = os.environ.get("SHIM_MODELS_FILE")
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        for m in data.get("models", []):
            reg[m["id"]] = {
                "prompt": _desentinel(m.get("prompt") or _DEFAULT_PROMPT),
                "extra_body": m.get("extra_body") or {},
                "max_tokens": int(m.get("max_tokens") or MAX_TOKENS),
            }
    return reg


REGISTRY = _load_registry()


def _cfg_for(model: str) -> dict:
    return REGISTRY.get(model, {"prompt": _DEFAULT_PROMPT, "extra_body": {}, "max_tokens": MAX_TOKENS})


def _prompt_for(model: str) -> str:
    return _cfg_for(model)["prompt"]


# --- backends: png -> markdown text ------------------------------------------------

def _infer_stub(png: bytes, model: str) -> str:
    return f"# STUB TRANSCRIPTION\n\nmodel={model} bytes={len(png)} prompt={_prompt_for(model)!r}\n"


def _infer_openai(png: bytes, model: str) -> str:
    b64 = base64.b64encode(png).decode("ascii")
    served = OPENAI_MODEL or model
    cfg = _cfg_for(model)
    payload = {
        "model": served,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                {"type": "text", "text": cfg["prompt"]},
            ],
        }],
        "max_tokens": cfg["max_tokens"],
        "temperature": 0.0,
    }
    payload.update(cfg["extra_body"])  # model-specific knobs (ngram xargs, skip_special_tokens, top_p, ...)
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{OPENAI_BASE}/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer EMPTY"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=3600) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


_BACKENDS = {"stub": _infer_stub, "openai": _infer_openai}


def _infer(png: bytes, model: str) -> str:
    return _BACKENDS[BACKEND](png, model)


# --- job store ---------------------------------------------------------------------

_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()
_SEQ = 0


def _next_seq() -> int:
    global _SEQ
    with _LOCK:
        _SEQ += 1
        return _SEQ


def _sanitize(model: str) -> str:
    return "".join(c if c.isalnum() or c in "-._" else "_" for c in model)


def _record(model: str, seq: int, latency_ms: float, text: str | None, state: str) -> None:
    if RAW_DIR and text is not None:
        d = os.path.join(RAW_DIR, _sanitize(model))
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{seq:04d}.md"), "w", encoding="utf-8") as fh:
            fh.write(text)
    if METRICS_FILE:
        os.makedirs(os.path.dirname(METRICS_FILE) or ".", exist_ok=True)
        row = {"model": model, "seq": seq, "latency_ms": round(latency_ms, 1),
               "chars": len(text) if text is not None else 0, "state": state}
        with _LOCK:
            with open(METRICS_FILE, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")


def _run_job(job_id: str, png: bytes, model: str, seq: int) -> None:
    t0 = time.monotonic()
    try:
        text = _infer(png, model)
        dt = (time.monotonic() - t0) * 1000.0
        with _LOCK:
            _JOBS[job_id] = {"state": "done", "text": text}
        _record(model, seq, dt, text, "done")
    except Exception as exc:  # noqa: BLE001 — opaque to the client, logged locally
        dt = (time.monotonic() - t0) * 1000.0
        with _LOCK:
            _JOBS[job_id] = {"state": "failed", "error": repr(exc)}
        _record(model, seq, dt, None, "failed")
        print(f"[shim] job {job_id} seq={seq} FAILED: {exc!r}", flush=True)


# --- multipart parsing (targeted at parse-anything's exact body) -------------------

def _parse_multipart(body: bytes, content_type: str) -> dict[str, bytes]:
    marker = "boundary="
    i = content_type.find(marker)
    if i < 0:
        return {}
    boundary = content_type[i + len(marker):].strip().strip('"')
    sep = b"--" + boundary.encode("ascii")
    fields: dict[str, bytes] = {}
    for part in body.split(sep):
        if not part or part in (b"--\r\n", b"--"):
            continue
        head_end = part.find(b"\r\n\r\n")
        if head_end < 0:
            continue
        header = part[:head_end].decode("utf-8", "replace")
        value = part[head_end + 4:]
        if value.endswith(b"\r\n"):
            value = value[:-2]
        name = None
        for tok in header.split(";"):
            tok = tok.strip()
            if tok.startswith("name="):
                name = tok[5:].strip().strip('"')
        if name:
            fields[name] = value
    return fields


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _json(self, code: int, obj: dict) -> None:
        payload = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):  # noqa: A002 — match base signature; stay quiet
        return

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/api/v2/ocr/jobs"):
            self._json(404, {"error": "not_found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        fields = _parse_multipart(body, self.headers.get("Content-Type", ""))
        png = fields.get("file")
        model = (fields.get("model") or b"").decode("utf-8", "replace") or OPENAI_MODEL or "unknown"
        if not png:
            self._json(400, {"error": "no_file"})
            return
        job_id = uuid.uuid4().hex
        seq = _next_seq()
        with _LOCK:
            _JOBS[job_id] = {"state": "processing"}
        threading.Thread(target=_run_job, args=(job_id, png, model, seq), daemon=True).start()
        self._json(200, {"data": {"jobId": job_id}})

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path.rstrip("/") == "/health":
            self._json(200, {"status": "ok"})
            return
        if path.startswith("/results/") and path.endswith(".jsonl"):
            job_id = path[len("/results/"):-len(".jsonl")]
            with _LOCK:
                job = _JOBS.get(job_id)
            if not job or job.get("state") != "done":
                self._json(404, {"error": "not_ready"})
                return
            line = json.dumps({"result": {"layoutParsingResults": [{"markdown": {"text": job["text"]}}]}})
            payload = (line + "\n").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        # job status:  .../api/v2/ocr/jobs/<id>
        if "/api/v2/ocr/jobs/" in path:
            job_id = path.rsplit("/", 1)[-1]
            with _LOCK:
                job = _JOBS.get(job_id)
            if not job:
                self._json(404, {"error": "unknown_job"})
                return
            state = job["state"]
            data = {"state": state}
            if state == "done":
                data["resultUrl"] = {"jsonUrl": f"{PUBLIC_URL}/results/{job_id}.jsonl"}
            self._json(200, {"data": data})
            return
        self._json(404, {"error": "not_found"})


def main() -> None:
    print(f"[shim] backend={BACKEND} port={PORT} public={PUBLIC_URL} openai_base={OPENAI_BASE} "
          f"model={OPENAI_MODEL or '(from request)'}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
