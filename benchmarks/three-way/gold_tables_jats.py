#!/usr/bin/env python3
"""Extract GOLD tables from a JATS XML as normalized HTML (for TEDS scoring).

Each JATS <table-wrap> carries a real <table> with <tr>/<td>/<th> + colspan/rowspan -- the
publisher's human-edited table structure. That is the independent ground truth a born-digital
table extractor (ODL) must reproduce, and which a flat-text metric cannot see.

Emits corpus/tables/<stem>.gold.json: [{label, caption, html, n_rows, n_cells}] in document order.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from lxml import etree, html


def _norm_table_html(table_el) -> str:
    """Serialize a JATS <table> to a minimal normalized HTML string: keep only structural tags +
    colspan/rowspan, drop all styling/ids so TEDS compares STRUCTURE + TEXT, not markup noise."""
    keep_attrs = {"colspan", "rowspan"}
    # rebuild a clean tree
    def clean(el):
        tag = etree.QName(el).localname
        if tag not in ("table", "thead", "tbody", "tr", "td", "th"):
            return None
        new = html.Element(tag)
        for a in keep_attrs:
            if el.get(a):
                new.set(a, el.get(a))
        text = re.sub(r"\s+", " ", " ".join(el.itertext())).strip() if tag in ("td", "th") else ""
        if text:
            new.text = text
        if tag not in ("td", "th"):
            for c in el:
                cc = clean(c)
                if cc is not None:
                    new.append(cc)
        return new
    cleaned = clean(table_el)
    return html.tostring(cleaned, encoding="unicode") if cleaned is not None else ""


def extract(xml_path: Path) -> list[dict]:
    root = etree.parse(str(xml_path)).getroot()
    out = []
    for tw in root.findall(".//table-wrap"):
        table = tw.find(".//table")
        if table is None:
            continue
        rows = table.findall(".//tr")
        cells = table.findall(".//td") + table.findall(".//th")
        if len(rows) < 2:            # skip trivial/degenerate
            continue
        label = tw.find(".//label")
        caption = tw.find(".//caption")
        out.append({
            "label": " ".join(label.itertext()).strip() if label is not None else "",
            "caption": re.sub(r"\s+", " ", " ".join(caption.itertext())).strip()[:200] if caption is not None else "",
            "html": _norm_table_html(table),
            "n_rows": len(rows),
            "n_cells": len(cells),
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    tables = extract(Path(args.xml))
    Path(args.out).write_text(json.dumps(tables, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {args.out}: {len(tables)} gold tables")
    for t in tables:
        print(f"  {t['label'] or '(no label)':12} rows={t['n_rows']:2} cells={t['n_cells']:3}  {t['caption'][:60]}")


if __name__ == "__main__":
    main()
