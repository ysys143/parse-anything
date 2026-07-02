"""Reproducible experiment behind design doc §9.5 (Mode 1 chunk-boundary claims).

Runs the ACTUAL installed LightRAG chunker (`lightrag.chunker.chunking_by_token_size`)
to verify, not just assert, that:

  1. ``split_by_character`` provides chunk boundaries — without the delimiter the
     chunker token-windows across our seams (boundaries lost); with it, no chunk
     crosses a seam.
  2. ``only=False`` (1c) preserves each fitting segment whole and sub-splits only
     oversize segments.
  3. ``only=True`` (1b) yields exact 1:1 boundaries when segments fit, and RAISES
     ``ChunkTokenLimitExceededError`` on an oversize segment (does NOT silently emit
     a giant chunk) — the finding that makes 1b the first-party default.

CI-safe: skips when ``lightrag-hku`` is not installed (the offline test env has no
network to install it). Reproduce locally with ``pip install lightrag-hku``.

The tokenizer is a lossless char-level stub: the chunker's branching is
tokenizer-independent, and char-decode round-trips exactly, so the observed behavior
holds for tiktoken/Gemini/etc. — only the token *counts* differ.
"""
from __future__ import annotations

import pytest

chunking = pytest.importorskip("lightrag.chunker")
from lightrag.chunker import chunking_by_token_size  # noqa: E402
from lightrag.exceptions import ChunkTokenLimitExceededError  # noqa: E402

SEAM = "\n<<<CHUNK>>>\n"
PARA1 = ("Retrieval-augmented generation grounds a language model in an external "
         "corpus, so answers cite real passages instead of parametric memory.")
PARA2 = ("Document parsing recovers tables, figures and equations as structure and "
         "preserves reading order; that structure later governs chunking quality.")
TABLE = "TABLE 3.2 Ablation results\n" + "\n".join(
    f"| row{i} | valueA{i} | valueB{i} | valueC{i} |" for i in range(30)
)
LIMIT, OVERLAP = 240, 24  # char "tokens"; PARA1/2 ~140, TABLE ~1200 (oversize)


class _CharTok:
    """Lossless char-level TokenizerInterface (encode/decode round-trip exactly)."""

    def encode(self, content: str) -> list[int]:
        return [ord(c) for c in content]

    def decode(self, tokens: list[int]) -> str:
        return "".join(chr(t) for t in tokens)


def _chunks(doc, delim, only):
    return chunking_by_token_size(_CharTok(), doc, delim, only, OVERLAP, LIMIT)


def _has_whole(chunks, text):
    return any(c["content"].strip() == text.strip() for c in chunks)


def test_split_by_character_carries_boundaries():
    doc = SEAM.join([PARA1, PARA2, TABLE])
    with_delim = _chunks(doc, SEAM, False)   # 1c
    no_delim = _chunks(doc, None, False)     # baseline
    # 1c: each fitting paragraph survives as its own whole chunk...
    assert _has_whole(with_delim, PARA1)
    assert _has_whole(with_delim, PARA2)
    # ...and no chunk merges the two paragraphs across the seam.
    assert not any(PARA1[:20] in c["content"] and PARA2[:20] in c["content"] for c in with_delim)
    # baseline (no delimiter): the seam is ignored, so PARA1 is NOT preserved whole.
    assert not _has_whole(no_delim, PARA1)


def test_1c_only_false_subsplits_only_oversize():
    doc = SEAM.join([PARA1, PARA2, TABLE])
    chunks = _chunks(doc, SEAM, False)
    # PARA1, PARA2 -> one chunk each; the oversize TABLE -> multiple sub-chunks.
    assert _has_whole(chunks, PARA1) and _has_whole(chunks, PARA2)
    assert len(chunks) > 3  # table was internally sub-split
    assert all(c["tokens"] <= LIMIT for c in chunks)


def test_1b_only_true_exact_boundaries_when_fits():
    doc = SEAM.join([PARA1, PARA2, "TABLE small: r0 | r1 | r2"])
    chunks = _chunks(doc, SEAM, True)
    assert len(chunks) == 3  # 1:1 with the three seam segments
    assert _has_whole(chunks, PARA1) and _has_whole(chunks, PARA2)


def test_1b_only_true_raises_on_oversize_atomic():
    doc = SEAM.join([PARA1, PARA2, TABLE])
    with pytest.raises(ChunkTokenLimitExceededError):
        _chunks(doc, SEAM, True)
