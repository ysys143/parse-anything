"""Reproducible LightRAG-integration probe for the Mode 1 ``1b``/``1c`` ingest paths.

This is the artifact ``docs/agent-ready-schema-and-chunking.md`` §9.5 promises: not a claim
in prose but a *re-runnable* check that LightRAG's default ingest chunker
(``chunking_by_token_size``) actually honours the chunk boundaries parse-anything owns when
those boundaries are handed over as a ``split_by_character``-delimited stream.

The join under test is the design's ``1b`` serialization: take the ``display_text`` of our
Layer-2 ``ChunkRecord``s, concatenate them with a single-character SENTINEL, and ingest via
``ainsert(txt, split_by_character=SENTINEL, split_by_character_only=...)``. This test drives the
chunker directly (no LLM/embedding/network) and asserts the four behaviours §9.5 records:

  A. no delimiter (baseline)      -> seams ignored, our boundaries LOST (token-window cut)
  B. ``only=False`` (path 1c)     -> fit segments preserved 1:1, only oversize atom re-split
  C. ``only=True``  (path 1b)     -> exact 1:1 boundaries + atomicity for a fit stream
  D. ``only=True``  + oversize    -> raises ``ChunkTokenLimitExceededError`` (ingest fail-loud)

Tokenizer: tiktoken's BPE vocab needs a network fetch and is unavailable offline, so we
substitute a *lossless* code-point tokenizer (1 char == 1 token). The chunker's branch logic is
tokenizer-agnostic, so the boundary conclusions are identical; only the token *counts* differ
(here they equal character counts, which keeps the fixtures self-checking). Skips cleanly when
``lightrag-hku`` is not installed.
"""
from __future__ import annotations

import pytest

pytest.importorskip("lightrag", reason="lightrag-hku not installed (optional ingest-integration dep)")

# The chunker moved packages across lightrag releases (operate -> chunker.token_size); try both so
# the test tracks the public entry point rather than one version's layout.
try:
    from lightrag.chunker.token_size import chunking_by_token_size
except ImportError:  # pragma: no cover - older lightrag layout
    from lightrag.operate import chunking_by_token_size  # type: ignore[attr-defined,no-redef]
from lightrag.exceptions import ChunkTokenLimitExceededError
from lightrag.utils import Tokenizer

from parse_anything.export import ChunkRecord

# 1 char == 1 token under the lossless tokenizer below, so these bounds are in characters.
CHUNK_TOKEN_SIZE = 80
OVERLAP = 20
SENTINEL = "\x1e"  # ASCII record separator: never appears in prose, single char, non-whitespace


class _CharTokenizer:
    """Lossless code-point tokenizer (offline stand-in for tiktoken; 1 char == 1 token)."""

    def encode(self, content: str) -> list[int]:
        return [ord(c) for c in content]

    def decode(self, tokens: list[int]) -> str:
        return "".join(chr(t) for t in tokens)


def _tokenizer() -> Tokenizer:
    return Tokenizer("char-lossless", _CharTokenizer())


def _text(r: ChunkRecord) -> str:
    """display_text is Optional in the contract, but every fixture record sets it -- narrow here."""
    assert r.display_text is not None
    return r.display_text


def _prose_records() -> list[ChunkRecord]:
    """Three prose child chunks, each comfortably under the token cap (fit stream)."""
    texts = [
        "Introduction: parse-anything owns the chunk boundaries.",
        "Each prose child must survive the LightRAG ingest whole.",
        "The heading breadcrumb rides along in embedding_text.",
    ]
    recs = [
        ChunkRecord(id=f"c{i}", doc_id="doc0", structural_type="paragraph", level="child",
                    display_text=t, token_count=len(t))
        for i, t in enumerate(texts)
    ]
    # Fixture invariant: every prose segment fits, so 1b/1c must agree on them.
    assert all(len(_text(r)) <= CHUNK_TOKEN_SIZE for r in recs)
    return recs


