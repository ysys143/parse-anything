"""Track B: ODL hybrid backend variants (B-1..B-4).

ODL drives the run (``opendataloader-pdf --hybrid``); its triage routes complex pages to an
HTTP backend that we provide. This package implements the no-fork proxy variants:

- B-3 (``proxy``): minimal HTTP backend, pure VLM transcription (no grounding).
- B-4 (``proxy`` + ``det_aug``): B-3 plus deterministic grounding + value-oracle/arithmetic
  guards re-parsed from the PDF in-proxy (reuses ``odl_vl.pipeline`` modules).

The DoclingDocument wire contract (what ODL's DoclingSchemaTransformer consumes) is built in
``docling_out``. See docs/parsing-engine-spike-plan.md (Track B) and the plan file.
"""
