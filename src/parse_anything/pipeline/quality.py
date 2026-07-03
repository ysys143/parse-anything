"""Deterministic input-quality gate (blur / resolution).

Evidence: docs/.design/measurement-findings.md F4 (legibility drives VLM numeric accuracy) and F6.
Contract: pdf-pipeline-requirements §3.4 (low-quality trigger). This is a cheap pre-VLM
signal that complements the VLM legibility gate: a clearly blurry/low-res page can be
flagged from the rendered image alone, before spending a VLM call. Threshold is a parameter
(R-A7). It surfaces a flag; it does not by itself drop a page.
"""
from __future__ import annotations

import io

import numpy as np
from PIL import Image


def laplacian_variance(image_png: bytes) -> float:
    """Variance of the Laplacian -- a standard sharpness metric (higher = sharper)."""
    gray = np.asarray(Image.open(io.BytesIO(image_png)).convert("L"), dtype=float)
    laplacian = (
        -4.0 * gray
        + np.roll(gray, 1, 0)
        + np.roll(gray, -1, 0)
        + np.roll(gray, 1, 1)
        + np.roll(gray, -1, 1)
    )
    # ignore the wrapped border rows/cols introduced by np.roll
    return float(laplacian[1:-1, 1:-1].var())


def is_low_quality(image_png: bytes, *, min_laplacian_variance: float = 50.0) -> bool:
    return laplacian_variance(image_png) < min_laplacian_variance
