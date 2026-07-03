#!/usr/bin/env python3
"""Extract a clean, independent ground-truth text from a PLOS JATS XML manuscript.

The publisher's JATS XML is human-edited: correct reading order, no text-layer spacing collapse,
real table-cell text, proper captions. Using it as GT breaks the CIRCULARITY of scoring a
text-layer extractor (ODL) against another text-layer extraction (pypdfium2) -- and it does not
penalize a VLM for CORRECTING text-layer errors, because the GT already has the correct text.

Extracts, in document order: article-title + abstract + body + back (incl. supplementary-material
captions, where the statistics blocks live). Excludes journal/publisher boilerplate and the
reference LIST (citation formatting is noise both sides would differ on), but keeps everything else.

Usage: python gt_from_jats.py --xml corpus/gt/plos_3002373.xml --out corpus/gt/plos_3002373.gt.txt
"""
from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
from pathlib import Path


def _text(el: ET.Element) -> str:
    return re.sub(r"\s+", " ", " ".join(el.itertext())).strip()


def extract(xml_path: Path) -> str:
    root = ET.parse(xml_path).getroot()
    parts: list[str] = []

    title = root.find(".//front//article-title")
    if title is not None:
        parts.append(_text(title))
    abstract = root.find(".//front//abstract")
    if abstract is not None:
        parts.append(_text(abstract))

    body = root.find(".//body")
    if body is not None:
        parts.append(_text(body))

    # back matter EXCEPT the formatted reference list (ref-list): keep SI captions, acks, footnotes.
    back = root.find(".//back")
    if back is not None:
        for child in back:
            if child.tag == "ref-list":
                continue
            parts.append(_text(child))

    return "\n\n".join(p for p in parts if p)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    gt = extract(Path(args.xml))
    Path(args.out).write_text(gt, encoding="utf-8")
    print(f"wrote {args.out}: {len(gt)} chars")


if __name__ == "__main__":
    main()
