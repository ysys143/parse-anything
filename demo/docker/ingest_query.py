"""End-to-end ingest+query for ONE delivery method, run inside an isolated container.

parse-anything owns the chunking (it produced ``chunks.jsonl``); this script hands those
boundaries to LightRAG via one of the two delivery methods and then queries the store:

  METHOD=a  (delimiter)      -> ainsert(SENTINEL-joined text, split_by_character=SENTINEL,
                                        split_by_character_only=True)  -- LightRAG's chunker is
                                        fenced to our boundaries; file_path meta slot preserved.
  METHOD=b  (custom_chunks)  -> ainsert_custom_chunks(full_text, text_chunks=[...])  -- LightRAG's
                                        chunker is bypassed; our list is the storage unit verbatim.

LLM + embedding are served by the host's Ollama (reached over the container boundary), so no
API key and no per-container model download. Each container has its own working_dir volume, so
the two methods' vector/graph stores never mix -- that is the isolation the demo is proving.
"""
from __future__ import annotations

import asyncio
import json
import os
import re

import numpy as np

from lightrag import LightRAG, QueryParam
from lightrag.kg.shared_storage import initialize_pipeline_status
from lightrag.llm.gemini import (  # maintained Gemini binding (reuse)
    gemini_complete_if_cache,
    gemini_embed,
    gemini_model_complete,
)
from lightrag.utils import EmbeddingFunc

# Method C can add a semantic layer we extract ourselves (concepts) on top of the structural KG.
# "1" (default) = extract concepts via Gemini; "0" = structure-only (the earlier zero-LLM variant).
WITH_CONCEPTS = os.environ.get("WITH_CONCEPTS", "1") == "1"

# The maintained gemini_embed is decorated (declares dim 1536); we call its RAW inner coroutine so
# we can pass an explicit output dimension and control batching (see _embed).
_raw_gemini_embed = gemini_embed.func

METHOD = os.environ["METHOD"].lower()            # "a" (delimiter) | "b" (custom_chunks)
# LLM + embeddings both via the Gemini API. The key is read from the environment by LightRAG's
# _ensure_api_key (GEMINI_API_KEY / LLM_BINDING_API_KEY) -- this script never touches the value.
LLM_MODEL = os.environ.get("LLM_MODEL", "gemini-flash-lite-latest")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "gemini-embedding-2")
EMBED_DIM = int(os.environ.get("EMBED_DIM", "768"))
EMBED_CONCURRENCY = int(os.environ.get("EMBED_CONCURRENCY", "8"))
WORKDIR = os.environ.get("WORKDIR", "/work/rag")
CHUNKS_PATH = os.environ.get("CHUNKS_PATH", "/data/chunks.jsonl")
DOC_MD_PATH = os.environ.get("DOC_MD_PATH", "/data/document.md")
QUERY = os.environ.get(
    "QUERY",
    "How does corrective feedback influence human perceptual decision-making in this study, "
    "and what did the authors conclude?",
)
QUERY_MODE = os.environ.get("QUERY_MODE", "hybrid")
# Chunk-boundary marker for the delimiter path. It MUST survive LightRAG's
# ``sanitize_text_for_encoding`` (run inside ``ainsert`` before chunking), which strips ASCII
# control chars -- so the intuitive record-separator \x1e is silently removed and the whole doc
# collapses into one oversize segment. A Private Use Area code point survives sanitization and
# never appears in real document text.
SENTINEL = "\ue000"


def load_records(path: str) -> list[dict]:
    """All chunk records (parents + children) in file order."""
    rows: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _display(rec: dict) -> str:
    return (rec.get("display_text") or rec.get("text") or "").strip()


def load_child_chunks(path: str) -> list[str]:
    """The leaf retrieval units parse-anything emitted (level == 'child'), in file order."""
    return [t for r in load_records(path) if r.get("level") == "child" and (t := _display(r))]


