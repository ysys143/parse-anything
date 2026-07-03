# Export Contracts (Layer 2 chunks · Layer 0+1 structure)

> Status: contract spec. Implements `.design/agent-ready-schema-and-chunking.md` §10's "pin down the two export surfaces
> as public and versioned." The authoritative definition lives in code at `src/parse_anything/export/contracts.py`; this
> document describes its fields, versions, and stability policy. `tests/test_export_contracts.py` enforces that the two stay in sync.

## Why contracts

Between the parsing/chunking core and downstream consumers we place **two stable, independently versioned surfaces**. That way a
future repo split (`parse-anything` core <-> `parse-anything[kg]`) becomes a **packaging task rather than a rewrite** (§10).

- **Structure export (Layer 0+1)** — the grounded structure graph. Consumed by **Mode 2 (our KG builder)** and graph tools.
  A superset of the existing `document.json` plus the Layer 1 `roles` overlay.
- **Chunk export (Layer 2)** — agent/RAG-ready chunk records. Consumed by **Mode 1 (text/chunks)** RAG ingest.

## Versioning and stability policy

- Versions are `"MAJOR.MINOR"`. **MINOR** = field addition (backward-compatible). **MAJOR** = field removal/rename/semantic change.
- **Consumers must ignore unknown fields** (forward-compat). `from_dict` enforces this (unknown key drop).
- **Producers omit `None` optionals** (matching the compact style of `document.json`).
- Every payload carries a `contract` tag (`{name, version}`). Consumers gate on **MAJOR** via `check_compatible`.
- Current versions: `parse-anything.structure` = **1.1**, `parse-anything.chunks` = **1.1**, `parse-anything.semantic` = **1.0**,
  `parse-anything.provenance` = **1.0**.
  - **v1.1 delta** (PR #3 x #4 merge): add `@context` and `zones[]` to `StructureExport` (additive -> MINOR);
    extend `ChunkRecord` into a small-to-big parent/child model (add `level/children/prev/next/is_continuation/
    display_text/embedding_text/tokenizer/node_types/zone`, keep `text` as an optional legacy alias).
    Newly add `SemanticView` and `Provenance` for the Layer 2 clean projection and its geometry sidecar.

```python
from parse_anything.export import STRUCTURE_CONTRACT, check_compatible
assert check_compatible(payload["contract"], STRUCTURE_CONTRACT)  # same name + same major
```

## Structure export (Layer 0+1)

Consistent with the output of `build_graph` (`pipeline/structure.py`) plus `DocumentMeta.to_dict()` (`pipeline/docmeta.py`).
That is, this contract does not invent a new format; it **documents the current output**. The pipeline emits it as
**`document.structure.json`** (`StructureExport.from_dict(document.json_dict).to_dict()`).
This is a **typed view** of the loss-aware `document.json` — keys outside the dataclass are dropped here (lossy-by-design) but
preserved in the original `document.json`. Identifiers are flattened **at the top level** just as in `SemanticView`/`document.json`
(v1.1, not wrapped under `document`).

Top level:

| Field | Type | Description |
|---|---|---|
| `contract` | `{name, version}` | `parse-anything.structure` / `1.1` |
| `@context` | object \| null | JSON-LD `@context` (portable IR, v1.1). Omitted if absent |
| `document_id`, `content_sha256`, `n_pages`, `mode`, … | — | flat identity (`DocumentMeta.to_dict()` flattened to top level) |
| `ontology` | `{profile, version}` \| null | injected ontology (§2.4). null if unclassified |
| `pages` | `PageEntry[]` | per-page reading-order id stream |
| `sections` | `Section[]` | chapter/section tree (parent-child) |
| `blocks` | `Block[]` | text-node registry |
| `tables` | `Table[]` | table nodes (a page-spanning table is one node, `pages[]`) |
| `figures` | `Figure[]` | figure nodes |
| `roles` | `{node_id: RoleAssignment}` | **Layer 1 overlay**. Non-destructive (does not stamp roles onto nodes). `{}` if unclassified |
| `zones` | `{zone, pages[]}[]` | zone->pages summary (promotes zones to a top-level axis, v1.1) |

The required/optional fields per node are authoritative in the dataclasses of `contracts.py`:

- **Block**: `id, type, page, order, bbox, text` + optional `font_size, section, refs, figure`.
- **Table**: `id, type=table, pages, order, n_rows, n_cols, cells[][], regions[]` + optional `label, caption,
  caption_id, continued, arithmetic, views, section`. **Cell**: `text` + optional `bbox, row_span, col_span`.
- **Figure**: `id, type=figure, page, order, kind` + optional `label, caption, caption_id, bbox, file, source,
  description, section`.
- **Section**: `id, heading, level, block_id, children[], content[]` + optional `page, parent`.
- **PageEntry**: `page_index, page_number, mode, used_vlm, flags[]` + optional `page_label, markdown_file,
  content[], blocks[], tables[], figures[]`.
- **RoleAssignment**: `role, confidence, by` (`signal:… | vlm | default`).

> **Note:** `roles` is a separate map — it does not inline `role` into the node dict. At the contract level this enforces
> the §1 principle that Layer 1 is an overlay that does not modify Layer 0. `document.json` (Layer 0) keeps byte-compat
> (no `role/zone/heading_level/odl_role`), while `roles`/`zones`/`@context` are added additively at the top level.

## Semantic view (Layer 2) + Provenance sidecar

`document.semantic.json` — the agent-clean projection. Roles are inlined into nodes (this is a projection, so it does not
violate §1), and geometry (bbox/order/font_size/regions/cell bbox) is removed and demoted into the companion
`document.provenance.json`. The pipeline serializes these two files from the `.to_dict()` of `SemanticView` and `Provenance`
respectively (§5 producer-backed).

**`SemanticView`** (`parse-anything.semantic` / `1.0`) — the top level flattens flat identity (aligned with Layer 0) and carries envelope fields:

| Field | Type | Description |
|---|---|---|
| `contract` | `{name, version}` | `parse-anything.semantic` / `1.0` |
| `document_id`, `content_sha256`, `n_pages`, `mode`, … | — | flat identity (flattened from `document`) |
| `@context` | object \| null | JSON-LD `@context` |
| `profile` | object \| null | injected ontology profile stamp |
| `metadata` | `{title, …}` | document metadata (title, etc.) |
| `zones` | `{zone, pages[]}[]` | zone summary |
| `nodes` | object[] | **geometry-free** clean nodes (`id/type(=role)/zone/text\|latex/label/caption_ref?/…`) |
| `sections` | object[] | heading tree (`id/heading/level/zone/heading_ref/parent/children/content`) |
| `reading_order` | id[] | flat reading-order node id stream |

**`Provenance`** (`parse-anything.provenance` / `1.0`) — the geometry sidecar. **Joined by node id** with `SemanticView`/`StructureExport`:

| Field | Type | Description |
|---|---|---|
| `contract` | `{name, version}` | `parse-anything.provenance` / `1.0` |
| `profile` | object \| null | ontology profile stamp |
| `prov` | `{node_id: {page?, order?, bbox?, font_size?, regions?, cell_boxes?}}` | per-node geometry |

## Chunk export (Layer 2)

`chunks.jsonl` — one `ChunkRecord` per line (serialized via `ChunkRecord.to_dict()`). Small-to-big: **PARENT**
chunks (a section or a page group) are filled by the **CHILD** chunks that are the indexing targets (token-packed, atomic ones kept whole).
You embed and search the children and return the parent section.

| Field | Type | Description |
|---|---|---|
| `id` | str | chunk id |
| `level` | `parent\|child` | small-to-big hierarchy (v1.1) |
| `parent_id` | str \| null | child->parent chunk id |
| `children` | str[] | parent->child chunk ids (v1.1) |
| `doc_id` | str | content-hash document id |
| `structural_type` | str | `section/page` (parent) · `text/table/figure/equation` (child) |
| `zone` | str \| null | the zone the chunk belongs to (v1.1) |
| `role` | str \| null | semantic role (§2.2). Roles with a `drop` policy have no record at all |
| `heading_path` | str[] | ancestor heading breadcrumb |
| `display_text` | str | on-screen display text (table = md-stub, equation = LaTeX) (v1.1) |
| `embedding_text` | str \| null | embedding text prefixed with the breadcrumb (§9.3) (child) (v1.1) |
| `text` | str \| null | **legacy v1.0 alias** (optional). New consumers use `display_text` |
| `token_count` | int | model-agnostic **estimate**. Fit is guaranteed against the consumer-configured tokenizer (§9.5) |
| `tokenizer` | str \| null | name of the tokenizer used for the count (counts are tokenizer-specific) (v1.1) |
| `atomic` | bool | table/figure/equation = no-split unit |
| `is_continuation` | bool | continuation of the immediately preceding text child (over-budget split) (v1.1) |
| `prev` / `next` | str \| null | reading-order leaf links (v1.1) |
| `source_refs` | `{nodes[], pages[]}` | **Layer 0 round-trip**: citation/bbox grounding (`pages` = page span). For an atomic child, `nodes[0]` is exactly the table/figure/equation ref |
| `node_types` | str[] | semantic node types contained in this chunk (v1.1) |
| `refs` | str[] | node ids linked by cross-ref |
| `meta` | object | additional metadata (role-specific) |

## Consumer mapping (summary)

- **Mode 1** -> Chunk export. LightRAG `ainsert` (1a/1c: text view) or delimiter serialization (1b). `role`/`bbox` are
  joined from the chunks.jsonl sidecar (since the fixed chunk schema strips them, §9.3).
- **Mode 2** -> Structure export. The extractor port uses blocks/sections/cross-refs as deterministic structure edges
  (fusion, §9.6), while prose entities are filled in by a pluggable engine. KG grounding via `source_refs`/node bbox.

## Non-goals

- The contract defines the **serialization shape**, not the production order/stages (that is §6).
- **As of v1.1 all four surfaces have producers attached**: `output.py` serializes `document.structure.json`/
  `document.semantic.json`/`document.provenance.json`/`document.chunks.jsonl` from the `.to_dict()` of `StructureExport`/
  `SemanticView`/`Provenance`/`ChunkRecord` respectively (§5). Therefore the contract round-trip test
  (`Contract.from_dict(read).to_dict() == read`) is itself an emission-schema regression test
  (`tests/test_export_emission.py`). Because `document.json` (Layer 0) is the loss-aware source of truth, it is not put
  through the fixed type gate and remains hand-built, while `document.structure.json` provides its **typed, versioned view**
  (original lossless, view contract-conformant).
- Distributing a separate JSON Schema is a follow-up (currently the dataclasses are the source of truth, and the tests
  guarantee spec-code sync).
