#!/usr/bin/env python3
"""Reproduce the semantic-captioning golden seed corpus from public sources.

Usage:
    python benchmarks/semantic-captioning/fetch.py --out .local/semantic-captioning/corpus/raw
    python benchmarks/semantic-captioning/fetch.py --domains table,drawing_dim   # subset
    python benchmarks/semantic-captioning/fetch.py --list                        # show plan only

Originals are NOT committed (repo policy: artifacts never committed). See SOURCES.md for
licenses and known gaps. Some Korean public (policy) links may drift; verify from SOURCES.md.
"""
from __future__ import annotations
import argparse, json, sys, urllib.parse, urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (semantic-captioning seed fetcher)"}
DEFAULT_OUT = ".local/semantic-captioning/corpus/raw"

# Direct-URL seeds: domain -> {filename: url}
DIRECT = {
    "table": {
        "arxiv_1706.03762_attention.pdf": "https://arxiv.org/pdf/1706.03762",
        "arxiv_2005.14165_gpt3.pdf": "https://arxiv.org/pdf/2005.14165",
    },
    "drawing_dim": {
        "wikimedia_schneckenwelle_worm_shaft.png":
            "https://upload.wikimedia.org/wikipedia/commons/thumb/9/96/Schneckenwelle.png/1280px-Schneckenwelle.png",
        "wikimedia_boundy_diameter_dimensioning.png":
            "https://upload.wikimedia.org/wikipedia/commons/thumb/3/39/Boundy_diameter.svg/1280px-Boundy_diameter.svg.png",
    },
    "handwriting": {
        "census_1900_population_schedule.jpg":
            "https://upload.wikimedia.org/wikipedia/commons/thumb/5/57/1900_census_Julian.jpg/1280px-1900_census_Julian.jpg",
        "census_1950_us.jpg":
            "https://upload.wikimedia.org/wikipedia/commons/thumb/9/92/Eugene_Freudenberg_%281900-1956%29_in_the_1950_US_census.jpg/1280px-Eugene_Freudenberg_%281900-1956%29_in_the_1950_US_census.jpg",
    },
    "statistics": {
        "kostat_고령자통계_2025.pdf":
            "https://www.kostat.go.kr/boardDownload.es?bid=10820&list_no=438832&seq=1",
        "kostat_사회조사_2024.pdf":
            "https://www.kostat.go.kr/boardDownload.es?bid=219&list_no=433638&seq=8",
    },
    "insurance": {
        "samsungfire_개인용자동차보험_약관_2023.pdf":
            "https://www.samsungfire.com/publication/pdf/20051_0_20231011_file1.pdf",
        "hyundai_실손의료비_약관_2026.pdf":
            "https://mdirect.hi.co.kr/dhNAS/terms/CM12M1_20260101.pdf",
        "insure_or_kr_생명보험표준약관_및해설.pdf":
            "https://exam.insure.or.kr/upload/attach/under/notice/20160202_1454394178948.pdf",
        "kiri_표준약관개정안_주요내용.pdf":
            "https://www.kiri.or.kr/report/downloadFile.do?docId=5906",
    },
    # policy: some links drift (게시물 seq/파일명 변동). Verify from SOURCES.md if these 404/HTML.
    "policy": {
        "knowhow_참여정부_정책보고서.pdf": "https://file3.knowhow.or.kr/download/27939/2.pdf",
    },
}

# Google Patents: re-extract the patentimages PDF link from the patent page (hash URLs drift).
PATENTS = {"drawing": ["US6285999B1", "US7663607B2"]}

# CORD: HF datasets-server serves images via *expiring signed* URLs -> re-query at fetch time.
CORD = {"form": {"dataset": "naver-clova-ix/cord-v2", "config": "default", "split": "train", "n": 3}}


def _get(url: str, timeout: int = 60) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


def _save(data: bytes, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    head = data[:5]
    kind = "pdf" if head.startswith(b"%PDF") else "img" if head[:3] in (b"\xff\xd8\xff", b"\x89PN") else "?"
    return f"{len(data):>9,}B {kind}"


def fetch_direct(domain: str, out: Path) -> None:
    for name, url in DIRECT.get(domain, {}).items():
        try:
            print(f"  {name}: {_save(_get(url), out/domain/name)}")
        except Exception as e:
            print(f"  {name}: FAIL {e}")


def fetch_patents(out: Path) -> None:
    for domain, pats in PATENTS.items():
        for pat in pats:
            try:
                html = _get(f"https://patents.google.com/patent/{pat}/en").decode("utf-8", "ignore")
                import re
                m = re.search(r'https://patentimages\.storage\.googleapis\.com/[^"]+\.pdf', html)
                if not m:
                    print(f"  patent_{pat}.pdf: FAIL no pdf link"); continue
                print(f"  patent_{pat}.pdf: {_save(_get(m.group(0)), out/domain/f'patent_{pat}.pdf')}")
            except Exception as e:
                print(f"  patent_{pat}.pdf: FAIL {e}")


def fetch_cord(out: Path) -> None:
    for domain, spec in CORD.items():
        try:
            q = urllib.parse.urlencode({"dataset": spec["dataset"], "config": spec["config"], "split": spec["split"]})
            data = json.loads(_get(f"https://datasets-server.huggingface.co/first-rows?{q}"))
            srcs = [r["row"]["image"]["src"] for r in data.get("rows", [])
                    if isinstance(r["row"].get("image"), dict) and r["row"]["image"].get("src")]
            for i, u in enumerate(srcs[: spec["n"]], 1):
                print(f"  cord_receipt_{i}.jpg: {_save(_get(u), out/domain/f'cord_receipt_{i}.jpg')}")
        except Exception as e:
            print(f"  cord_receipt_*.jpg: FAIL {e}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--domains", default="", help="comma-separated subset; default all")
    ap.add_argument("--list", action="store_true", help="print plan and exit")
    a = ap.parse_args()

    all_domains = sorted(set(DIRECT) | set(PATENTS) | set(CORD))
    want = [d.strip() for d in a.domains.split(",") if d.strip()] or all_domains
    if a.list:
        for d in all_domains:
            n = len(DIRECT.get(d, {})) + sum(len(v) for k, v in PATENTS.items() if k == d) + (CORD.get(d, {}).get("n", 0))
            print(f"{d:12} {n} file(s){'  [selected]' if d in want else ''}")
        return 0

    out = Path(a.out)
    print(f"-> {out}")
    for d in want:
        print(f"[{d}]")
        if d in DIRECT: fetch_direct(d, out)
        if d in PATENTS: fetch_patents(out)   # iterates its own domains; harmless if repeated
        if d in CORD: fetch_cord(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
