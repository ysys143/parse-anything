from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFilter

from parse_anything.pipeline.quality import is_low_quality, laplacian_variance


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _sharp_text_image() -> Image.Image:
    img = Image.new("L", (400, 240), 255)
    draw = ImageDraw.Draw(img)
    for y in range(20, 220, 20):
        draw.text((10, y), "Sharp text line 1234567890", fill=0)
    return img


def test_sharp_image_has_higher_laplacian_variance_than_blurred():
    sharp = _sharp_text_image()
    blurred = sharp.filter(ImageFilter.GaussianBlur(5))
    assert laplacian_variance(_png(sharp)) > laplacian_variance(_png(blurred))


def test_is_low_quality_distinguishes_sharp_and_blurred():
    sharp = _png(_sharp_text_image())
    blurred = _png(_sharp_text_image().filter(ImageFilter.GaussianBlur(6)))
    threshold = (laplacian_variance(sharp) + laplacian_variance(blurred)) / 2
    assert is_low_quality(blurred, min_laplacian_variance=threshold)
    assert not is_low_quality(sharp, min_laplacian_variance=threshold)
