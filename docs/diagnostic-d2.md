# D-2 — Flagship-Agent Source Diagnostic (oracle position)

D-2 is the heavy diagnostic tier (processing-tiers §2.5): when D-1 (the automated built-in-VLM
diagnostic, `diagnose.py`) is not enough — hard sources, calibration, disagreement — a flagship
coding agent (Claude Code / Codex) reviews sample material **by hand** and writes a
`SourceProfile`. The agent IS the oracle position: a human-like reviewer **outside** the
pipeline, not an API the pipeline calls. D-2 produces the same `SourceProfile` as D-1, so the
run and persistence are tier-agnostic.

## Procedure

1. **Assemble the bundle.** Run `python scripts/diagnose_prepare.py --pdf <pdf> --out <bundle>`
   (omit nothing; a key adds VLM material). It writes `<bundle>/bundle.json` + `pages/page-NNN.png`.
   Each sample has: `image`, `deterministic_text`, `is_scan`, `n_tables`, `n_figures`, and (if a
   key was set) `vlm_text` + `token_divergence`.

2. **Review each sample by hand.** Open the page image and compare it to `deterministic_text`:
   - Is the deterministic text **faithful and complete** (born-digital, reading order intact)?
   - Does the page have **structure the deterministic source mangles** (complex tables, figures,
     multi-column, math) where the VLM would do better?
   - Is the page a **scan** (no/garbled text layer) needing OCR (VLM)?
   - Where `vlm_text`/`token_divergence` exist, treat them as evidence, not verdict — judge the
     image yourself. Born-digital VALUES still come from the text layer (value oracle); the VLM
     never supplies numbers.

3. **Decide the mode and calibrate.** Recommend `deterministic` or `det_vlm` for the whole
   source. There are **no universal thresholds** — set the `thresholds` you judged appropriate
   for this domain (they may override D-1's defaults). Record concrete `reasons` and `evidence`.

4. **Write the `SourceProfile`** (schema below) to `<bundle>/profile.json`. The run then uses
   `recommended_mode`; persistence (R4.4) stores it for reuse so the source is not re-diagnosed.

## SourceProfile schema (`src/parse_anything/pipeline/profile.py`)

```jsonc
{
  "source_id": "csnl",
  "recommended_mode": "deterministic | det_vlm",
  "confidence": 0.0,                       // 0..1, your judged confidence
  "tier": "D-2",
  "reasons": ["...concrete, per-evidence..."],
  "thresholds": {"scan_fraction": 0.25, "token_divergence": 0.35},  // calibrated for this domain
  "evidence": {"...measurements/notes you relied on..."},
  "created_at": "<ISO-8601>"
}
```

## When to use D-2 over D-1

- D-1's confidence is low, or its recommendation conflicts with a spot-check.
- The source is a new/unusual domain needing threshold calibration.
- A high-stakes corpus where a wrong mode is expensive (the irreversibility argument).
- Otherwise D-1 (automated) is sufficient and cheaper.
