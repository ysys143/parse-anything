from __future__ import annotations

import io

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from parse_anything.pipeline.render import page_count, render_page_png


def _make_pdf(path, *, pages: int = 1) -> str:
    c = canvas.Canvas(str(path), pagesize=letter)
    for i in range(pages):
        c.drawString(72, 720, f"Page {i + 1} -- hello world")
        c.showPage()
    c.save()
    return str(path)


def test_page_count(tmp_path):
    assert page_count(_make_pdf(tmp_path / "doc.pdf", pages=3)) == 3


def test_render_page_png_returns_real_image(tmp_path):
    png = render_page_png(_make_pdf(tmp_path / "doc.pdf", pages=1), 0, scale=2.0)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic
    from PIL import Image

    width, height = Image.open(io.BytesIO(png)).size
    assert width > 100 and height > 100


def test_higher_scale_yields_larger_image(tmp_path):
    pdf = _make_pdf(tmp_path / "doc.pdf", pages=1)
    from PIL import Image

    small = Image.open(io.BytesIO(render_page_png(pdf, 0, scale=1.0))).size
    large = Image.open(io.BytesIO(render_page_png(pdf, 0, scale=2.0))).size
    assert large[0] > small[0] and large[1] > small[1]
