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
    seconds: float = 0.0
    error: str = ""

    @property
    def n_pages(self) -> int:
        return len(self.pages)

    @property
    def n_chars(self) -> int:
        return sum(len(p) for p in self.pages)


# ---------------------------------------------------------------------------
# 1. original opendataloader-pdf (deterministic Java extractor, ALONE)
# ---------------------------------------------------------------------------
def run_odl(pdf: Path, workdir: Path) -> RunResult:
    workdir.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    try:
        subprocess.run(
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
    return RunResult("odl", pdf.stem, pages=pages, seconds=dt)


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

    settings = load_settings()
    if not (settings.paddle_api_key and settings.paddle_base_url):
        return RunResult("paddle", pdf.stem, status="error", error="paddle_not_configured")
    client = ProviderHttpClient(SafeTransport(UrllibTransport()))
    transcribe = make_transcriber(
        client, base_url=settings.paddle_base_url, token=settings.paddle_api_key,
        model=settings.paddle_model or "PaddleOCR-VL-1.6",
    )

    doc = pdfium.PdfDocument(str(pdf))
    pages: list[str] = []
    t0 = time.monotonic()
    try:
        for i in range(len(doc)):
            bitmap = doc[i].render(scale=float(dpi) / 72.0)  # type: ignore[arg-type]
            png = _pil_png(bitmap.to_pil())
            md = transcribe(png)
            pages.append(md or "")
            (workdir / f"{i:04d}.md").write_text(md or "", encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        return RunResult("paddle", pdf.stem, pages=pages, status="error",
                         error=f"{type(exc).__name__}:{exc}", seconds=time.monotonic() - t0)
    return RunResult("paddle", pdf.stem, pages=pages, seconds=time.monotonic() - t0)


def _pil_png(img) -> bytes:
    import io
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 3. parse-anything (full pipeline)
# ---------------------------------------------------------------------------
def run_parse_anything(pdf: Path, workdir: Path, *, live: bool) -> RunResult:
    """Full pipeline via the CLI. In dry-run we still run it in DETERMINISTIC mode (ODL grounding
    only, no VLM calls) so parse-anything's structure layer is exercised without API spend; the
    live run uses --mode det_vlm --primary paddle (the real orchestration)."""
    workdir.mkdir(parents=True, exist_ok=True)
    mode_args = (["--mode", "det_vlm", "--primary", "paddle"] if live else ["--no-vlm"])
    t0 = time.monotonic()
    try:
        subprocess.run(
            [str(PY), "-m", "parse_anything.cli", "--pdf", str(pdf), "--out", str(workdir),
             "--source-id", "bench", "--force", *mode_args],
            check=True, capture_output=True, timeout=3600, cwd=str(REPO),
            env={**os.environ, "PYTHONPATH": str(REPO / "src")},
        )
    except subprocess.TimeoutExpired:
        return RunResult("pa", pdf.stem, status="error", error="timeout")
    except subprocess.CalledProcessError as exc:
        return RunResult("pa", pdf.stem, status="error",
                         error=f"pa_exit_{exc.returncode}:{exc.stderr.decode('utf-8','replace')[-300:]}")
    dt = time.monotonic() - t0
    # parse-anything writes <out>/bench/<document_id>/document.md
    mds = sorted(glob.glob(str(workdir / "**/document.md"), recursive=True))
    if not mds:
        return RunResult("pa", pdf.stem, status="error", error="pa_no_document_md", seconds=dt)
    text = Path(mds[0]).read_text(encoding="utf-8", errors="replace")
    status = "ok" if live else "deterministic_only"
    return RunResult("pa", pdf.stem, pages=_split_pages(text), status=status, seconds=dt)


def result_to_dict(r: RunResult) -> dict:
    return {"parser": r.parser, "doc": r.doc, "status": r.status, "seconds": round(r.seconds, 2),
            "n_pages": r.n_pages, "n_chars": r.n_chars, "error": r.error}
