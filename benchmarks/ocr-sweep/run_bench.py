#!/usr/bin/env python3
"""Orchestrate the 7-model parse-anything OCR sweep on ONE L4 (runs GPU-side).

For each model in models.json, sequentially (only one model in VRAM at a time):
  1. start its runner  -> OpenAI /v1 on :8000
       vllm_docker: docker run <image> --model <id> --served-model-name model <serve_args>
       native:      python native_wrapper.py --model-id <id> --port 8000 --preload
  2. wait for /v1/models to answer (health)
  3. for each test doc (born-digital + scanned):
       start shim (openai backend, raw+metrics dirs for THIS model/doc) on :8099
       run  parse-anything --primary paddle  against the shim  -> layered artifacts
       stop shim
  4. stop the runner, free VRAM, next model.

One model failing (OOM, bad vLLM version, ...) is recorded and skipped -- the sweep continues.
Results tree:  <results>/<model>/{out_born,out_scan,raw_born,raw_scan,metrics_*.jsonl}
               <results>/summary.jsonl   (one line per model/doc)

Usage (on the VM):
  python run_bench.py --models-file models.json \
      --born document.pdf --scan scan.pdf --results results/ \
      [--only deepseek-ai/DeepSeek-OCR,zai-org/GLM-OCR] [--health-timeout 900]
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import signal
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SHIM = os.path.join(HERE, "shim_server.py")
NATIVE = os.path.join(HERE, "native_wrapper.py")
CONTAINER = "pa_ocr_runner"          # fixed name so we can always docker rm -f it
RUNNER_PORT = 8000
SHIM_PORT = 8099


def log(msg: str) -> None:
    print(f"[bench] {msg}", flush=True)


def _http_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return 200 <= r.status < 500
    except Exception:
        return False


def wait_health(url: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _http_ok(url):
            return True
        time.sleep(3)
    return False


def sanitize(model_id: str) -> str:
    return "".join(c if c.isalnum() or c in "-._" else "_" for c in model_id)


# --- runner lifecycle --------------------------------------------------------------

def start_runner(m: dict, hf_cache: str) -> subprocess.Popen | None:
    """Start the model server on RUNNER_PORT. Returns a Popen for native runners
    (docker runs detached and is torn down by name)."""
    backend = m["backend"]
    if backend == "vllm_docker":
        subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
        cmd = [
            "docker", "run", "-d", "--name", CONTAINER, "--gpus", "all",
            "--ipc=host", "-p", f"{RUNNER_PORT}:8000",
            "-v", f"{hf_cache}:/root/.cache/huggingface",
            m["vllm_image"], "--model", m["id"],
            "--served-model-name", m.get("served_name", "model"),
        ]
        cmd += list(m.get("serve_args", []))
        if m.get("trust_remote_code"):
            cmd += ["--trust-remote-code"]
        log("docker: " + " ".join(shlex.quote(c) for c in cmd))
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            log(f"docker run FAILED: {r.stderr.strip()[:400]}")
            return None
        return None
    if backend == "custom_docker":
        subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
        tag, dockerfile = m["build_image"], os.path.join(HERE, m["dockerfile"])
        log(f"docker build {tag} (-f {m['dockerfile']}) -- first build pulls the base image")
        b = subprocess.run(["docker", "build", "-t", tag, "-f", dockerfile, HERE],
                           capture_output=True, text=True)
        if b.returncode != 0:
            log(f"docker build FAILED: {b.stderr.strip()[-600:]}")
            return None
        cmd = [
            "docker", "run", "-d", "--name", CONTAINER, "--gpus", "all",
            "--ipc=host", "-p", f"{RUNNER_PORT}:8000",
            "-v", f"{hf_cache}:/root/.cache/huggingface",
            tag, *list(m.get("docker_run_cmd", [])),
        ]
        log("docker: " + " ".join(shlex.quote(c) for c in cmd))
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            log(f"docker run FAILED: {r.stderr.strip()[:400]}")
            return None
        return None
    if backend == "native":
        cmd = [sys.executable, NATIVE, "--models-file", m["_models_file"],
               "--model-id", m["id"], "--port", str(RUNNER_PORT), "--preload"]
        log("native: " + " ".join(shlex.quote(c) for c in cmd))
        return subprocess.Popen(cmd)
    log(f"unknown backend: {backend}")
    return None


def stop_runner(m: dict, proc: subprocess.Popen | None) -> None:
    if m["backend"] in ("vllm_docker", "custom_docker"):
        subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
    elif proc is not None:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()


def runner_logs(m: dict) -> str:
    if m["backend"] in ("vllm_docker", "custom_docker"):
        r = subprocess.run(["docker", "logs", "--tail", "40", CONTAINER], capture_output=True, text=True)
        return (r.stdout or "") + (r.stderr or "")
    return "(native runner; see stderr)"


# --- shim + parse-anything per doc -------------------------------------------------

def run_doc(model_id: str, pdf: str, out_dir: str, raw_dir: str, metrics_file: str,
            served: str, parse_extra: list[str]) -> dict:
    env = dict(os.environ)
    env.update({
        "SHIM_BACKEND": "openai", "SHIM_PORT": str(SHIM_PORT),
        "SHIM_PUBLIC_URL": f"http://127.0.0.1:{SHIM_PORT}",
        "OPENAI_BASE": f"http://127.0.0.1:{RUNNER_PORT}/v1", "OPENAI_MODEL": served,
        "SHIM_MODELS_FILE": env["_MODELS_FILE"], "SHIM_RAW_DIR": raw_dir,
        "SHIM_METRICS_FILE": metrics_file,
    })
    shim = subprocess.Popen([sys.executable, SHIM], env=env)
    try:
        if not wait_health(f"http://127.0.0.1:{SHIM_PORT}/api/v2/ocr/jobs/x", 20):
            log("shim did not come up")
        t0 = time.monotonic()
        penv = dict(os.environ)
        penv.update({
            "GEMINI_API_KEY": "dummy-unused-on-paddle-path", "PADDLE_API_KEY": "dummy",
            "PADDLE_BASE_URL": f"http://127.0.0.1:{SHIM_PORT}", "PADDLE_MODEL": model_id,
        })
        cmd = ["parse-anything", "--pdf", pdf, "--out", out_dir, "--source-id", sanitize(model_id),
               "--mode", "det_vlm", "--primary", "paddle", *parse_extra]
        r = subprocess.run(cmd, env=penv, capture_output=True, text=True)
        dt = time.monotonic() - t0
        ok = r.returncode == 0
        tail = (r.stdout or "").strip().splitlines()[-1:] or [(r.stderr or "").strip()[-300:]]
        log(f"parse-anything {'OK' if ok else 'FAIL'} ({dt:.0f}s): {tail[0][:200]}")
        return {"ok": ok, "seconds": round(dt, 1), "tail": tail[0][:300]}
    finally:
        shim.send_signal(signal.SIGINT)
        try:
            shim.wait(timeout=10)
        except subprocess.TimeoutExpired:
            shim.kill()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models-file", required=True)
    ap.add_argument("--born", required=True, help="born-digital test PDF (document.pdf)")
    ap.add_argument("--scan", default=None, help="image-only stress PDF (scan.pdf)")
    ap.add_argument("--results", default="results")
    ap.add_argument("--only", default=None, help="comma-separated model ids to run (default all)")
    ap.add_argument("--health-timeout", type=float, default=900.0, help="seconds to wait for runner /v1")
    ap.add_argument("--hf-cache", default=os.path.expanduser("~/.cache/huggingface"))
    ap.add_argument("--parse-extra", default="--no-chunks", help="extra parse-anything flags")
    args = ap.parse_args()

    with open(args.models_file, encoding="utf-8") as fh:
        models = json.load(fh)["models"]
    only = set(x.strip() for x in args.only.split(",")) if args.only else None
    if only:
        models = [m for m in models if m["id"] in only]
    os.environ["_MODELS_FILE"] = os.path.abspath(args.models_file)

    docs = [("born", args.born)] + ([("scan", args.scan)] if args.scan else [])
    parse_extra = shlex.split(args.parse_extra)
    os.makedirs(args.results, exist_ok=True)
    summary_path = os.path.join(args.results, "summary.jsonl")

    for m in models:
        m["_models_file"] = os.path.abspath(args.models_file)
        mid = m["id"]
        mdir = os.path.join(args.results, sanitize(mid))
        os.makedirs(mdir, exist_ok=True)
        log(f"===== {mid} ({m['backend']}, {m.get('params','?')}) =====")
        proc = start_runner(m, args.hf_cache)
        served = m.get("served_name", "model")
        healthy = wait_health(f"http://127.0.0.1:{RUNNER_PORT}/v1/models", args.health_timeout)
        if not healthy:
            log(f"runner UNHEALTHY after {args.health_timeout:.0f}s -- skipping. logs:\n{runner_logs(m)[:800]}")
            _append(summary_path, {"model": mid, "status": "runner_unhealthy"})
            stop_runner(m, proc)
            continue
        log("runner healthy")
        for tag, pdf in docs:
            res = run_doc(
                mid, pdf, os.path.join(mdir, f"out_{tag}"), os.path.join(mdir, f"raw_{tag}"),
                os.path.join(mdir, f"metrics_{tag}.jsonl"), served, parse_extra,
            )
            _append(summary_path, {"model": mid, "doc": tag, **res})
        stop_runner(m, proc)
        log(f"{mid} done; VRAM freed")

    log(f"SWEEP COMPLETE -> {summary_path}")
    return 0


def _append(path: str, row: dict) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
