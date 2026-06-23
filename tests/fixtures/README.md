# Fixture Manifest Contract

This directory contains metadata for the initial public generated fixture set. It intentionally does not contain generated PDFs, images, private document paths, downloaded benchmarks, or live provider outputs.

## Files

- `manifest.json`: the eight initial fixture families and the metadata needed to generate, route, mutate, and score them later.
- `golden_schema.json`: the JSON-only page-level golden record contract that future generated fixture answers must follow.

## Initial Families

- `simple_text`: born-digital simple body text for deterministic-only baseline checks.
- `two_column_ko_en`: two-column Korean and English text with footnotes for reading-order checks.
- `merged_table`: merged cells, nested headers, and unit rows for table fidelity checks.
- `formula_symbols`: formulas, subscripts, arrows, and special symbols for OCR contamination checks.
- `chart_like_page`: chart or diagram content for semantic image-description checks.
- `text_as_image`: raster text without a text layer for OCR routing and text recovery checks.
- `rotated_scan`: rotated or skewed scan-like content for orientation routing checks.
- `low_quality_scan`: blurred, compressed, low-resolution scan-like content for robustness checks.

## Generation Policy

The manifest is metadata-only. Future tasks may generate public synthetic artifacts from these recipes, but those artifacts are not part of this task. Any private shadow set must remain outside this repository and may only be represented here by non-sensitive family-level metadata.

## Scoring Policy

Golden records are page-level JSON records. They should capture reading order, table structure, key fields, image-description expectations, bounding-box tolerance, provider-specific allowances, and scoring metrics. The schema is deliberately plain JSON so fixture validation does not add a YAML dependency.

This is the current slice contract, not the full PDF pipeline contract. Before
claiming compliance with the full requirements, fixture scoring must add
document-level records for page-spanning tables, merged logical table ids,
numeric source-oracle expectations, arithmetic invariant checks, hallucination
guard flags, orientation correction, processing-depth routing, and privacy-safe
provider routing.
