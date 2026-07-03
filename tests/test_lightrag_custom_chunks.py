"""Reproducible LightRAG-integration probe for the *direct chunk insertion* delivery method.

parse-anything owns the chunking (design intent, PR #2: structure is deterministic and ours).
There are two ways to hand that ownership to LightRAG (docs §9.2):

  1. plaintext delimiter  -- ``ainsert(txt, split_by_character=SENTINEL, ...)``: LightRAG's own
     chunker runs but is fenced to our boundaries. Covered by ``test_lightrag_chunk_boundary``.
  2. direct chunk insert  -- ``ainsert_custom_chunks(full_text, text_chunks=[...])``: LightRAG's
     chunker is BYPASSED entirely; our chunk list is upserted verbatim as the storage units.
     *This* file covers (2).

``ainsert_custom_chunks`` still runs LLM entity extraction after upsert (unlike
``ainsert_custom_kg``, path C, which does not), so the instance is wired with a fake LLM that
returns "" (zero entities) and a deterministic offline embedding -- no network, no API key. The
assertion is on the *chunk* storage, not the graph: our records land in order, byte-for-byte,
with no merge/split, and an oversize atom that would make the delimiter path (1b, ``only=True``)
raise ``ChunkTokenLimitExceededError`` is instead stored whole here (the divergence that makes
direct-insert the size-agnostic delivery method).

Skips cleanly when ``lightrag-hku`` (or numpy) is unavailable.
"""
from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("lightrag", reason="lightrag-hku not installed (optional ingest-integration dep)")
np = pytest.importorskip("numpy", reason="numpy required for the offline embedding stub")

from lightrag import LightRAG
from lightrag.kg.shared_storage import finalize_share_data, initialize_pipeline_status
from lightrag.utils import EmbeddingFunc, Tokenizer

from parse_anything.export import ChunkRecord


@pytest.fixture(autouse=True)
def _isolate_lightrag_shared_state():
    """LightRAG's KV storage ``_data`` is a reference into the process-global ``_shared_dicts``
    (not per-working-dir), so two tests in one process contaminate each other -- an identical
    doc_id makes ``ainsert_custom_chunks`` early-return ("already in storage"). Reset the shared
    state around every test so each gets a clean, isolated store."""
    finalize_share_data()
    yield
    finalize_share_data()

CHUNK_TOKEN_SIZE = 80  # 1 char == 1 token under the char tokenizer, so this bound is in characters
_EMBED_DIM = 8


class _CharTokenizer:
    """Lossless code-point tokenizer (offline stand-in for tiktoken; 1 char == 1 token)."""

    def encode(self, content: str) -> list[int]:
        return [ord(c) for c in content]

    def decode(self, tokens: list[int]) -> str:
        return "".join(chr(t) for t in tokens)


async def _fake_embed(texts: list[str]):
    """Deterministic offline embedding: no network, no key, stable per text."""
    return np.array(
        [[(sum(map(ord, t)) + i) % 7 / 7.0 for i in range(_EMBED_DIM)] for t in texts],
        dtype=float,
    )


async def _fake_llm(prompt, system_prompt=None, history_messages=None, **kwargs) -> str:
    """LLM stub that extracts nothing -- we assert on chunk storage, not the KG."""
    return ""


async def _offline_rag(working_dir: str) -> LightRAG:
    rag = LightRAG(
        working_dir=working_dir,
        embedding_func=EmbeddingFunc(embedding_dim=_EMBED_DIM, func=_fake_embed),
        llm_model_func=_fake_llm,
        tokenizer=Tokenizer("char-lossless", _CharTokenizer()),
    )
    await rag.initialize_storages()
    await initialize_pipeline_status()
    return rag


def _text(r: ChunkRecord) -> str:
    assert r.display_text is not None
    return r.display_text


def _prose_records() -> list[ChunkRecord]:
    texts = [
        "Introduction: parse-anything owns the chunk boundaries.",
        "Each prose child must survive the LightRAG ingest whole.",
        "The heading breadcrumb rides along in embedding_text.",
    ]
    return [
        ChunkRecord(id=f"c{i}", doc_id="doc0", structural_type="paragraph", level="child",
                    display_text=t, token_count=len(t))
        for i, t in enumerate(texts)
    ]


def _oversize_table_record() -> ChunkRecord:
    row = "| region | pages | role | confidence | provenance |"
    text = "Table 1: ingest coupling matrix\n" + "\n".join(row for _ in range(6))
    rec = ChunkRecord(id="t0", doc_id="doc0", structural_type="table", level="child",
                      atomic=True, display_text=text, token_count=len(text))
    assert len(_text(rec)) > CHUNK_TOKEN_SIZE  # genuinely oversize
    return rec


async def _insert_and_read(tmp_path, records: list[ChunkRecord]) -> list[dict]:
    """Insert our chunk list through the real API and read the stored chunk records back, ordered."""
    rag = await _offline_rag(str(tmp_path))
    try:
        chunk_texts = [_text(r) for r in records]
        full_text = "\n\n".join(chunk_texts)
        await rag.ainsert_custom_chunks(full_text=full_text, text_chunks=chunk_texts, doc_id="doc0")
        stored = list(rag.text_chunks._data.values())  # type: ignore[attr-defined]  # JsonKVStorage backing dict
        stored.sort(key=lambda r: r.get("chunk_order_index", 0))
        return stored
    finally:
        await rag.finalize_storages()


# ---------------------------------------------------------------------------------------------
# Our chunk list becomes the storage units, in order, byte-for-byte -- no chunker in the path.
# ---------------------------------------------------------------------------------------------
def test_custom_chunks_land_in_order_with_exact_boundaries(tmp_path):
    records = _prose_records()
    stored = asyncio.run(_insert_and_read(tmp_path, records))

    assert [r["content"] for r in stored] == [_text(rec) for rec in records], \
        "direct insert did not preserve our chunk boundaries/order verbatim"
    assert [r["chunk_order_index"] for r in stored] == list(range(len(records)))


# ---------------------------------------------------------------------------------------------
# The divergence from the delimiter path: an oversize atom that makes 1b (only=True) raise is
# stored whole here, because ainsert_custom_chunks bypasses the token-window chunker (no size cap).
# ---------------------------------------------------------------------------------------------
def test_custom_chunks_store_oversize_atom_whole(tmp_path):
    records = [*_prose_records(), _oversize_table_record()]
    stored = asyncio.run(_insert_and_read(tmp_path, records))

    contents = [r["content"] for r in stored]
    assert len(stored) == len(records), "direct insert unexpectedly split or merged a chunk"
    assert _text(records[-1]) in contents, "oversize atom was not stored whole under direct insert"
