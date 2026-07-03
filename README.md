# parse-anything

Deterministic-first, ontology-driven PDF parsing into **agent-ready layered artifacts + RAG chunks**.

`parse-anything` turns a PDF into a clean, tagged document graph and ready-to-embed chunks. Structure
(chapters/sections, tables, figures, equations, references) is recovered **deterministically** — from
numbering, the PDF outline / printed table of contents, and geometry — and is *never* hallucinated. The
semantic role of each node (title / heading / paragraph / caption / reference / …) and its zone
(cover / metadata / body / references / appendix / furniture) come from an **external, runtime-injectable
ontology**, so the tagging generalises across document families and languages (validated on EN and KR
papers/reports). A VLM (Gemini or PaddleOCR) is used only when configured, and only for visual structure /
transcription — gated by a born-digital value oracle so it can never invent numbers.

## What you get

One run writes a set of layered artifacts under `<out>/<source_id>/<document_id>/`
(`document_id` = content hash, so re-processing is idempotent):

| Artifact | Layer | What it is |
|---|---|---|
| `document.md` | — | Human-readable assembled Markdown (equations as `$…$`, figures inlined) |
| `document.json` | 0 | **Loss-aware source of truth**: raw extraction graph with geometry inline (bbox/order/font), identity + provenance, per-page reading order, blocks/tables/figures/sections. Plus a non-destructive top-level `roles`/`zones`/`@context`/`ontology` overlay |
| `document.structure.json` | 0+1 | Typed, contract-tagged view of Layer 0 (`StructureExport`) |
| `document.semantic.json` | 2 | **Clean projection**: a flat `nodes[]` pool with role inlined and NO geometry, the section tree, `zones[]`, `metadata.title`, and a flat `reading_order` (`SemanticView`) |
| `document.provenance.json` | 2 | Geometry sidecar (`bbox`/`order`/`font_size`/`regions`) keyed by the same node id (`Provenance`) |
| `document.chunks.jsonl` | chunks | **Small-to-big RAG chunks**: a parent per section (or page group) + token-packed children, atomics kept whole (`ChunkRecord`) |
| `tables/` · `assets/` · `pages/` | — | Per-table JSON+MD, cropped figure images, per-page Markdown |
| `ledger.jsonl` · `results.jsonl` | — | Per-page route/flags |

All run artifacts are git-ignored.

## Install

**Prebuilt, self-contained** — no Python or Java needed. Installs `parse-anything` (aliases `parse`, `pa`)
under `~/.local` and adds it to your PATH. Re-run to update; add `-s -- --uninstall` to remove.

```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/ysys143/parse-anything/main/install.sh | sh
```
```powershell
# Windows (PowerShell)
irm https://raw.githubusercontent.com/ysys143/parse-anything/main/install.ps1 | iex
```

