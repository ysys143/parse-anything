#!/usr/bin/env python3
"""Three parser runners for the head-to-head comparison.

Each runner takes a PDF and produces per-page markdown text (list[str], one per page) plus a
small dict of metadata (latency, char count, status). The three are deliberately layered:

  odl        -- original opendataloader-pdf, the deterministic Java extractor ALONE
                (java -jar ...-cli.jar <pdf> --format markdown). No VLM, no orchestration.
  paddle     -- PaddleOCR-VL-1.6 ALONE: rasterize each page, call the hosted jobs API,
                concatenate raw per-page transcription. No deterministic grounding.
  pa         -- parse-anything, the FULL pipeline (CLI --mode det_vlm --primary paddle):
                ODL grounding + PaddleOCR-VL transcription + value-oracle gate + structure.

The point of the benchmark is the MARGINAL value of `pa` over its two raw ingredients.
"""
from __future__ import annotations

import glob
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
ODL_JAR = REPO / ".local/workspace/opendataloader-pdf/java/opendataloader-pdf-cli/target/opendataloader-pdf-cli-0.0.0.jar"
PY = REPO / ".venv/bin/python"


@dataclass
class RunResult:
    parser: str
    doc: str
    pages: list[str] = field(default_factory=list)   # per-page markdown
    status: str = "ok"
    seconds: float = 0.0                             # wall-clock (COST: latency)
    cpu_s: float = 0.0                               # user+sys CPU seconds (COST: compute)
    peak_rss_mb: float = 0.0                         # peak resident set (COST: memory)
    vlm_calls: int = 0                               # VLM API invocations (COST: $ proxy)
    error: str = ""

    @property
    def n_pages(self) -> int:
        return len(self.pages)

    @property
    def n_chars(self) -> int:
        return sum(len(p) for p in self.pages)


def _timed_subprocess(cmd: list[str], **kw) -> tuple[subprocess.CompletedProcess, float, float]:
    """Run cmd under `/usr/bin/time -l` and return (completed, cpu_s, peak_rss_mb).

    macOS `/usr/bin/time -l` reports peak RSS in BYTES and user/sys in seconds on stderr. We wrap
    so ODL (JVM) and parse-anything (JVM+Python) are measured for compute/memory cost, not just
    wall-clock. If /usr/bin/time is unavailable the caller still gets the process; cost = 0."""
    wrapped = ["/usr/bin/time", "-l", *cmd] if Path("/usr/bin/time").exists() else cmd
    proc = subprocess.run(wrapped, **kw)
    cpu_s, peak_rss_mb = 0.0, 0.0
    if wrapped is not cmd and proc.stderr:
        err = proc.stderr.decode("utf-8", "replace")
        import re
        if (m := re.search(r"([\d.]+)\s+real\s+([\d.]+)\s+user\s+([\d.]+)\s+sys", err)):
            cpu_s = float(m.group(2)) + float(m.group(3))
        if (m := re.search(r"(\d+)\s+maximum resident set size", err)):
            peak_rss_mb = round(int(m.group(1)) / (1024 * 1024), 1)  # macOS: bytes -> MB
    return proc, cpu_s, peak_rss_mb


