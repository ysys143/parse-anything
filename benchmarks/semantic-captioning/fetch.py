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

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
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
        "wikimedia_korean_manuscript.jpg":
            "https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/Korean-manuscript.JPG/1280px-Korean-manuscript.JPG",
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
        "swit_요구사항상세화_실무가이드라인.pdf":
            "https://www.cisp.or.kr/wp-content/uploads/2021/03/2.%EA%B3%B5%EA%B3%B5SW%EC%82%AC%EC%97%85-%EC%A0%9C%EC%95%88%EC%9A%94%EC%B2%AD%EC%84%9C-%EC%9E%91%EC%84%B1%EC%9D%84-%EC%9C%84%ED%95%9C-%EC%9A%94%EA%B5%AC%EC%82%AC%ED%95%AD-%EA%B0%80%EC%9D%B4%EB%93%9C-20210219.pdf",
        "swit_공공정보화_제안요청서_작성가이드.pdf":
            "https://www.swit.or.kr/download.do?fileName=%2F201406%2F%EA%B3%B5%EA%B3%B5%EC%A0%95%EB%B3%B4%ED%99%94+%EC%82%AC%EC%97%85%EC%9C%A0%ED%98%95%EB%B3%84+%EC%A0%9C%EC%95%88%EC%9A%94%EC%B2%AD%EC%84%9C+%EC%9E%91%EC%84%B1+%EA%B0%80%EC%9D%B4%EB%93%9C.pdf",
        "knowhow_참여정부_정책보고서.pdf": "https://file3.knowhow.or.kr/download/27939/2.pdf",
    },
}

# Google Patents: re-extract the patentimages PDF link from the patent page (hash URLs drift).
PATENTS = {"drawing": ["US6285999B1", "US7663607B2"]}

# CORD: HF datasets-server serves images via *expiring signed* URLs -> re-query at fetch time.
CORD = {"form": {"dataset": "naver-clova-ix/cord-v2", "config": "default", "split": "train", "n": 3}}


def _get(url: str, timeout: int = 60) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


def _kind(data: bytes) -> str:
    prefix = data[:256].lstrip().lower()
    if data.startswith(b"%PDF"):
        return "pdf"
    if data.startswith((b"\xff\xd8\xff", b"\x89PNG", b"II*\x00", b"MM\x00*")):
        return "img"
    if prefix.startswith((b"<!doctype html", b"<html")) or b"<html" in prefix[:128]:
        return "html"
    return "?"


def _expected_kind(name: str) -> str:
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}:
        return "img"
    return "?"


def _validate_download(data: bytes, name: str) -> str:
    kind = _kind(data)
    expected = _expected_kind(name)
    if kind == "html":
        raise ValueError(f"unexpected html response for {name}")
    if kind == "?":
        raise ValueError(f"unknown response type for {name}")
    if expected != "?" and kind != expected:
        raise ValueError(f"unexpected {kind} response for {name}; expected {expected}")
    return kind


def _summary(data: bytes, kind: str) -> str:
    return f"{len(data):>9,}B {kind}"


def _save(data: bytes, path: Path) -> str:
    kind = _validate_download(data, path.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return _summary(data, kind)


def _checked(data: bytes, name: str) -> str:
    return _summary(data, _validate_download(data, name))


def fetch_direct(domain: str, out: Path, *, check: bool = False) -> int:
    failures = 0
    for name, url in DIRECT.get(domain, {}).items():
        try:
            data = _get(url)
            result = _checked(data, name) if check else _save(data, out/domain/name)
            print(f"  {name}: {result}")
        except Exception as e:
            failures += 1
            print(f"  {name}: FAIL {e}")
    return failures


def fetch_patents(out: Path, *, check: bool = False) -> int:
    failures = 0
    for domain, pats in PATENTS.items():
        for pat in pats:
            name = f"patent_{pat}.pdf"
            try:
                html = _get(f"https://patents.google.com/patent/{pat}/en").decode("utf-8", "ignore")
                m = re.search(r'https://patentimages\.storage\.googleapis\.com/[^"]+\.pdf', html)
                if not m:
                    failures += 1
                    print(f"  {name}: FAIL no pdf link")
                    continue
                data = _get(m.group(0))
                result = _checked(data, name) if check else _save(data, out/domain/name)
                print(f"  {name}: {result}")
            except Exception as e:
                failures += 1
                print(f"  {name}: FAIL {e}")
    return failures


def fetch_cord(out: Path, *, check: bool = False) -> int:
    failures = 0
    for domain, spec in CORD.items():
        try:
            q = urllib.parse.urlencode({"dataset": spec["dataset"], "config": spec["config"], "split": spec["split"]})
            data = json.loads(_get(f"https://datasets-server.huggingface.co/first-rows?{q}"))
            srcs = [r["row"]["image"]["src"] for r in data.get("rows", [])
                    if isinstance(r["row"].get("image"), dict) and r["row"]["image"].get("src")]
            for i, u in enumerate(srcs[: spec["n"]], 1):
                name = f"cord_receipt_{i}.jpg"
                img = _get(u)
                result = _checked(img, name) if check else _save(img, out/domain/name)
                print(f"  {name}: {result}")
        except Exception as e:
            failures += 1
            print(f"  cord_receipt_*.jpg: FAIL {e}")
    return failures


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--domains", default="", help="comma-separated subset; default all")
    ap.add_argument("--list", action="store_true", help="print plan and exit")
    ap.add_argument("--check", action="store_true", help="validate source URLs without writing files")
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
    failures = 0
    for d in want:
        print(f"[{d}]")
        if d in DIRECT:
            failures += fetch_direct(d, out, check=a.check)
        if d in PATENTS:
            failures += fetch_patents(out, check=a.check)
        if d in CORD:
            failures += fetch_cord(out, check=a.check)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