> The prebuilt installer pulls a release bundle, so it works once a version is tagged on
> [Releases](https://github.com/ysys143/parse-anything/releases). Until then, install from source.

**From source** (dev; needs Python ≥ 3.11 and **Java 17** for the `opendataloader-pdf` layer):

```bash
uv pip install -e ".[dev]"     # installs the `parse-anything` command (aliases `parse`, `pa`)
```

## Quickstart

```bash
# deterministic only -- no network, no keys
parse-anything --pdf doc.pdf --out out/ --source-id mydocs --mode deterministic

# accuracy mode -- adds the VLM (needs GEMINI_API_KEY in .env)
parse-anything --pdf doc.pdf --out out/ --source-id mydocs --mode det_vlm

# pick the ontology family (default | paper) and/or skip chunk building
parse-anything --pdf paper.pdf --out out/ --source-id papers \
  --mode det_vlm --ontology paper --no-chunks
```

Provider keys live only in a local `.env` (auto-loaded; see `.env.example` for the variable names) — never
committed. `det_vlm` without a `GEMINI_API_KEY` is a **loud error, never a silent downgrade**.

### Visualize the output

```bash
uv run --no-sync python scripts/build_viewer.py --dir out/mydocs/<document_id>/
```

Writes a self-contained, double-clickable `viewer.html` (semantic nodes / section tree / small-to-big
chunks / zones + stats / figure gallery + equations & references; KaTeX with a raw-LaTeX fallback).

### Python SDK

Two calls — `run_document` (extract) → `write_outputs` (emit the layered artifacts):

```python
from parse_anything.pipeline.run import run_document
from parse_anything.pipeline.output import document_dir, write_outputs

# deterministic: no keys, no network
result = run_document("doc.pdf", mode="deterministic", source_id="docs")
out = document_dir("out/", result)
write_outputs(result, out, pdf_path="doc.pdf")   # ontology=None -> bundled default; chunk=True

# consume the clean view + RAG chunks through the versioned contracts
import json
from parse_anything.export import SemanticView, ChunkRecord, CHUNK_CONTRACT, check_compatible

sem = SemanticView.from_dict(json.load(open(out / "document.semantic.json")))
for line in open(out / "document.chunks.jsonl"):
    row = json.loads(line)
    assert check_compatible(row["contract"], CHUNK_CONTRACT)
    chunk = ChunkRecord.from_dict(row)
```

For `det_vlm` (VLM client + `GEMINI_API_KEY`), ontology injection, chunk-policy control, the full CLI flag
table, and the field-level output schema, see **[docs/usage.md](docs/usage.md)**.

## Modes

The CLI is **diagnose-then-configure**, not per-page runtime routing (auto-routing measured as a
false-positive gamble). Both modes use ODL
(structure / clean text) + pypdfium2 (value completeness / bbox):

- **`deterministic`** — ODL text + tables with a pypdfium2 value-completeness backstop
  (`odl_dropped_number:<v>` flags). No network, no keys.
- **`det_vlm`** — adds the VLM for visual structure, reconciled; the born-digital **value oracle**
  (pypdfium2) gates VLM numbers (`unsourced_number:<v>`), and the scan-legibility gate lets a degraded
  scan abstain (`illegible_low_quality`). **The mode is the lever.**

Let D-1 measure the source and pick the mode (saving a reusable `SourceProfile`):

```bash
parse-anything --pdf doc.pdf --out out/ --source-id mydocs --diagnose
parse-anything --pdf doc.pdf --out out/ --source-id mydocs --use-profile
```

D-1 (`scripts/diagnose_source.py`) measures deterministic-vs-VLM token divergence + scan fraction +
table/figure presence; D-2 (`scripts/diagnose_prepare.py`) assembles a review bundle for hard sources /
per-domain threshold calibration.

## Ontology-driven tagging

Every node carries a **semantic role** (title / heading / paragraph / caption / reference / equation / …)
and a **zone** (body / front-matter / back-matter / furniture / …). That vocabulary and the
signal→role/zone rules are *data*, not code: they live in `src/parse_anything/ontology/<family>.md`
(Markdown + YAML frontmatter, bundled in the wheel). Two families ship — `default` and `paper` — selected
with `--ontology <family>`; authoring a new document family is a new `ontology/<family>.md`, not a code
change. The chosen profile (name + version) is recorded in the output so a consumer knows which taxonomy it
is reading.

- **Rule engine** = ordered, **first-match-per-axis** rules over a fixed, tested predicate registry
  (`page_index`, `page_frac`, `odl_type`, `odl_role`, `classify_numbering`, `text_matches`,
  `text_degenerate`, `font_rank`, …). No `eval`, no code injection — every predicate is a named,
  unit-tested function.
- **Structure stays deterministic** (numbering / outline authority / geometry decide the tree); the
  ontology only overlays role + zone on top. The overlay is **non-destructive**: in `document.json` the
  roles/zones sit in a top-level layer keyed by node id (Layer 0 geometry is never mutated), and only the
  Layer 2 `document.semantic.json` inlines the role and drops geometry.
- Concrete effects: front-matter, extraction noise, and glyph-garbled math debris are **zoned out of the
  body** (not deleted — still addressable); reference lists are split into **per-entry nodes**; captions
  and display equations are **promoted to first-class nodes** so retrieval and grounding can target them.

## Versioned export contracts

`src/parse_anything/export/` defines the stable, versioned surfaces the pipeline emits through, so a
downstream consumer (RAG ingestion, KG builder) binds to a **contract**, not to internal shapes. The
surfaces map onto the layered artifacts:

| Contract (`name`) | Artifact | Layer | Role |
|---|---|---|---|
| `parse-anything.structure` (`StructureExport`) | `document.structure.json` | 0+1 | typed, contract-tagged view of the loss-aware graph + role/zone overlay |
| `parse-anything.semantic` (`SemanticView`) | `document.semantic.json` | 2 | clean node pool, role inlined, geometry removed |
| `parse-anything.provenance` (`Provenance`) | `document.provenance.json` | 2 | geometry sidecar (bbox/order/font/regions) keyed by node id |
| `parse-anything.chunks` (`ChunkRecord`) | `document.chunks.jsonl` | chunks | small-to-big RAG chunks |

- **Small-to-big chunk model** (`ChunkRecord`): a **parent** per section (or page group) lists its
  token-packed **children**; atomics (table / figure / equation) are kept whole. Each child carries a
  `heading_path` breadcrumb, `display_text` (what to show) vs `embedding_text` (breadcrumb-prefixed, so a
  focused child still embeds with its structural context), and `source_refs` (node ids + page span) — the
  round-trip back to Layer 0 for citation / bbox grounding.
- **Versioning**: every payload carries a `{name, version}` tag. `from_dict` drops unknown keys
  (forward-compat — a newer producer can add fields without breaking an older consumer); `check_compatible`
  gates a consumer on the **major** version only.
- **Self-checking**: `output.py` serializes each artifact *through* its contract's `.to_dict()`, so
  reading a file back and re-serializing is a no-op — the contract round-trip is the emission's
  schema-regression test. See [export contracts](docs/export-contracts.md).

## RAG / graph integration (LightRAG first-class)

`parse-anything` is **RAG-neutral** — the [export contracts](#versioned-export-contracts) are the seam, so
its output feeds any RAG/graph tool, and there is no LightRAG import in the core. That said, **LightRAG is a
first-class integration target**: we verify it end-to-end and keep a canonical, provider-agnostic recipe for
it. "Provider-agnostic" means the recipe plugs any LLM/embedding backend behind LightRAG's `llm_model_func`
/ `embedding_func`; the only cross-provider requirements are **R1** (embedding returns N vectors for N
texts, fixed dim) and **R2** (the keyword-extraction call returns a single strict JSON object).

Two blessed ingest paths — both keep the chunk boundaries **we** own; they differ in who owns the KG:

| Path | Chunk boundaries | Knowledge graph | `file_path` anchor | Ingest LLM cost |
|---|---|---|---|---|
| **Delimiter (`ainsert`)** | ours, via a sanitize-surviving delimiter | LightRAG extracts it | [O] preserved | high (LightRAG extraction) |
| **`ainsert_custom_kg` + concept fusion** | ours, exact | **ours** — structure (sections/figures) fused with concepts we extract | [O] preserved | our call (0 for structure-only) |

The second path is the full "we own structure, extraction, and ontology" posture; the first is the simplest
complete option when letting LightRAG own the KG is fine. Query with `hybrid` (graph) or `mix` (graph +
vector chunks). **Avoid `ainsert_custom_chunks`** — it embeds chunks but never merges the KG, so only
vector/naive retrieval works. Full recipes, pitfalls (delimiter sanitize, oversize hard-split, keyword
JSON), and a runnable isolated demo (`demo/docker/`) are in the
[LightRAG integration guide](docs/lightrag-integration-guide.md).

## Development

```bash
cd tests && uv run --no-sync python -m pytest -q      # full suite
uv run --with ruff ruff check .                       # lint
```

## Documentation

- [Usage](docs/usage.md) — full CLI & SDK reference, output schema, ontology authoring.
- [Export contracts](docs/export-contracts.md) — the versioned Layer-0/1/2 + chunk surfaces.
- [PDF pipeline requirements](docs/pdf-pipeline-requirements.md) — the mandatory full-pipeline contract
  (rendering, processing-depth, complex/page-spanning tables, numeric guards, outputs, privacy).
- [LightRAG integration guide](docs/lightrag-integration-guide.md) — canonical recipes for the two verified
  ingest paths (delimiter / `custom_kg` + concept fusion), pitfalls, and a runnable demo. Provider-agnostic.

Internal design notes, requirements rationale, and measurement evidence live under `docs/.design/`
(not part of the public reference).

> Not production-ready; interfaces may change. Provider credentials must stay in local environment
> configuration only and must never be committed.
