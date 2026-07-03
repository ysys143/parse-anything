#!/usr/bin/env python3
"""Score each parser's TABLE extraction against JATS gold tables with TEDS.

Structure-aware, unlike the flat-text scorer. Reports, per parser:
  detected      how many of the N gold tables the parser produced a table for (recall of tables)
  teds          standard TEDS (includes th/thead header semantics)
  teds_geom     geometry-only TEDS (th==td, thead/tbody stripped) -- pure grid+content fidelity
  header_gap    teds_geom - teds = the header-semantics the parser fails to mark (th vs td)

This decomposition matters: a born-digital deterministic extractor (ODL) can nail grid geometry
(teds_geom ~1.0) yet miss which cells are headers (low teds) because the PDF text layer carries no
th/thead markup -- a gap a VLM that SEES the visual header can close.

Per-parser table -> HTML extractors handle each output format (ODL html, pa tables/*.json grid,
raw VLM markdown with inline <table>).
"""
from __future__ import annotations

import argparse
import glob
import json
import re
from pathlib import Path

from lxml import html

from teds import teds


# --- per-parser table -> list[html] ---------------------------------------
def tables_from_odl_html(odl_dir: str) -> list[str]:
    files = sorted(glob.glob(f"{odl_dir}/**/*.html", recursive=True))
    if not files:
        return []
    doc = html.parse(files[0])
    return [html.tostring(t, encoding="unicode") for t in doc.xpath("//table")]


def tables_from_pa(pa_out_dir: str) -> list[tuple[str, str]]:
    """pa writes tables/<id>.json as an n_rows x n_cols grid of {text,bbox}. Build plain HTML
    (all <td>, no spans -- pa's grid carries neither th nor span). Returns (label, html)."""
    out = []
    for jf in sorted(glob.glob(f"{pa_out_dir}/**/tables/*.json", recursive=True)):
        t = json.loads(Path(jf).read_text())
        rows = t.get("cells") or []
        trs = []
        for row in rows:
            tds = "".join(f"<td>{_esc(c.get('text','').strip())}</td>" for c in row)
            trs.append(f"<tr>{tds}</tr>")
        out.append((t.get("label", ""), f"<table>{''.join(trs)}</table>"))
    return out


def tables_from_markdown(pages: list[str]) -> list[str]:
    """Extract inline <table>...</table> blocks from raw VLM markdown (PaddleOCR-VL emits HTML)."""
    full = "\n".join(pages)
    return re.findall(r"<table[\s>].*?</table>", full, re.S | re.I)


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# --- scoring ---------------------------------------------------------------
def _canon(h: str) -> str:
    h = re.sub(r"</?(thead|tbody)[^>]*>", "", h, flags=re.I)
    h = re.sub(r"<th\b", "<td", h, flags=re.I)
    h = re.sub(r"</th>", "</td>", h, flags=re.I)
    return h


def score_parser(gold: list[dict], pred_html: list[str],
                 pred_labels: list[str] | None = None) -> dict:
    """Align each gold table to its best-matching predicted table (by label if available, else
    best geometry-TEDS), then average TEDS. Unmatched gold tables score 0 (a real miss)."""
    used: set[int] = set()
    rows = []
    for gi, g in enumerate(gold):
        gh = g["html"]
        cand = -1
        if pred_labels:
            for i, lab in enumerate(pred_labels):
                if i not in used and lab and g["label"] and lab.strip().lower() == g["label"].strip().lower():
                    cand = i
                    break
        if cand < 0:  # best geometry match
            best = -1.0
            for i, p in enumerate(pred_html):
                if i in used:
                    continue
                s = teds(_canon(p), _canon(gh))
                if s > best:
                    best, cand = s, i
        if cand < 0:
            rows.append({"label": g["label"], "detected": False, "teds": 0.0, "teds_geom": 0.0})
            continue
        used.add(cand)
        rows.append({
            "label": g["label"], "detected": True,
            "teds": round(teds(pred_html[cand], gh), 3),
            "teds_geom": round(teds(_canon(pred_html[cand]), _canon(gh)), 3),
        })
    n = len(gold)
    det = sum(r["detected"] for r in rows)
    mean = lambda k: round(sum(r[k] for r in rows) / n, 3) if n else 0.0
    return {"n_gold": n, "detected": det,
            "teds": mean("teds"), "teds_geom": mean("teds_geom"),
            "header_gap": round(mean("teds_geom") - mean("teds"), 3), "per_table": rows}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", required=True, help="gold tables json (gold_tables_jats.py)")
    ap.add_argument("--odl-dir", help="ODL --format html output dir")
    ap.add_argument("--pa-dir", help="parse-anything output dir (has tables/*.json)")
    ap.add_argument("--pa-label", default="pa", help="label for the pa column")
    ap.add_argument("--paddle-pages", help="paddle raw pages.json (VLM markdown)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    gold = json.loads(Path(args.gold).read_text())
    results = {}
    if args.odl_dir:
        results["odl"] = score_parser(gold, tables_from_odl_html(args.odl_dir))
    if args.pa_dir:
        pa = tables_from_pa(args.pa_dir)
        results[args.pa_label] = score_parser(gold, [h for _, h in pa], [lb for lb, _ in pa])
    if args.paddle_pages:
        pages = json.loads(Path(args.paddle_pages).read_text())
        results["paddle"] = score_parser(gold, tables_from_markdown(pages))

    Path(args.out).write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{'parser':10} {'detected':>10} {'teds':>7} {'teds_geom':>10} {'header_gap':>11}")
    for name, r in results.items():
        print(f"{name:10} {r['detected']:>4}/{r['n_gold']:<5} {r['teds']:>7.3f} {r['teds_geom']:>10.3f} {r['header_gap']:>11.3f}")


if __name__ == "__main__":
    main()
