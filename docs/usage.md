# Usage — CLI & SDK reference

Complete reference for driving `parse-anything` from the command line and as a Python library, plus the
shape of every emitted artifact and how to consume it through the versioned export contracts.

- [Install & environment](#install--environment)
- [CLI](#cli)
  - [`pdf_to_markdown` — the pipeline](#pdf_to_markdown--the-pipeline)
  - [Output artifacts](#output-artifacts)
  - [Auxiliary CLIs](#auxiliary-clis)
- [SDK](#sdk)
  - [`run_document` → `write_outputs`](#run_document--write_outputs)
  - [Options: modes, ontology, chunking](#options-modes-ontology-chunking)
  - [Consuming the output (export contracts)](#consuming-the-output-export-contracts)
- [Authoring an ontology family](#authoring-an-ontology-family)
- [Diagnosis (D-1 / D-2) and profiles](#diagnosis-d-1--d-2-and-profiles)

---

## Install & environment

Requires **Python ≥ 3.11** and **Java 17** (the `opendataloader-pdf` structure layer runs on the JVM).

```bash
uv pip install -e ".[dev]"     # editable install with test deps (pytest, reportlab)
```

Runtime dependencies (declared in `pyproject.toml`): `pypdfium2` (render + value/bbox oracle),
`opendataloader-pdf` (ODL structure + clean text, needs Java 17), `pdf-inspector` (triage),
`Pillow`, `numpy`.

### Credentials & configuration

Provider keys live only in a local `.env` (auto-loaded; never commit them). Recognised variables:

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Gemini direct VLM (required for `--mode det_vlm` with the default `gemini` transcriber) |
| `PADDLE_API_KEY` (alias `PADDLEOCR_API_KEY`) | PaddleOCR official API key (for `--primary paddle`) |
| `PADDLE_BASE_URL` (alias `PADDLEOCR_BASE_URL`) | PaddleOCR endpoint |
| `PADDLE_MODEL` | PaddleOCR model name (default `PaddleOCR-VL-1.6`) |
| `PARSE_ANYTHING_OUT_DIR` | default `--out` root (else `./out`) |
| `PARSE_ANYTHING_PROFILE_DIR` | default `SourceProfile` store (else `./profiles`) |

`.env` is loaded internally by `load_settings()`; do **not** `source .env`. Process env overrides the
`.env` file, but an empty exported var does not mask a valid `.env` value.

---

## CLI

### `parse-anything` — the pipeline

After `uv pip install -e .` (or `pip install parse-anything`), the pipeline is the **`parse-anything`**
console command (short alias **`pa`**). From a source checkout without an install, the legacy
`python scripts/pdf_to_markdown.py …` path still works.

```
parse-anything --pdf <PDF> [options]
```

The CLI is **diagnose-then-configure**: it runs one source in one configured **mode** for the whole
document (no per-page runtime routing).

#### Flags

| Flag | Default | Description |
|---|---|---|
| `--pdf PATH` | (required) | Input PDF. |
| `--out DIR` | `$PARSE_ANYTHING_OUT_DIR` or `./out` | Output root. |
| `--source-id ID` | `default` | Document-stream id; output is grouped by it. |
| `--mode {deterministic,det_vlm}` | `det_vlm` | The lever. `det_vlm` without a key is a loud error. |
| `--no-vlm` | off | Alias for `--mode deterministic`. |
| `--ontology FAMILY` | `default` | Ontology family (`default`, `paper`, or a custom `<family>.md`). |
| `--primary {gemini,paddle}` | `gemini` | det_vlm primary transcriber. `paddle` needs `PADDLE_*` env. |
| `--diagnose` | off | Run D-1 first, save a `SourceProfile`, and use the recommended mode. |
| `--use-profile` | off | Reuse a stored `SourceProfile`'s mode for `--source-id` (skip diagnosis). |
| `--profiles-dir DIR` | `$PARSE_ANYTHING_PROFILE_DIR` or `./profiles` | Profile store. |
| `--sample-size N` | `4` | Pages D-1 samples when `--diagnose`. |
| `--external-id ID` | — | Caller document id, preserved in metadata. |
| `--ingested-from SRC` | `--pdf` | Provenance origin (path/url) recorded in metadata. |
| `--force` | off | Reprocess even if this content hash was already produced. |
| `--review` | off | Also write `review.html` (source vs extraction + flags). |
| `--no-chunks` | off | Skip building `document.chunks.jsonl`. |
| `--no-ground` | off | det_vlm: skip ODL + pypdfium2 deterministic grounding (`DetVlmOptions.ground`). |
| `--no-spanning` | off | det_vlm: skip page-spanning table reconstruction (`.spanning`). |
| `--no-arithmetic` | off | det_vlm: skip the arithmetic-invariant guard (`.arithmetic`). |
| `--no-inline-figures` | off | Skip interleaving figure image refs into the page Markdown. |
| `--no-headings` | off | Skip the section-hierarchy tree + `#/##/###` in Markdown. |
| `--no-describe-figures` | off | det_vlm: skip the VLM text description per cropped vector chart. |
| `--prompt TEXT` | — | det_vlm: custom base prompt (overrides the default). |
| `--prompt-file PATH` | — | det_vlm: read the custom base prompt from a file. |

#### Modes

- **`deterministic`** — ODL text + tables, backstopped by the pypdfium2 value oracle
  (`odl_dropped_number:<v>` flags when ODL drops a printed number). No network, no keys, reproducible.
- **`det_vlm`** — adds the VLM for visual structure, reconciled against the deterministic layer. The
  born-digital value oracle gates VLM numbers (`unsourced_number:<v>` flag), and the scan-legibility gate
  lets a degraded scan abstain (`illegible_low_quality`). The `det_vlm` toggles above are all ON by
  default (opt-out).

#### Examples

```bash
# deterministic — no keys
parse-anything --pdf doc.pdf --out out/ --source-id docs --mode deterministic

# det_vlm with the paper ontology, no chunk file
parse-anything --pdf paper.pdf --out out/ --source-id papers \
  --mode det_vlm --ontology paper --no-chunks

# PaddleOCR as the primary transcriber (needs PADDLE_* env)
parse-anything --pdf scan.pdf --out out/ --source-id scans \
  --mode det_vlm --primary paddle

# diagnose the source, save a profile, then reuse it on the next run
parse-anything --pdf doc.pdf --out out/ --source-id docs --diagnose
parse-anything --pdf doc2.pdf --out out/ --source-id docs --use-profile
```

### Output artifacts

Everything lands under `<out>/<source_id>/<document_id>/` where `document_id` is a content hash, so a
re-run of the same bytes is idempotent (skipped unless `--force`).

| File | What it is |
|---|---|
| `document.md` | Assembled Markdown (human view): headings, tables, `$…$`/`$$…$$` equations, inlined `![]()` figures. |
| `document.json` | **Layer 0 — loss-aware source of truth.** Identity/provenance + `pages[]` (per-page reading-order id stream) + `blocks[]`/`tables[]`/`figures[]`/`sections[]` registries with geometry inline (`bbox`/`order`/`font_size`). Plus a non-destructive top-level overlay: `roles{id: {role, confidence, by}}`, `zones[]`, `@context`, `ontology`. |
| `document.structure.json` | **Layer 0+1 typed view** (`StructureExport`, contract `parse-anything.structure`). Same graph as a contract-tagged, typed payload; identity spread flat. |
| `document.semantic.json` | **Layer 2 clean projection** (`SemanticView`, `parse-anything.semantic`). Flat `nodes[]` with role inlined and NO geometry, the `sections[]` tree, `zones[]`, `metadata.title`, flat `reading_order[]`. |
| `document.provenance.json` | **Geometry sidecar** (`Provenance`, `parse-anything.provenance`). `prov{node_id: {page?, order?, bbox?, font_size?, regions?}}`, joined to the semantic nodes by id. |
| `document.chunks.jsonl` | **Small-to-big RAG chunks**, one `ChunkRecord` (`parse-anything.chunks`) per line. |
| `tables/<id>.{json,md}` | Per-table cell JSON + Markdown view. |
| `assets/<id>.png` | Cropped figure images. |
| `pages/page-NNN.md` | Per-page Markdown. |
| `ledger.jsonl`, `results.jsonl` | Per-page route + flags. |

#### Node types (semantic view)

Each `nodes[]` entry carries `id`, `type` (the role), `zone`, and type-specific fields:

- `title` / `heading` / `paragraph` / `list_item` — `text` (+ `level` for headings that open a section, `section`, `refs`).
- `caption` — `text`, `caption_of` (the figure/table id); the host carries `caption_ref`.
- `reference` — `text`, `marker?` (numeric/circled), inside the `references` zone.
- `figure` — `label?`, `kind?`, `source` (`odl_image`/`vlm`/`vector`), `file?`, `caption_ref?`, `description?`.
- `table` — `label?`, `n_rows`/`n_cols`, `cells[][]`, `views?`, `caption_ref?`.
- `equation` — `latex`, `display?`.

**Zones** (orthogonal axis): `cover`, `metadata`, `toc`, `body`, `references`, `appendix`, `furniture`.
`furniture` (extraction noise / glyph-garbled math) is kept in `nodes[]` but excluded from `reading_order`
and the chunks.

#### Chunk record (chunks.jsonl line)

`{contract, id, level(parent|child), parent_id?, children?[], doc_id, structural_type(section|page|text|table|figure|equation), zone, role?, heading_path[], display_text, embedding_text?, token_count, tokenizer, atomic, is_continuation, prev?, next?, source_refs{nodes[], pages[min,max]}, node_types[], refs?, meta?}`

Index the **children** (focused leaves; `embedding_text` prepends the heading breadcrumb) and return the
**parent** (whole section / page group). Atomics (`table`/`figure`/`equation`) are kept whole
(`atomic: true`, one node in `source_refs.nodes`). See [export-contracts.md](export-contracts.md) for the
full field spec and [agent-ready-schema-and-chunking.md](agent-ready-schema-and-chunking.md) for the design.

### Auxiliary CLIs

```bash
# self-contained HTML viewer for one output dir -> <dir>/viewer.html (double-click, no server)
uv run --no-sync python scripts/build_viewer.py --dir out/docs/<document_id>/ [--out viewer.html]

# D-1 source diagnosis -> recommended mode + evidence (JSON)
uv run --no-sync python scripts/diagnose_source.py --pdf doc.pdf

# D-2 review bundle for hard sources / per-domain threshold calibration
uv run --no-sync python scripts/diagnose_prepare.py --pdf doc.pdf --out bundle/

# provider config presence check (never prints key values)
uv run --no-sync python scripts/parse_anything_smoke.py --provider gemini --dry-config
uv run --no-sync python scripts/parse_anything_smoke.py --provider paddle --dry-config
```

---

## SDK

`import parse_anything` after `uv pip install -e .`. The pipeline is two calls: **`run_document`** (extract
into a `DocumentResult`) → **`write_outputs`** (emit the layered artifacts).

### `run_document` → `write_outputs`

```python
def run_document(
    pdf_path: str, *,
    mode: str = "det_vlm",              # "deterministic" | "det_vlm"
    vlm_client=None,                    # ProviderHttpClient; required for det_vlm
    api_key: str = "",                  # GEMINI key for det_vlm
    odl_runner=None,                    # override the ODL structure runner (tests/advanced)
    source_id: str = "default",
    external_id: str | None = None,
    ingested_from: str | None = None,
    options=None,                       # DetVlmOptions (det_vlm behaviour toggles)
    primary_transcribe=None,            # a paddle transcriber callable (for --primary paddle)
) -> DocumentResult

def write_outputs(
    result: DocumentResult, out_dir: str | Path, *,
    pdf_path: str | None = None,        # needed to crop vector-figure assets
    arithmetic: bool = True,
    inline_figures: bool = True,
    headings: bool = True,
    describe_figure=None,               # Callable[[png_bytes, caption|None], str] for figure descriptions
    ontology=None,                      # Ontology; None -> bundled "default"
    chunk: bool = True,                 # emit document.chunks.jsonl
) -> None

def document_dir(out_root: str | Path, result: DocumentResult) -> Path   # <out_root>/<source_id>/<document_id>
```

**Deterministic (no keys, no network):**

```python
from parse_anything.pipeline.run import run_document
from parse_anything.pipeline.output import document_dir, write_outputs

result = run_document("doc.pdf", mode="deterministic", source_id="docs")
out = document_dir("out/", result)
write_outputs(result, out, pdf_path="doc.pdf")     # ontology=None -> bundled default; chunk=True
```

**det_vlm (VLM client + key):**

```python
from parse_anything.config import load_settings
from parse_anything.cli_support import Runtime, safe_client
from parse_anything.pipeline.run import run_document
from parse_anything.pipeline.output import document_dir, write_outputs

settings = load_settings(env_file=".env")          # -> Settings(gemini_api_key, paddle_*, ...)
client = safe_client(Runtime())                    # ProviderHttpClient

result = run_document(
    "doc.pdf", mode="det_vlm",
    vlm_client=client, api_key=settings.gemini_api_key,
    source_id="papers",
)
write_outputs(result, document_dir("out/", result), pdf_path="doc.pdf")
```

`Settings` fields: `gemini_api_key`, `paddle_api_key`, `paddle_base_url`, `paddle_model`, plus `has_gemini` /
`has_paddle` properties.

### Options: modes, ontology, chunking

**det_vlm behaviour** — pass a `DetVlmOptions` to `run_document(options=...)` (all default ON):

```python
from parse_anything.pipeline.assemble import DetVlmOptions

opts = DetVlmOptions(
    ground=True,              # inject ODL + pypdfium2 grounding
    spanning=True,            # reconstruct page-spanning tables
    arithmetic=True,          # arithmetic-invariant guard
    reading_order=True,       # re-sequence VLM blocks into ODL reading order
    input_quality_min=50.0,   # Laplacian-variance blur threshold
    primary="gemini",         # "gemini" | "paddle"
    prompt=None,              # custom base prompt
)
result = run_document("doc.pdf", mode="det_vlm", vlm_client=client,
                      api_key=key, options=opts, source_id="docs")
```

**Ontology injection** — swap the tagging vocabulary/rules with no code change:

```python
from parse_anything.pipeline.ontology import load_ontology, bundled_ontology_root

onto = load_ontology("paper", bundled_ontology_root())     # bundled family
# or a custom directory:  load_ontology("contract", "/path/to/my/ontologies")
write_outputs(result, out, pdf_path="doc.pdf", ontology=onto)
```

**Chunking** — controlled by the ontology's `chunking:` block (a `ChunkPolicy`) and the `chunk` flag:

```python
# ChunkPolicy(child_tokens=384, tokenizer="cl100k_base", parent="section",
#             keep_atomic=("table","figure","equation"))  -- from ontology frontmatter
write_outputs(result, out, pdf_path="doc.pdf", chunk=False)   # skip chunk emission entirely
```

### Consuming the output (export contracts)

`parse_anything.export` gives typed, versioned readers for the emitted JSON. Every payload carries a
`{name, version}` `contract` tag; `from_dict` drops unknown keys (forward-compat); `check_compatible`
gates on the **major** version.

```python
import json
from parse_anything.export import (
    StructureExport, SemanticView, Provenance, ChunkRecord,
    STRUCTURE_CONTRACT, SEMANTIC_CONTRACT, PROVENANCE_CONTRACT, CHUNK_CONTRACT,
    check_compatible, contract_tag,
)

d = json.load(open(out / "document.semantic.json"))
assert check_compatible(d["contract"], SEMANTIC_CONTRACT)
sem = SemanticView.from_dict(d)
print(sem.metadata.get("title"), len(sem.nodes), sem.zones, sem.sections)

prov = Provenance.from_dict(json.load(open(out / "document.provenance.json")))
bbox = prov.prov[sem.nodes[0]["id"]].get("bbox")        # join semantic <-> geometry by node id

for line in open(out / "document.chunks.jsonl"):
    row = json.loads(line)
    if not check_compatible(row["contract"], CHUNK_CONTRACT):
        continue
    c = ChunkRecord.from_dict(row)
    if c.level == "child":
        embed(c.embedding_text)                          # index the leaves
        # c.parent_id, c.heading_path, c.source_refs["nodes"], c.source_refs["pages"], c.atomic ...
```

Contract surfaces and their JSON files:

| Contract | Type | File |
|---|---|---|
| `parse-anything.structure` | `StructureExport` | `document.structure.json` |
| `parse-anything.semantic` | `SemanticView` | `document.semantic.json` |
| `parse-anything.provenance` | `Provenance` | `document.provenance.json` |
| `parse-anything.chunks` | `ChunkRecord` | `document.chunks.jsonl` |

Full field lists for every contract (and the `Block`/`Table`/`Figure`/`Section`/`PageEntry`/`Cell`/`Region`/
`RoleAssignment` node types) are in [export-contracts.md](export-contracts.md).

---

## Authoring an ontology family

An ontology is one Markdown file per family (`ontology/<family>.md`) with a YAML frontmatter and a
human-readable body. The bundled families are `src/parse_anything/ontology/{default,paper}.md`.

```markdown
---
id: pa:ontology/myfamily
version: 1.0.0
default_zone: body
node_types:
  title:     {meaning: doco:Title}
  heading:   {meaning: doco:Subtitle}
  paragraph: {meaning: doco:Paragraph}
  figure:    {meaning: doco:FigureBox, atomic: true}
  table:     {meaning: doco:TableBox,  atomic: true}
  equation:  {meaning: doco:FormulaBox, atomic: true}
  caption:   {meaning: doco:Caption}
  reference: {meaning: deo:BibliographicReference}
zones: [cover, metadata, toc, body, references, appendix, furniture]
figure_kinds: [chart, plot, diagram, photo, map, logo, icon, full_page_image, decoration]
rules:                              # ORDERED; first match wins per axis (type / zone)
  - {id: noise-furniture, when: {text_degenerate: true}, then: {zone: furniture}}
  - {id: doc-title, when: {all: [{page_index: {eq: 0}}, {odl_role: {in: [Doctitle, Title]}}]}, then: {type: title, zone: cover}}
  - {id: references-zone, when: {all: [{page_frac: {gte: 0.4}}, {text_matches: '(?i)^\s*references\s*$'}]}, then: {zone: references, opens_zone: true}}
  - {id: numbered-heading, when: {classify_numbering: not_null}, then: {type: heading, level: from_numbering}}
  - {id: default-text, when: {}, then: {type: paragraph}}
chunking: {child_tokens: 384, tokenizer: cl100k_base, parent: section, keep_atomic: [table, figure, equation]}
---
# My family
Human docs for the rules above.
```

**Rule engine** — ordered, first-match-per-axis over a fixed predicate registry (no `eval`):

- **Signal predicates** (compared with `{eq|in|not_in|gte|lte|gt|lt|not_null: …}` or a bare scalar):
  `page_index`, `page_frac`, `odl_type`, `odl_role`, `odl_heading_level`, `font_size`, `font_rank`,
  `is_landscape`, `bbox_area_frac`, `centered`, `text`.
- **Special predicates**: `classify_numbering` (is the text a recognised numbering prefix — bool;
  `not_null` / `{eq: true}` require numbering, `{eq: false}` requires its absence), `text_matches`
  (regex, `(?i)` for case-insensitive), `text_degenerate` (repeated-token / single-char extraction noise).
- **Combinators**: `all`, `any`, `not`.
- **`then` axes**: `type`, `zone`, `level` (`from_numbering` | `from_font_rank`), `opens_zone` (a
  back-matter heading opens the zone for the nodes that follow, to end of document — used only by
  `references`/`appendix`).

Structure (nesting) comes only from the numbering class or the document's own outline authority (PDF
bookmarks / printed TOC) — never from font size. The ontology assigns role + zone; it never fabricates a
hierarchy. Inject at runtime with `--ontology <family>` (CLI) or `load_ontology(family, root)` (SDK).

---

## Diagnosis (D-1 / D-2) and profiles

`--diagnose` runs **D-1** (`scripts/diagnose_source.py`): it measures deterministic-vs-VLM token
divergence, scan fraction, and structure-aware-sampled table/figure presence, then recommends
`deterministic` vs `det_vlm` with evidence and saves a reusable `SourceProfile` (under
`$PARSE_ANYTHING_PROFILE_DIR` or `./profiles`). `--use-profile` reuses that profile's mode without
re-diagnosing. **D-2** (`scripts/diagnose_prepare.py`) assembles a review bundle for hard sources and
per-domain threshold calibration — see [diagnostic-d2.md](diagnostic-d2.md). Both persist a
`SourceProfile`; the mode is the lever, chosen by measurement, and then the whole document uses it.
