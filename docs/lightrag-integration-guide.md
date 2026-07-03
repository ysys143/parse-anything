# parse-anything → LightRAG Integration Guide (canonical)

This document is the **practical canonical reference** for `docs/.design/agent-ready-schema-and-chunking.md` (design and rationale). It keeps only the **two validated paths** that ingest
parse-anything's output (`document.chunks.jsonl` + structure) into LightRAG and carry it through to querying. It is the result of end-to-end measurement and surgery, and a reproducible demo lives in `demo/docker/`.

> **Design intent (PR #2)**: STRUCTURE is ours, deterministically; CONTENT is the VLM's. parse-anything **owns** the structure, reading
> order, and **chunking**, and LightRAG is a downstream consumer. The two paths below carry that intent through.

> **Backend-agnostic (important)**: The two paths below are an **integration contract independent of the LLM/embedding provider**. Behind LightRAG's
> `llm_model_func` / `embedding_func` plugs you can use anything — OpenAI, Gemini, Ollama, local, etc.
> The body of this document (§0–§5) does not commit to a provider. Provider-specific settings and pitfalls live only in **[Appendix A](#appendix-a-backend-setup-this-demo-uses-gemini)** (this demo uses Gemini).
> Measured numbers (e.g., KG 500/511) are results from *this demo (Gemini)* and vary by provider and model.

---

## 0. Which path to use (decision criteria)

| Goal | Path | One-liner |
|---|---|---|
| Keep our chunk boundaries but **leave the KG to LightRAG** | **① delimiter (`ainsert`)** | Simplest and complete. Exact boundaries + KG extracted inside LightRAG + `file_path` anchor. |
| **We control structure, chunking, extraction, and fusion end to end** | **C+concept (`ainsert_custom_kg`)** | We define the ontology/prompts/schema. Fuse structure (sections/figures) + concepts we extracted into a single graph. |
| Only naive/vector RAG needed (no graph) | ①'s `--mode naive` query suffices | No separate path needed. |

> **Do not use `ainsert_custom_chunks` (path ②).** See [Anti-pattern](#5-anti-pattern-ainsert_custom_chunks) below.

Both paths must satisfy the R1 and R2 contract of **§3 (LLM/embedding plugs, provider-agnostic)**.

---

## 1. Path ① — plaintext delimiter (`ainsert`)

If we serialize our owned chunk boundaries with a **delimiter that survives sanitize** and pass them in, LightRAG's default chunker cuts only at those
boundaries (`split_by_character_only=True` → exact 1:1). LightRAG then extracts entities with its own LLM and builds the KG automatically.

```python
# a child chunk's display_text = the retrieval boundary we own
chunks = [c["display_text"] for c in child_chunks]

SENTINEL = "\ue000"  # PUA U+E000. See [Pitfall 1] below — ASCII control chars (\x1e etc.) are stripped by ainsert's sanitize
assert all(SENTINEL not in c for c in chunks)          # prevent collision with body text

await rag.ainsert(
    SENTINEL.join(chunks),
    split_by_character=SENTINEL,
    split_by_character_only=True,   # segment = chunk 1:1, atomicity guaranteed
    file_paths="document.pdf",       # §9.3 metadata round-trip anchor (queryable free string) — preserved
)
```

**Required precondition**: every chunk's token count < `chunk_token_size`. If even one segment exceeds it,
`ChunkTokenLimitExceededError` **aborts the entire ingest** (§9.5). Remedies:
- Set `LightRAG(chunk_token_size=...)` above the largest chunk, or
- **hard-split** oversize atoms (large tables/figures) ahead of time.
- (Reference demo: largest child is 1078 tiktoken tok < 1500, so no hard-split needed.)

**Properties**: exact boundaries · `file_path` anchor preserved · KG automatic (LightRAG extraction). **Cost**: LLM extraction
cost at ingest, and LightRAG owns the KG (no ontology control).

**Measured (demo)**: 88 chunks · KG 500 entities / 511 edges · hybrid query grounding succeeded.

---

## 2. Path C — `ainsert_custom_kg` (structure + concept fusion)

We **supply chunks + entities + relationships directly**. LightRAG only stores and retrieves (no extraction of its own). Cost-vs-quality is
tuned across three stages (the demo's `WITH_CONCEPTS` toggle).

```python
kg = build_custom_kg(rows)            # (2a) structure: sections + figures + edges  — 0 LLM cost
await add_concept_entities(kg, rows)  # (2b) semantics: fuse concepts we extracted — 1 LLM call per chunk (provider-agnostic)
await rag.ainsert_custom_kg(kg, full_doc_id="doc-demo")
```

`custom_kg` schema (core): `{"chunks":[...], "entities":[...], "relationships":[...]}`
- **chunk**: `{content, source_id, file_path, chunk_order_index}` — `source_id` is the chunk key we define.
- **entity**: `{entity_name, entity_type, description, source_id, file_path}` — `source_id` references the chunk's
  `source_id` to **link entity↔chunk**. `file_path` can be set (contrast with ②'s `unknown_source`).
- **relationship**: `{src_id, tgt_id, description, keywords, weight, source_id}` — `description` and `keywords`
  are **required**, `weight` defaults to 1.0. Endpoints reference entity_name (if missing, pre-populate them as thin nodes).

### 2a. Structure KG (0 LLM) — `build_custom_kg`

Build the graph purely from what parse-anything already emits:
- **Entities**: `structural_type=="section"` (parent, carries `heading_path`) → `entity_type="section"`,
  `source_id` = that section's first child. Additionally, `"Fig N ..."` caption chunks → `figure` entities (rich caption description).
- **Relationships**: section reading-order chain + `heading_path` of `"[Fig N]"`/caption chunks → `section→figure` (references/illustrated-by).

> Validation rule (recommend asserting inside the builder): every relationship endpoint exists as an entity, and every entity
> `source_id` maps to a chunk `source_id`. (Demo dry-run: 0 missing.)

**Measured**: 39 entities (32 sections + 7 figures) / 38 edges. **0 LLM cost at ingest**.

### 2b. concept fusion (we extract) — `add_concept_entities`

For each chunk, fire 1 call to an LLM of our choice with **our prompt + JSON schema** to extract concept entities/relations, and
fuse them into the 2a structure. This is the docs §9.6 **fusion differentiator** (we are not extractor resellers — we combine structure + semantics).
The extraction LLM is provider-agnostic — use any model that can be forced to output via a JSON schema (concrete call in [Appendix A](#appendix-a-backend-setup-this-demo-uses-gemini)).

```python
# JSON schema that fixes the output shape (provider-agnostic). Force this schema via response_format.
_CONCEPT_SCHEMA = {
    "type": "object",
    "properties": {
        "entities":  {"type": "array", "items": {"type": "object",
            "properties": {"name": {"type":"string"}, "type": {"type":"string"}, "description": {"type":"string"}},
            "required": ["name", "description"]}},
        "relations": {"type": "array", "items": {"type": "object",
            "properties": {"source": {"type":"string"}, "target": {"type":"string"}, "description": {"type":"string"}},
            "required": ["source", "target", "description"]}},
    }, "required": ["entities", "relations"]}

# 1 call per chunk (concurrency-capped). extract_json() forces the schema on our chosen LLM and returns a dict (Appendix A).
data = await extract_json(PROMPT + chunk_text[:2000], schema=_CONCEPT_SCHEMA)
# data = {"entities":[{name,type,description}], "relations":[{source,target,description}]}
# -> dedup into concept entities (source_id=chunk id) by name (prefer longer description), merge relations, missing endpoints become thin nodes.
```

**Measured**: 88 chunks → 311 concept entities + 340 relations, fused with the structure for a **total of 345 entities / 364 edges** (verified in the on-disk
graphml). Comparable to ① (500/511) but **we own the extraction** (control of prompts/schema/ontology, fused with structure).

---

## 3. Common: LLM / embedding plugs (provider-agnostic)

LightRAG takes only two callables: `llm_model_func` (completion) and `embedding_func` (embedding). **Any provider**
just needs to conform to those interfaces (OpenAI, Gemini, Ollama, local, etc.). The integration requires only **two provider-agnostic contracts**:

- **R1 — embeddings must return N vectors per N texts** as an (N, dim) array. Some providers/models collapse a batched
  input into a single vector or return a mismatched dim → then `EmbeddingFunc` throws "Vector count mismatch". In the
  provider adapter, guarantee **1 text = 1 vector, fixed dim** (concrete workaround in Appendix A).
- **R2 — the keyword-extraction LLM must return a single JSON object** (`{high_level_keywords, low_level_keywords}`). At
  query time LightRAG calls `llm_model_func(..., keyword_extraction=True)`. If the model emits loose JSON, **force the output with
  `response_format`/schema on that call only** (leaving answer generation untouched). Otherwise keyword parsing breaks, leading to "0 vector chunks".

Both requirements are satisfied by the per-provider adapter. **This demo's Gemini implementation is in [Appendix A](#appendix-a-backend-setup-this-demo-uses-gemini).**

### 3c. Query mode caveats (provider-agnostic)

- `hybrid` = entity (local) + relation (global) retrieval. **"0 vector chunks" is normal** (chunks come along via entity `source_id`).
- To mix in direct vector-chunk retrieval, use **`mix`** mode (demo measured: `mix` yields 15 ent / 15 rel / **20 vector chunks**).

---

## 4. Pitfalls — provider-agnostic (only caught E2E)

These two are pitfalls of the LightRAG integration itself, so they apply whatever the provider. (Backend-specific pitfalls are in [Appendix A](#appendix-a-backend-setup-this-demo-uses-gemini).)

| # | Pitfall | Symptom | Remedy |
|---|---|---|---|
| 1 | `ainsert`'s `sanitize_text_for_encoding` **strips** ASCII control chars (`\x1e`/`\x1f`/`\x00`/`\f`) and U+FFFF | delimiter vanishes -> the document clumps into one segment, causing `ChunkTokenLimitExceededError` (demo: 27760 tok) | use **PUA U+E000** as the delimiter. (Unit tests call the chunker directly, skipping this step, so they miss it -> guard `test_delimiter_marker_must_survive_sanitize`) |
| 2 | `ainsert_custom_chunks` **discards** extraction results (no merge) | graphml 0 nodes, hybrid `[no-context]` | avoid path ② -> use ① or C ([§5](#5-anti-pattern-ainsert_custom_chunks)) |

---

## 5. Anti-pattern: `ainsert_custom_chunks`

Path ② inserts chunk vectors but **builds no KG** (confirmed bug: it gathers `_process_extract_entities` results and discards the return value — no
`merge_nodes_and_edges` call). It also pins `file_path` to `unknown_source` and merges identical-text chunks by content-hash (88->85). **naive retrieval works, but it is unfit for graph purposes**.
-> excluded from the canonical reference. If you want a graph, use ① or C.

---

## 6. Reproduction (demo)

Canonical implementation: `demo/docker/ingest_query.py`
- Path ① = `METHOD=a`, Path C = `METHOD=c` (+`WITH_CONCEPTS=1`), Anti-pattern control = `METHOD=b`.
- Includes shared utilities (`_embed`, `_llm`), structure KG (`build_custom_kg`), and concept fusion (`add_concept_entities`).

```bash
# 1) generate chunks.jsonl with parse-anything (deterministic)
parse-anything --pdf document.pdf --mode deterministic --out demo/out --source-id demo --force

# 2) ingest + query in an isolated container (LLM+embedding=Gemini API, key from GEMINI_API_KEY in repo .env)
docker compose -f demo/docker/docker-compose.yml build
docker compose -f demo/docker/docker-compose.yml up --no-log-prefix method-a   # path ①
docker compose -f demo/docker/docker-compose.yml up --no-log-prefix method-c   # path C (+concept)
```

Prerequisites: host Gemini key (`GEMINI_API_KEY` in `.env`), models `gemini-flash-lite-latest` + `gemini-embedding-2`.
Contract reproduction tests (offline): `tests/test_lightrag_chunk_boundary.py`, `tests/test_lightrag_custom_chunks.py`.

---

## 7. Summary table

| | ① delimiter | C structure-only | C + concept | ~~② custom_chunks~~ |
|---|---|---|---|---|
| KG entities/edges *(demo, Gemini)* | 500 / 511 | 39 / 38 | **345 / 364** | 0 / 0 (bug) |
| Extractor | LightRAG | none | **us** | (discarded) |
| Ingest LLM cost | high | 0 | high | wasted |
| `file_path` anchor | [O] | [O] | [O] | [X] `unknown_source` |
| hybrid query | [O] | [O] | [O] | [X] (naive only) |
| Control (ontology) | LightRAG | us | **us** | — |
| Recommendation | [O] simple, complete | low-cost structure KG | [O] full control | [X] avoid |

---

## Appendix A. Backend setup (this demo uses Gemini)

> From here on it is **provider-specific**. If you use a different provider, swap out only this section; the body (§0–§5) stays the same.
> This demo reuses the maintained binding `lightrag.llm.gemini` (validated versus hand-rolled HTTP).

**Models / key**: LLM `gemini-flash-lite-latest`, embedding `gemini-embedding-2` (dim 768). The key is `GEMINI_API_KEY` in the repo `.env`
(LightRAG's `_ensure_api_key` reads it from the env). **Model id caveat**: the bare name `gemini-flash-lite` returns
404 — use the alias `gemini-flash-lite-latest`.

### A-1. Embedding adapter — satisfies contract R1 (N texts -> N vectors)

Two Gemini-specific pitfalls: (i) `gemini-embedding-2` **collapses** multi-input `contents` **into a single vector** (001 is N->N,
2 is N->1); (ii) the decorated `gemini_embed`, when `output_dimensionality` is unspecified, returns 3072, mismatching the declared 1536 ("2 vectors"). -> **specify the dim on the raw function + call one text at a time in parallel**, then stack.

```python
_raw_gemini_embed = gemini_embed.func     # bypass the decorator (raw coroutine)
EMBED_DIM = 768

async def _embed(texts, **kwargs):        # -> EmbeddingFunc(func=_embed): satisfies R1
    context = kwargs.get("context", "document")
    sem = asyncio.Semaphore(8)
    async def one(t):
        async with sem:
            v = await _raw_gemini_embed([t], model="gemini-embedding-2",
                                        embedding_dim=EMBED_DIM, context=context)
            return np.asarray(v)[0]
    return np.array(await asyncio.gather(*(one(t) for t in texts)))

embedding_func = EmbeddingFunc(embedding_dim=EMBED_DIM, max_token_size=2048, func=_embed)
```

### A-2. LLM adapter + keyword schema — satisfies contract R2

`gemini-flash-lite` emits **two JSON objects** for the keyword-extraction prompt, breaking parsing ("payload is not a
JSON object: list"). -> force `response_json_schema` on the keyword call only.

```python
_KEYWORD_SCHEMA = {"type": "json_schema", "json_schema": {"schema": {
    "type": "object", "properties": {
        "high_level_keywords": {"type": "array", "items": {"type": "string"}},
        "low_level_keywords":  {"type": "array", "items": {"type": "string"}},
    }, "required": ["high_level_keywords", "low_level_keywords"]}}}

async def _llm(prompt, system_prompt=None, history_messages=None, keyword_extraction=False, **kw):
    if keyword_extraction:
        kw.setdefault("response_format", _KEYWORD_SCHEMA)
    return await gemini_model_complete(prompt, system_prompt=system_prompt,
                                       history_messages=history_messages,
                                       keyword_extraction=keyword_extraction, **kw)

rag = LightRAG(llm_model_func=_llm, llm_model_name="gemini-flash-lite-latest",
               embedding_func=embedding_func, ...)
```

### A-3. concept extraction call (the `extract_json` implementation from §2b)

`gemini_complete_if_cache` can be called standalone without a LightRAG instance. Wrap §2b's `_CONCEPT_SCHEMA` in
OpenAI style and pass it as `response_format`.

```python
async def extract_json(prompt, schema):   # Gemini implementation of the provider-agnostic signature §2b calls
    rf = {"type": "json_schema", "json_schema": {"schema": schema}}
    raw = await gemini_complete_if_cache("gemini-flash-lite-latest", prompt,
                                         response_format=rf, timeout=60)
    return json.loads(raw)
```

### A-4. Gemini backend pitfall summary

| Pitfall | Symptom | Remedy |
|---|---|---|
| `gemini-embedding-2` collapses multi-input into a single vector | "Vector count mismatch: expected N got 1" | A-1 fan out one text at a time |
| decorated `gemini_embed` declares dim 1536 vs 3072 when unspecified | "expected 1 got 2" | A-1 raw + explicit `embedding_dim` |
| `gemini-flash-lite` keyword emits 2 JSON objects | "payload is not a JSON object: list", "0 vector chunks" | A-2 force keyword schema |
| model id `gemini-flash-lite` 404 | NotFound | alias `gemini-flash-lite-latest` |

> Other providers (OpenAI/Ollama/…) have these pitfalls differently or not at all. As long as each satisfies R1 (1 text = 1 vector, fixed dim)
> and R2 (keyword as a single JSON object), the two paths in the body run unchanged.
