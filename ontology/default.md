---
id: odl:ontology/default
version: 1.0.0
conformsTo: https://sparontologies.github.io/doco/
default_zone: body
node_types:
  title: {meaning: doco:Title}
  heading: {meaning: doco:Subtitle}
  paragraph: {meaning: doco:Paragraph}
  list_item: {meaning: doco:ListItem}
  figure: {meaning: doco:FigureBox, atomic: true}
  table: {meaning: doco:TableBox, atomic: true}
  equation: {meaning: doco:FormulaBox, atomic: true}
  caption: {meaning: doco:Caption}
  reference: {meaning: deo:BibliographicReference}
zones: [cover, metadata, toc, body, references, appendix, furniture]
figure_kinds: [chart, plot, diagram, photo, map, screenshot, logo, icon, full_page_image, decoration]
rules:
  - {id: noise-furniture, when: {text_degenerate: true}, then: {zone: furniture}}
  - {id: math-garble-furniture, when: {text_matches: '[ðÐÞþ]|[A-Za-z]\s*¼\s*\d'}, then: {zone: furniture}}
  - {id: doc-title, when: {all: [{page_index: {eq: 0}}, {odl_role: {in: [Doctitle, Title]}}]}, then: {type: title, zone: cover}}
  - {id: references-zone, when: {all: [{page_frac: {gte: 0.4}}, {text_matches: '(?i)^\s*(?:\d+\.?\s+)?(?:references|bibliography|works\s+cited|literature\s+cited|참고\s*문헌|参考文献)\s*$'}]}, then: {zone: references, opens_zone: true}}
  - {id: appendix-zone, when: {all: [{page_frac: {gte: 0.4}}, {text_matches: '(?i)^\s*(?:\d+\.?\s+|appendix\s+)?(?:appendix|supplementary|supporting\s+information|부록|附録)\b'}]}, then: {zone: appendix, opens_zone: true}}
  - {id: toc-zone, when: {text_matches: '(?i)^\s*(?:contents|table\s+of\s+contents|목차|目次)\s*$'}, then: {zone: toc, opens_zone: true}}
  - {id: front-matter-metadata, when: {all: [{page_frac: {lte: 0.2}}, {text_matches: '(?i)^\s*(?:open\s+access|citation\s*:|received\s*:|accepted\s*:|published\s*:|revised\s*:|copyright\b|competing\s+interests\b|conflict\s+of\s+interest|funding\s*:|data\s+availability|abbreviations\s*:|academic\s+editor\b|peer\s+review\s+history|correspondence\s*:|doi\s*:|issn\s*:|©)'}]}, then: {zone: metadata}}
  - {id: numbered-heading, when: {classify_numbering: not_null}, then: {type: heading, level: from_numbering}}
  - {id: prose-heading, when: {any: [{odl_type: {eq: heading}}, {odl_role: {in: [Subtitle, Sectiontitle, Sectionheader]}}, {odl_heading_level: {gte: 1}}]}, then: {type: heading, level: from_font_rank}}
  - {id: list-item, when: {odl_type: {eq: list item}}, then: {type: list_item}}
  - {id: default-text, when: {}, then: {type: paragraph}}
chunking: {child_tokens: 384, tokenizer: cl100k_base, parent: section, keep_atomic: [table, figure, equation]}
---
# Default document ontology

The general, document-type-agnostic ontology used when no family is specified.

## Axes

Every content node is tagged on two orthogonal axes:

- **type** (what it is): `title`, `heading` (+`level`), `paragraph`, `list_item`, `figure`, `table`,
  `equation`, `caption`, `reference`.
- **zone** (where it sits): `cover`, `metadata`, `toc`, `body`, `references`, `appendix`, `furniture`.
  The default zone is `body`; `opens_zone` rules set the zone for the heading and every following node
  until another `opens_zone` rule fires.

## Rules (ordered; first match wins per axis)

0. `noise-furniture` — extraction NOISE (one token/character repeated, e.g. `a1111 a1111 a1111 …` or a
   divider run) is tagged `zone: furniture` so it leaves the `body`/reading flow. High precision; prose
   never trips it (see `_is_degenerate_text`). Layer 0 `document.json` still keeps it (loss-aware).
0b. `math-garble-furniture` — glyph-garbled math-font fragments (eth/thorn `ð`/`Þ` mis-maps, or a
   `letter¼digit` where `¼` is a mangled `=`) are tagged `zone: furniture`. In `det_vlm` the clean equation
   is harvested from the VLM markdown (standalone `$…$` display lines), so these deterministic-layer
   fragments are redundant debris. Targets EN/KR/JP docs (no legitimate eth/thorn); not a glyph rewrite.
1. `doc-title` — a page-1 block ODL tagged as `Doctitle`/`Title` is the document title (zone `cover`).
2. `references-zone` / `appendix-zone` / `toc-zone` — a heading whose text names the section opens that
   zone for the nodes that follow (independent of whether the heading itself is admitted as a section).
2b. `front-matter-metadata` — near the document front (`page_frac <= 0.2`), journal furniture labels
   (OPEN ACCESS, Citation:, Received/Accepted/Published:, Copyright/©, Competing interests, Funding:,
   Data Availability, Abbreviations:, Academic Editor, DOI:, ISSN:, …) are tagged `zone: metadata` for
   that node only (no `opens_zone`), so they leave the `body`/reading flow without touching the abstract.
3. `numbered-heading` — a recognised numbering prefix (第N章 / 1.2 / (N) / Ⅰ / 제N조 …) → heading, level
   from the numbering class.
4. `prose-heading` — an UNNUMBERED heading recovered from ODL's own signal (`odl_type == heading`, an ODL
   structural role, or `heading_level >= 1`) → heading, level from the document's font-size ranking. This
   is what recovers "Introduction"/"Methods"-style headings that carry no numbering.
5. `list-item` / `default-text` — everything else keeps its ODL kind.

Admission is still vetoed by the conservative prose/list/caption guards in `sections.py`; the ontology
proposes, the guards dispose.

## Adding a document family

Copy this file to `ontology/<family>.md`, adjust the `zones`/`node_types`, and add or reorder `rules`.
No pipeline code changes — the family is selected at runtime with `--ontology <family>`.