def build_custom_kg(rows: list[dict]) -> dict:
    """Turn parse-anything's OWN structure into a LightRAG custom-KG (path C) -- no LLM extraction.

    Entities  = sections (parent chunks with a heading), described by their heading + a snippet,
                each linked (source_id) to its first child chunk.
    Relations = the section reading-order chain (section i -> section i+1).
    Chunks    = the child leaves, so entity/vector retrieval can ground on real text.
    This is the design's Mode 2 seed_graph (docs §9.6): we own structure AND the KG; LightRAG only
    stores + retrieves. Contrast with the buggy custom_chunks path, which never builds a graph."""
    children = [r for r in rows if r.get("level") == "child" and _display(r)]
    chunks = [
        {"content": _display(r), "source_id": r["id"], "file_path": "document.pdf",
         "chunk_order_index": i}
        for i, r in enumerate(children)
    ]

    sections = [
        r for r in rows
        if r.get("structural_type") == "section" and (r.get("heading_path") or []) and r.get("children")
    ]
    entities, seen = [], set()
    section_names: list[tuple[str, str]] = []  # (entity_name, source_child_id)
    child_by_id = {r["id"]: r for r in children}
    for sec in sections:
        name = (sec["heading_path"] or [""])[-1].strip()
        first_child = next((c for c in sec["children"] if c in child_by_id), None)
        if not name or name in seen or first_child is None:
            continue
        seen.add(name)
        snippet = _display(child_by_id[first_child])[:300]
        entities.append({
            "entity_name": name, "entity_type": "section",
            "description": f"{name}: {snippet}", "source_id": first_child,
            "file_path": "document.pdf",
        })
        section_names.append((name, first_child))

    relationships = [
        {"src_id": section_names[i][0], "tgt_id": section_names[i + 1][0],
         "description": f"'{section_names[i][0]}' is followed by '{section_names[i + 1][0]}' in the document.",
         "keywords": "reading-order, document structure", "weight": 1.0,
         "source_id": section_names[i][1]}
        for i in range(len(section_names) - 1)
    ]

    # Structural enrichment (still no LLM): figure entities + section->figure edges, derived from the
    # figure-caption chunks ("Fig N ...") and reference-placeholder chunks ("[Fig N]") parse-anything emits.
    fig_caption = re.compile(r"^\s*Fig\.?\s*(\d+)\b", re.I)
    fig_ref = re.compile(r"^\s*\[\s*Fig\.?\s*(\d+)\s*\]", re.I)
    fig_entities: dict[str, dict] = {}
    fig_edges: list[tuple[str, str, str, str]] = []  # (section, figure, relation, source_chunk_id)
    for r in children:
        txt, hp = _display(r), (r.get("heading_path") or [])
        sec = hp[-1].strip() if hp else None
        mref, mcap = fig_ref.match(txt), fig_caption.match(txt)
        if mref:
            name = f"Figure {mref.group(1)}"
            if sec is not None and sec in seen:
                fig_edges.append((sec, name, "references", r["id"]))
        elif mcap:  # caption chunk carries the real figure text
            name = f"Figure {mcap.group(1)}"
            if name not in fig_entities or len(txt) > len(fig_entities[name]["description"]):
                fig_entities[name] = {"entity_name": name, "entity_type": "figure",
                                      "description": txt[:400], "source_id": r["id"],
                                      "file_path": "document.pdf"}
            if sec is not None and sec in seen:
                fig_edges.append((sec, name, "illustrated by", r["id"]))
    for _, name, _, sid in fig_edges:            # thin node for figures only referenced, never captioned
        fig_entities.setdefault(name, {"entity_name": name, "entity_type": "figure",
                                       "description": f"{name} in the document.", "source_id": sid,
                                       "file_path": "document.pdf"})
    entities.extend(fig_entities.values())
    for src, tgt, kind, sid in fig_edges:
        relationships.append({"src_id": src, "tgt_id": tgt,
                              "description": f"Section '{src}' {kind} {tgt}.",
                              "keywords": f"{kind}, figure reference", "weight": 1.0, "source_id": sid})

    print(f"[method c] custom_kg: {len(chunks)} chunks, {len(entities)} entities "
          f"({len(section_names)} sections + {len(fig_entities)} figures), "
          f"{len(relationships)} edges ({len(section_names) - 1} reading-order + {len(fig_edges)} figure)",
          flush=True)
    return {"chunks": chunks, "entities": entities, "relationships": relationships}


