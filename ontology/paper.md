---
id: odl:ontology/paper
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
  - {id: doc-title, when: {all: [{page_index: {eq: 0}}, {odl_role: {in: [Doctitle, Title]}}]}, then: {type: title, zone: cover}}
  - {id: abstract-metadata, when: {all: [{page_index: {lte: 1}}, {text_matches: '(?i)^\s*(?:abstract|요\s*약|초\s*록)\b'}]}, then: {zone: metadata}}
  - {id: keywords-metadata, when: {text_matches: '(?i)^\s*(?:keywords|key\s+words|index\s+terms|주\s*제\s*어)\b'}, then: {zone: metadata}}
  - {id: references-zone, when: {all: [{page_frac: {gte: 0.4}}, {text_matches: '(?i)^\s*(?:\d+\.?\s+)?(?:references|bibliography|works\s+cited|literature\s+cited|참고\s*문헌|参考文献)\s*$'}]}, then: {zone: references, opens_zone: true}}
  - {id: appendix-zone, when: {all: [{page_frac: {gte: 0.4}}, {text_matches: '(?i)^\s*(?:\d+\.?\s+|appendix\s+)?(?:appendix|supplementary|supporting\s+information|부록|附録)\b'}]}, then: {zone: appendix, opens_zone: true}}
  - {id: numbered-heading, when: {classify_numbering: not_null}, then: {type: heading, level: from_numbering}}
  - {id: prose-heading, when: {any: [{odl_type: {eq: heading}}, {odl_role: {in: [Subtitle, Sectiontitle, Sectionheader]}}, {odl_heading_level: {gte: 1}}]}, then: {type: heading, level: from_font_rank}}
  - {id: list-item, when: {odl_type: {eq: list item}}, then: {type: list_item}}
  - {id: default-text, when: {}, then: {type: paragraph}}
chunking: {child_tokens: 384, tokenizer: cl100k_base, parent: section, keep_atomic: [table, figure, equation]}
---
# Academic-paper ontology

Extends the default with paper-specific zoning: an `abstract`/`요약` block on the front page and a
`keywords` line are tagged into the `metadata` zone, and the references section opens a `references`
zone. Everything else follows the default rules.

Select at runtime with `--ontology paper`. Swapping `--ontology default` vs `--ontology paper` changes
the tagging with no code change — the ontology is injected, not compiled in.
