"""B-3 proxy: minimal ODL hybrid backend (stdlib http.server, pure VLM).

ODL (``--hybrid=docling-fast --hybrid-url=http://host:port``) POSTs ``multipart/form-data`` with
``files`` (the whole PDF, filename ``document.pdf``) and ``page_ranges`` (a single ``"min-max"``
string) to ``/v1/convert/file``, and probes ``/health`` first. We render the requested pages,
transcribe each with a VLM (fixed prompt), and return a DoclingDocument envelope ODL absorbs.

stdlib only (no FastAPI) — two endpoints, manual multipart parsing — matching the repo's
minimal-dependency / license-clean posture. Pages are never dropped silently: a per-page failure
becomes a ``failed_pages`` entry and ``partial_success`` (or ``failure`` if every page failed).

B-4 augments this proxy with deterministic grounding + guards (see ``det_aug``); B-3 is the bare
transcription path.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

import pypdfium2 as pdfium

from odl_vl.pipeline.render import render_page_png
from odl_vl_track_b.docling_out import PageBlock, build_docling_document, build_response
from odl_vl_track_b.vlm_client import Transcriber, transcriber_from_env

logger = logging.getLogger("odl_vl_track_b.proxy")

# Fixed corpus-level prompt (B-3). ODL cannot carry a per-document prompt; the proxy owns it.
DEFAULT_PROMPT = (
    "Transcribe this page to clean, faithful GitHub-Flavored Markdown. Preserve reading order, "
    "headings, lists, and tables (use Markdown table syntax). Do NOT invent values or text that "
    "is not visible. Output only the Markdown, no preamble."
)

# Pre-hook: (pdf_path, page_index_0based, page_png, base_prompt) -> (prompt, extra_flags). Runs
# before transcription. B-3 uses the identity hook; B-4 injects deterministic grounding here.
PageHook = Callable[[str, int, bytes, str], tuple[str, tuple[str, ...]]]
# Post-hook: (pdf_path, page_index_0based, markdown) -> extra_flags. Runs after transcription.
# B-4 runs the value-oracle / arithmetic guards here. Keeps the HTTP loop variant-agnostic.
PostHook = Callable[[str, int, str], tuple[str, ...]]


def _identity_hook(_pdf_path: str, _page_index: int, _png: bytes, prompt: str) -> tuple[str, tuple[str, ...]]:
    return prompt, ()


def _no_post(_pdf_path: str, _page_index: int, _markdown: str) -> tuple[str, ...]:
    return ()


def parse_multipart(body: bytes, boundary: str) -> dict[str, bytes]:
    """Minimal multipart/form-data parser -> {field_name: raw_bytes}.

    Splits on the boundary delimiter, strips the single leading/trailing CRLF that frames each
    part (NOT a full strip — PDF bytes may legitimately end in \\r or \\n), then separates headers
    from content on the first blank line. Only the ``name=`` field is read from Content-Disposition.
    """
    delim = b"--" + boundary.encode("latin1")
    out: dict[str, bytes] = {}
    for raw in body.split(delim):
        if raw in (b"", b"--", b"--\r\n", b"\r\n"):
            continue
        part = raw
        if part.startswith(b"\r\n"):
            part = part[2:]
        if part.endswith(b"\r\n"):
            part = part[:-2]
        if b"\r\n\r\n" not in part:
            continue
        raw_headers, content = part.split(b"\r\n\r\n", 1)
        name: str | None = None
        for line in raw_headers.split(b"\r\n"):
            if line.lower().startswith(b"content-disposition:"):
                for seg in line.decode("latin1").split(";"):
                    seg = seg.strip()
                    if seg.startswith("name="):
                        name = seg[5:].strip().strip('"')
        if name is not None:
            out[name] = content
    return out


def _page_size(pdf_path: str, page_index: int) -> tuple[float, float]:
    doc = pdfium.PdfDocument(pdf_path)
    try:
        w, h = doc[page_index].get_size()  # PDF points, bottom-left origin
        return float(w), float(h)
    finally:
        doc.close()


def _page_count(pdf_path: str) -> int:
    doc = pdfium.PdfDocument(pdf_path)
    try:
        return len(doc)
    finally:
        doc.close()


def _parse_range(page_ranges: str | None, total: int) -> tuple[int, int]:
    """ODL sends a single ``"min-max"`` (1-based, inclusive). Absent -> whole document."""
    if not page_ranges:
        return 1, total
    parts = page_ranges.split("-")
    start = int(parts[0])
    end = int(parts[-1]) if len(parts) > 1 and parts[-1] else start
    return max(1, start), min(total, end)


def convert_pdf(
    pdf_bytes: bytes,
    page_ranges: str | None,
    *,
    transcriber: Transcriber,
    prompt: str = DEFAULT_PROMPT,
    hook: PageHook = _identity_hook,
    post_hook: PostHook = _no_post,
) -> dict[str, Any]:
    """Render + transcribe the requested pages and build the DoclingDocument envelope.

    Pure function over bytes (no HTTP) so it is unit-testable with a fake transcriber. ``hook``
    (pre) and ``post_hook`` (post) are the B-3/B-4 seams: B-4 passes a grounding pre-hook that
    rewrites the prompt and a guard post-hook that flags unsourced numbers in the transcription.
    """
    started = time.monotonic()
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        pdf_path = tmp.name

    blocks: list[PageBlock] = []
    errors: list[str] = []
    failed: list[int] = []
    try:
        total = _page_count(pdf_path)
        start, end = _parse_range(page_ranges, total)
        for page_no in range(start, end + 1):
            idx = page_no - 1
            try:
                png = render_page_png(pdf_path, idx)
                page_prompt, flags = hook(pdf_path, idx, png, prompt)
                markdown = transcriber(png, page_prompt)
                flags = flags + post_hook(pdf_path, idx, markdown)
                width, height = _page_size(pdf_path, idx)
                blocks.append(PageBlock(page_no, width, height, markdown, flags=flags))
            except Exception as exc:  # never drop a page silently
                errors.append(f"Page {page_no}: {type(exc).__name__}")
                failed.append(page_no)
    finally:
        try:
            os.unlink(pdf_path)
        except OSError:
            pass

    status = "success" if not failed else ("partial_success" if blocks else "failure")
    document = build_docling_document(blocks)
    return build_response(
        status, document, processing_time=time.monotonic() - started, errors=errors, failed_pages=failed
    )


class _Handler(BaseHTTPRequestHandler):
    transcriber: Transcriber  # set on the handler class by serve()
    prompt: str = DEFAULT_PROMPT
    hook: PageHook = staticmethod(_identity_hook)
    post_hook: PostHook = staticmethod(_no_post)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - base signature name
        logger.info("%s - %s", self.address_string(), format % args)

    def _send_json(self, obj: dict[str, Any], code: int = 200) -> None:
        payload = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json({"status": "ok"})
        else:
            self._send_json({"error": "not_found"}, 404)

    def do_POST(self) -> None:
        if self.path != "/v1/convert/file":
            self._send_json({"error": "not_found"}, 404)
            return
        ctype = self.headers.get("Content-Type", "")
        if "boundary=" not in ctype:
            self._send_json({"status": "failure", "errors": ["missing multipart boundary"]}, 400)
            return
        boundary = ctype.split("boundary=", 1)[1].strip().strip('"')
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length)
        fields = parse_multipart(body, boundary)
        if "files" not in fields:
            self._send_json({"status": "failure", "errors": ["missing 'files' part"]}, 400)
            return
        page_ranges = fields.get("page_ranges")
        page_ranges_str = page_ranges.decode("latin1").strip() if page_ranges else None
        try:
            result = convert_pdf(
                fields["files"], page_ranges_str,
                transcriber=type(self).transcriber, prompt=type(self).prompt,
                hook=type(self).hook, post_hook=type(self).post_hook,
            )
            self._send_json(result)
        except Exception as exc:
            logger.exception("convert failed")
            self._send_json({"status": "failure", "document": {"json_content": {}},
                             "errors": [type(exc).__name__], "failed_pages": []}, 500)


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 5002,
    transcriber: Transcriber,
    prompt: str = DEFAULT_PROMPT,
    hook: PageHook = _identity_hook,
    post_hook: PostHook = _no_post,
) -> ThreadingHTTPServer:
    """Build (not start) a server bound to host:port with the given transcriber/hook(s)."""
    handler = type("_BoundHandler", (_Handler,), {})
    handler.transcriber = staticmethod(transcriber)  # type: ignore[assignment]
    handler.prompt = prompt
    handler.hook = staticmethod(hook)  # type: ignore[assignment]
    handler.post_hook = staticmethod(post_hook)  # type: ignore[assignment]
    return ThreadingHTTPServer((host, port), handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Track B (B-3) ODL hybrid proxy backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5002)
    parser.add_argument("--provider", choices=["gemini", "paddle"], default="gemini")
    parser.add_argument("--det-aug", action="store_true",
                        help="B-4: deterministic grounding + value-oracle guards (re-parse in proxy)")
    parser.add_argument("--no-odl-grounding", action="store_true",
                        help="B-4: skip ODL structure outline, ground on pypdfium2 text only")
    parser.add_argument("--min-value", type=float, default=None,
                        help="B-4: only guard numbers >= this value (page numbers / small counts are noise)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    transcriber = transcriber_from_env(args.provider)
    if args.det_aug:
        from odl_vl_track_b.det_aug import make_grounding_hook, make_guard_hook
        server = serve(
            host=args.host, port=args.port, transcriber=transcriber,
            hook=make_grounding_hook(use_odl=not args.no_odl_grounding),
            post_hook=make_guard_hook(min_value=args.min_value),
        )
        variant = "B-4 (det-aug)"
    else:
        server = serve(host=args.host, port=args.port, transcriber=transcriber)
        variant = "B-3 (pure VLM)"
    logger.info("%s proxy on http://%s:%d (provider=%s)", variant, args.host, args.port, args.provider)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("shutting down")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
