"""FR-1 multi-format ingest: wrap a standalone image (JPG/PNG/TIFF/...) into a thin single-page PDF so
the rest of the pipeline (render -> ODL -> scan path) handles it UNCHANGED. A wrapped image has no
born-digital text layer, so its page flows through the scanned/VLM route exactly like a scanned PDF page
-- no image-specific branch is needed downstream. Uses Pillow (already a core dependency); no new dep."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

# Raster formats Pillow can decode that we accept as a direct document input. PDF/TIFF-as-document is not
# here: a real PDF takes the normal path, and a multi-page TIFF is wrapped first-frame-only (see below).
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".gif"})


def is_image(path: str) -> bool:
    """Whether ``path`` is an image we wrap (by extension -- the entry point routes on the filename)."""
    return Path(path).suffix.lower() in IMAGE_SUFFIXES


# Fixed PDF metadata so the wrapped bytes are DETERMINISTIC for a given image. Pillow otherwise stamps a
# wall-clock CreationDate and copies the output filename into /Title -- with our random temp name that makes
# every wrap unique, which would defeat the content-hash document_id (reprocessing skip never fires, and
# content_sha256 drifts run-to-run). A constant title + epoch date keep identity == image content.
_FIXED_DATE = "D:20000101000000Z"
_FIXED_TITLE = "parse-anything-image-wrap"


def image_to_pdf(image_path: str, out_pdf: str) -> int:
    """Wrap ONE image into a ONE-page, byte-DETERMINISTIC PDF (Pillow); return the source's frame count
    (>1 means pages were dropped -- the caller should warn). Alpha/palette modes are flattened to RGB --
    PDF has no alpha channel and Pillow refuses to save those directly; grayscale (``L``), bitonal (``1``)
    and CMYK are kept as-is (efficient for scans). Only the FIRST frame of a multi-frame image (animated
    GIF / multi-page TIFF) is wrapped -- multi-page raster documents are out of scope for the thin v1 wrap.
    Metadata is pinned (see ``_FIXED_*``) so the same image always hashes the same (identity is scoped to
    the installed Pillow version -- an upgrade may change the bytes and thus the document_id, a benign
    one-time reprocess)."""
    with Image.open(image_path) as im:
        n_frames = int(getattr(im, "n_frames", 1))
        if im.mode not in ("RGB", "L", "1", "CMYK"):   # RGBA/LA/P/other -> flatten (PDF has no alpha/palette)
            im = im.convert("RGB")
        im.save(out_pdf, "PDF", title=_FIXED_TITLE, creationDate=_FIXED_DATE, modDate=_FIXED_DATE)
    return n_frames