# ---------------------------------------------------------------------------
# 1. original opendataloader-pdf (deterministic Java extractor, ALONE)
# ---------------------------------------------------------------------------
def run_odl(pdf: Path, workdir: Path) -> RunResult:
    workdir.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    try:
        _, cpu_s, rss = _timed_subprocess(
            ["java", "-jar", str(ODL_JAR), str(pdf), "--format", "markdown", "-o", str(workdir)],
            check=True, capture_output=True, timeout=1200,
        )
    except FileNotFoundError:
        return RunResult("odl", pdf.stem, status="error", error="java_not_found")
    except subprocess.TimeoutExpired:
        return RunResult("odl", pdf.stem, status="error", error="timeout")
    except subprocess.CalledProcessError as exc:
        return RunResult("odl", pdf.stem, status="error",
                         error=f"odl_exit_{exc.returncode}:{exc.stderr.decode('utf-8','replace')[:200]}")
    dt = time.monotonic() - t0
    # ODL writes <stem>.md (single markdown file with page separators, or per-page). Locate it.
    mds = sorted(glob.glob(str(workdir / "**/*.md"), recursive=True))
    if not mds:
        return RunResult("odl", pdf.stem, status="error", error="odl_no_md_output", seconds=dt)
    text = Path(mds[0]).read_text(encoding="utf-8", errors="replace")
    pages = _split_pages(text)
    # odl is deterministic-only: vlm_calls=0 by construction (that IS its cost advantage).
    return RunResult("odl", pdf.stem, pages=pages, seconds=dt, cpu_s=cpu_s, peak_rss_mb=rss, vlm_calls=0)


def _split_pages(text: str) -> list[str]:
    """ODL markdown may or may not carry page separators; fall back to a single 'page'."""
    for sep in ("\n\f", "\f", "\n---\n", "<!-- page"):
        if sep in text:
            parts = [p.strip() for p in text.split(sep)]
            return [p for p in parts if p]
    return [text.strip()] if text.strip() else []


# ---------------------------------------------------------------------------
# 2. PaddleOCR-VL-1.6 (document VLM, ALONE)
# ---------------------------------------------------------------------------
def run_paddle(pdf: Path, workdir: Path, *, dpi: int = 150, live: bool) -> RunResult:
    """Rasterize each page and transcribe via the hosted PaddleOCR-VL jobs API.

    live=False -> DRY RUN: skip network, emit an empty result so the harness is exercisable
    without spending API quota. live=True -> real calls (reuses parse_anything.providers +
    pipeline.paddle_vlm so the exact same client/prompt/model as the full pipeline is used).
    """
    workdir.mkdir(parents=True, exist_ok=True)
    if not live:
        return RunResult("paddle", pdf.stem, status="dry_run", error="paddle_skipped_dry_run")

    sys.path.insert(0, str(REPO / "src"))
    import pypdfium2 as pdfium  # noqa: E402
    from parse_anything.config import load_settings  # noqa: E402
    from parse_anything.pipeline.paddle_vlm import make_transcriber  # noqa: E402
    from parse_anything.providers import ProviderHttpClient, SafeTransport, UrllibTransport  # noqa: E402

    # load_settings resolves .env RELATIVE to cwd; run_compare runs from benchmarks/three-way/, so
    # point it at the repo-root .env explicitly (same one the pa CLI subprocess picks up via cwd=REPO).
    settings = load_settings(env_file=REPO / ".env")
    if not (settings.paddle_api_key and settings.paddle_base_url):
        return RunResult("paddle", pdf.stem, status="error", error="paddle_not_configured")
    client = ProviderHttpClient(SafeTransport(UrllibTransport()))
    transcribe = make_transcriber(
        client, base_url=settings.paddle_base_url, token=settings.paddle_api_key,
        model=settings.paddle_model or "PaddleOCR-VL-1.6",
    )

    doc = pdfium.PdfDocument(str(pdf))
    pages: list[str] = []
    calls, failed = 0, 0
    t0 = time.monotonic()
    for i in range(len(doc)):
        bitmap = doc[i].render(scale=float(dpi) / 72.0)  # type: ignore[arg-type]
        png = _pil_png(bitmap.to_pil())
        md = ""
        # Per-page retry with backoff: the hosted API returns http_0 (dropped connection) under
        # rapid back-to-back load. A single page failing must NOT abandon the rest of the column.
        for attempt in range(3):
            try:
                md = transcribe(png) or ""
                break
            except Exception as exc:  # noqa: BLE001
                if attempt == 2:
                    failed += 1
                    md = f"<!-- paddle_page_error: {type(exc).__name__}:{exc} -->"
                else:
                    time.sleep(2.0 * (attempt + 1))   # 2s, 4s backoff before retry
        calls += 1                       # paddle-alone: one VLM call per page, ungated
        pages.append(md)
        (workdir / f"{i:04d}.md").write_text(md, encoding="utf-8")
    status = "ok" if failed == 0 else ("partial" if failed < len(doc) else "error")
    err = "" if failed == 0 else f"{failed}/{len(doc)} pages failed"
    return RunResult("paddle", pdf.stem, pages=pages, seconds=time.monotonic() - t0,
                     vlm_calls=calls, status=status, error=err)