def _oversize_table_record() -> ChunkRecord:
    """One atomic table child whose serialized view exceeds the token cap."""
    row = "| region | pages | role | confidence | provenance |"
    text = "Table 1: ingest coupling matrix\n" + "\n".join(row for _ in range(6))
    rec = ChunkRecord(id="t0", doc_id="doc0", structural_type="table", level="child",
                      atomic=True, display_text=text, token_count=len(text))
    # Fixture invariant: this atom is genuinely oversize, so it is the 1b/1c divergence point.
    assert len(_text(rec)) > CHUNK_TOKEN_SIZE
    return rec


def _serialize(records: list[ChunkRecord]) -> str:
    """The design's ``1b`` delimiter serialization: display_texts joined by the SENTINEL."""
    return SENTINEL.join(_text(r) for r in records)


def _chunk(stream: str, *, only: bool, delimiter: str | None = SENTINEL) -> list[dict]:
    return chunking_by_token_size(
        _tokenizer(), stream,
        split_by_character=delimiter, split_by_character_only=only,
        chunk_overlap_token_size=OVERLAP, chunk_token_size=CHUNK_TOKEN_SIZE,
    )


# ---------------------------------------------------------------------------------------------
# A. Baseline — no delimiter: the chunker ignores our seams and cuts on the token window, so our
#    boundaries are lost. Concretely, no prose segment survives as its own standalone chunk.
# ---------------------------------------------------------------------------------------------
def test_baseline_no_delimiter_loses_our_boundaries():
    recs = _prose_records()
    stream = _serialize(recs)  # stream still contains SENTINELs, but we DON'T tell the chunker
    chunks = [c["content"] for c in _chunk(stream, only=False, delimiter=None)]

    segments = {r.display_text for r in recs}
    # Not one of our exact segments is reproduced as a whole chunk -> boundaries not preserved.
    assert segments.isdisjoint(chunks), (
        "baseline token-window chunking unexpectedly preserved a segment boundary"
    )


# ---------------------------------------------------------------------------------------------
# B. Path 1c (only=False): each fit segment is preserved 1:1 as its own chunk, and ONLY the
#    oversize atom is internally re-split. No exception, and no chunk crosses a seam.
# ---------------------------------------------------------------------------------------------
def test_only_false_preserves_fit_segments_and_subsplits_oversize():
    prose = _prose_records()
    table = _oversize_table_record()
    stream = _serialize([*prose, table])
    chunks = [c["content"] for c in _chunk(stream, only=False)]

    # Every fit prose segment survives whole (seam honoured).
    for r in prose:
        assert r.display_text in chunks, f"1c dropped fit boundary for {r.id}"
    # The oversize atom is split into >1 sub-chunk (sizing owned by the consumer)...
    assert table.display_text not in chunks, "oversize atom unexpectedly kept whole under 1c"
    assert len(chunks) > len([*prose, table]), "no sub-splitting happened for the oversize atom"
    # ...but no sub-chunk ever spans across a SENTINEL (no seam crossing).
    assert all(SENTINEL not in c for c in chunks)


# ---------------------------------------------------------------------------------------------
# C. Path 1b (only=True) on a fit stream: exact 1:1 boundaries + atomicity. The chunk list is our
#    segment list, in order, with nothing merged or split.
# ---------------------------------------------------------------------------------------------
def test_only_true_exact_one_to_one_boundaries():
    recs = _prose_records()
    stream = _serialize(recs)
    chunks = [c["content"] for c in _chunk(stream, only=True)]

    assert chunks == [r.display_text for r in recs], "1b did not reproduce our boundaries exactly"


# ---------------------------------------------------------------------------------------------
# D. Path 1b (only=True) with an oversize atom: the chunker fails loud rather than silently
#    emitting an over-window chunk -> ingest aborts, which is why 1b REQUIRES pre-hard-splitting
#    oversize atoms (docs §9.5).
# ---------------------------------------------------------------------------------------------
def test_only_true_oversize_atom_raises():
    stream = _serialize([*_prose_records(), _oversize_table_record()])
    with pytest.raises(ChunkTokenLimitExceededError):
        _chunk(stream, only=True)