# flash-lite intermittently emits TWO JSON objects for the keyword-extraction prompt (the query's
# low-level keywords then fail to parse -> "0 vector chunks"). Forcing a response_json_schema on ONLY
# the keyword calls constrains it to a single object; the prose answer call is left untouched.
_KEYWORD_SCHEMA = {
    "type": "json_schema",
    "json_schema": {"schema": {
        "type": "object",
        "properties": {
            "high_level_keywords": {"type": "array", "items": {"type": "string"}},
            "low_level_keywords": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["high_level_keywords", "low_level_keywords"],
    }},
}


async def _llm(prompt, system_prompt=None, history_messages=None, keyword_extraction=False, **kwargs):
    if keyword_extraction:
        kwargs.setdefault("response_format", _KEYWORD_SCHEMA)
    return await gemini_model_complete(
        prompt, system_prompt=system_prompt, history_messages=history_messages,
        keyword_extraction=keyword_extraction, **kwargs,
    )


async def _embed(texts, **kwargs):
    """Embed a batch. gemini-embedding-2 collapses a multi-item ``contents`` list into ONE vector
    (unlike gemini-embedding-001, which returns one-per-item), so LightRAG's batch call would get
    the wrong count. We fan out to single-item calls (concurrency-capped) and stack -> N vectors
    for N texts, with an explicit output dimension so the count/dim validation holds."""
    context = kwargs.get("context", "document")
    sem = asyncio.Semaphore(EMBED_CONCURRENCY)

    async def one(text: str) -> np.ndarray:
        async with sem:
            vec = await _raw_gemini_embed(
                [text], model=EMBED_MODEL, embedding_dim=EMBED_DIM, context=context
            )
            return np.asarray(vec)[0]

    vecs = await asyncio.gather(*(one(t) for t in texts))
    return np.array(vecs)


async def build_rag() -> LightRAG:
    rag = LightRAG(
        working_dir=WORKDIR,
        llm_model_func=_llm,
        llm_model_name=LLM_MODEL,
        llm_model_kwargs={"timeout": 120},
        embedding_func=EmbeddingFunc(embedding_dim=EMBED_DIM, max_token_size=2048, func=_embed),
        # Max child is ~1078 tiktoken tokens < 1200, so method A reproduces all boundaries 1:1
        # with no oversize raise and no pre-hard-split. Margin added for safety.
        chunk_token_size=1500,
    )
    await rag.initialize_storages()
    await initialize_pipeline_status()
    return rag


_CONCEPT_SCHEMA = {
    "type": "json_schema",
    "json_schema": {"schema": {
        "type": "object",
        "properties": {
            "entities": {"type": "array", "items": {"type": "object", "properties": {
                "name": {"type": "string"}, "type": {"type": "string"},
                "description": {"type": "string"}}, "required": ["name", "description"]}},
            "relations": {"type": "array", "items": {"type": "object", "properties": {
                "source": {"type": "string"}, "target": {"type": "string"},
                "description": {"type": "string"}}, "required": ["source", "target", "description"]}},
        },
        "required": ["entities", "relations"],
    }},
}
_CONCEPT_PROMPT = (
    "Extract a knowledge graph from this excerpt of an academic paper. Identify the key domain "
    "concepts as entities (name, a short type, and a one-sentence description) and the relations "
    "between them (source, target, description). Only include concepts actually present in the text.\n\n"
    "Text:\n"
)


async def add_concept_entities(kg: dict, rows: list[dict]) -> None:
    """Fuse a SEMANTIC layer onto the structural KG: we run the extraction ourselves (Gemini, our
    prompt + schema) and hand LightRAG the concepts/relations via custom_kg. This is the full Mode 2
    posture -- we own structure AND the extracted KG -- distinct from method A where LightRAG extracts
    internally. Concepts link (source_id) to the chunk they came from, fusing with sections/figures."""
    children = [r for r in rows if r.get("level") == "child" and _display(r)]
    existing = {e["entity_name"] for e in kg["entities"]}
    sem = asyncio.Semaphore(EMBED_CONCURRENCY)

    async def one(rec: dict):
        async with sem:
            try:
                raw = await gemini_complete_if_cache(
                    LLM_MODEL, _CONCEPT_PROMPT + _display(rec)[:2000],
                    response_format=_CONCEPT_SCHEMA, timeout=60,
                )
                return rec["id"], json.loads(raw if isinstance(raw, str) else "")
            except Exception:
                return rec["id"], None

    results = await asyncio.gather(*(one(r) for r in children))

    concepts: dict[str, dict] = {}
    relations: list[dict] = []
    for cid, data in results:
        if not isinstance(data, dict):
            continue
        for e in data.get("entities", []):
            name = (e.get("name") or "").strip()
            if not name:
                continue
            desc = (e.get("description") or name)[:300]
            if name not in concepts or len(desc) > len(concepts[name]["description"]):
                concepts[name] = {"entity_name": name, "entity_type": (e.get("type") or "concept"),
                                  "description": desc, "source_id": cid, "file_path": "document.pdf"}
        for rel in data.get("relations", []):
            s, t = (rel.get("source") or "").strip(), (rel.get("target") or "").strip()
            if s and t and s != t:
                relations.append({"src_id": s, "tgt_id": t,
                                  "description": (rel.get("description") or f"{s} - {t}")[:200],
                                  "keywords": "concept relation", "weight": 1.0, "source_id": cid})

    names = set(concepts) | existing
    for rel in relations:  # thin node for any endpoint neither a concept nor a structural entity
        for nm in (rel["src_id"], rel["tgt_id"]):
            if nm not in names:
                concepts[nm] = {"entity_name": nm, "entity_type": "concept", "description": nm,
                                "source_id": rel["source_id"], "file_path": "document.pdf"}
                names.add(nm)

    kg["entities"].extend(concepts.values())
    kg["relationships"].extend(relations)
    print(f"[method c] + concepts: {len(concepts)} concept entities, {len(relations)} concept relations "
          f"(from {len(children)} chunks)", flush=True)


async def ingest(rag: LightRAG, rows: list[dict], full_text: str) -> None:
    chunks = [t for r in rows if r.get("level") == "child" and (t := _display(r))]
    if METHOD == "a":
        assert all(SENTINEL not in c for c in chunks), "a chunk contains the SENTINEL char"
        stream = SENTINEL.join(chunks)
        await rag.ainsert(
            stream,
            split_by_character=SENTINEL,
            split_by_character_only=True,
            file_paths="document.pdf",
        )
    elif METHOD == "b":
        await rag.ainsert_custom_chunks(full_text=full_text, text_chunks=chunks, doc_id="doc-demo")
    elif METHOD == "c":
        kg = build_custom_kg(rows)
        if WITH_CONCEPTS:
            await add_concept_entities(kg, rows)
        await rag.ainsert_custom_kg(kg, full_doc_id="doc-demo")
    else:
        raise SystemExit(f"unknown METHOD={METHOD!r} (expected 'a', 'b', or 'c')")


async def stored_chunk_count(rag: LightRAG) -> int:
    try:
        return len(rag.text_chunks._data)  # type: ignore[attr-defined]  # JsonKVStorage backing dict
    except Exception:
        return -1


_DELIVERY = {"a": "delimiter/ainsert", "b": "custom_chunks", "c": "custom_kg (structure-seeded)"}


async def graph_counts(rag: LightRAG) -> tuple[int, int]:
    """Entity (node) + relation (edge) counts read straight from the graph store, so the number
    reflects what actually landed in the KG (the full_relations KV was a misleading proxy)."""
    try:
        n_ent = len(await rag.chunk_entity_relation_graph.get_all_labels())
    except Exception:
        n_ent = -1
    n_rel = -1
    graph = getattr(rag.chunk_entity_relation_graph, "_graph", None)
    if graph is not None:
        try:
            n_rel = graph.number_of_edges()
        except Exception:
            n_rel = -1
    return n_ent, n_rel


async def main() -> None:
    rows = load_records(CHUNKS_PATH)
    n_children = sum(1 for r in rows if r.get("level") == "child" and _display(r))
    with open(DOC_MD_PATH, encoding="utf-8") as fh:
        full_text = fh.read()

    print(f"[method {METHOD}] loaded {n_children} child chunks; ingesting via "
          f"{_DELIVERY.get(METHOD, METHOD)} ...", flush=True)

    rag = await build_rag()
    try:
        await ingest(rag, rows, full_text)
        n_chunks = await stored_chunk_count(rag)
        n_ent, n_rel = await graph_counts(rag)
        print(f"[method {METHOD}] stored_chunks={n_chunks} entities={n_ent} relations={n_rel}",
              flush=True)

        # Retrieved evidence (grounding) + the generated answer.
        qp_ctx = QueryParam(mode=QUERY_MODE, top_k=8, only_need_context=True)  # type: ignore[arg-type]
        qp_ans = QueryParam(mode=QUERY_MODE, top_k=8)  # type: ignore[arg-type]
        ctx = await rag.aquery(QUERY, param=qp_ctx)
        answer = await rag.aquery(QUERY, param=qp_ans)
        ctx = ctx if isinstance(ctx, str) else ""
        answer = answer if isinstance(answer, str) else str(answer)

        summary = {
            "method": METHOD,
            "delivery": _DELIVERY.get(METHOD, METHOD),
            "child_chunks_ingested": n_children,
            "stored_chunks": n_chunks,
            "entities": n_ent,
            "relations": n_rel,
            "query": QUERY,
            "query_mode": QUERY_MODE,
            "answer": answer,
        }
        print("\n===== RESULT JSON =====", flush=True)
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
        print("\n===== RETRIEVED CONTEXT (head) =====", flush=True)
        print((ctx or "")[:2000], flush=True)
    finally:
        await rag.finalize_storages()


if __name__ == "__main__":
    asyncio.run(main())