def _pil_png(img) -> bytes:
    import io
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 3. parse-anything (full pipeline)
# ---------------------------------------------------------------------------
def run_parse_anything(pdf: Path, workdir: Path, *, live: bool, diagnose: bool = False,
                       name: str = "pa") -> RunResult:
    """Full pipeline via the CLI.

    live=False  -> DETERMINISTIC (--no-vlm): structure layer only, no API spend.
    live=True   -> det_vlm --primary paddle: VLM on EVERY page (no document-level triage).
    diagnose=True -> --diagnose --primary paddle: parse-anything runs D-1 diagnosis FIRST and picks
        the mode per document. This is its NATIVE operating point: born-digital should route to
        deterministic (VLM 0 calls, ~ODL cost); scan should route to det_vlm. `name` labels the
        results dir/row so the triaged variant can sit beside the forced-VLM one."""
    workdir.mkdir(parents=True, exist_ok=True)
    if diagnose:
        mode_args = ["--diagnose", "--primary", "paddle"]
    elif live:
        mode_args = ["--mode", "det_vlm", "--primary", "paddle"]
    else:
        mode_args = ["--no-vlm"]
    t0 = time.monotonic()
    try:
        proc, cpu_s, rss = _timed_subprocess(
            [str(PY), "-m", "parse_anything.cli", "--pdf", str(pdf), "--out", str(workdir),
             "--source-id", "bench", "--force", *mode_args],
            check=True, capture_output=True, timeout=3600, cwd=str(REPO),
            env={**os.environ, "PYTHONPATH": str(REPO / "src")},
        )
    except subprocess.TimeoutExpired:
        return RunResult(name, pdf.stem, status="error", error="timeout")
    except subprocess.CalledProcessError as exc:
        return RunResult(name, pdf.stem, status="error",
                         error=f"pa_exit_{exc.returncode}:{exc.stderr.decode('utf-8','replace')[-300:]}")
    dt = time.monotonic() - t0
    # The CLI prints e.g. "pages=46 mode=det_vlm doc=... vlm_pages=7 flagged=2". vlm_pages = the
    # VALUE-ORACLE-GATED VLM invocation count -- parse-anything's core cost lever vs paddle-alone.
    out = (proc.stdout or b"").decode("utf-8", "replace")
    vlm_calls = 0
    if (m := __import__("re").search(r"vlm_pages=(\d+)", out)):
        vlm_calls = int(m.group(1))
    # parse-anything writes <out>/bench/<document_id>/document.md
    mds = sorted(glob.glob(str(workdir / "**/document.md"), recursive=True))
    if not mds:
        return RunResult(name, pdf.stem, status="error", error="pa_no_document_md", seconds=dt)
    text = Path(mds[0]).read_text(encoding="utf-8", errors="replace")
    status = ("triaged" if diagnose else "ok") if (live or diagnose) else "deterministic_only"
    return RunResult(name, pdf.stem, pages=_split_pages(text), status=status, seconds=dt,
                     cpu_s=cpu_s, peak_rss_mb=rss, vlm_calls=vlm_calls)


def result_to_dict(r: RunResult) -> dict:
    return {"parser": r.parser, "doc": r.doc, "status": r.status, "seconds": round(r.seconds, 2),
            "cpu_s": round(r.cpu_s, 2), "peak_rss_mb": r.peak_rss_mb, "vlm_calls": r.vlm_calls,
            "n_pages": r.n_pages, "n_chars": r.n_chars, "error": r.error}
