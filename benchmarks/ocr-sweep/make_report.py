#!/usr/bin/env python3
"""Build a side-by-side comparison report from a run_bench.py results tree.

Reads, per model, for both docs (born / scan):
  metrics_<doc>.jsonl  -> per-page latency, char count, done/failed (from the shim)
  raw_<doc>/<model>/*.md -> the model's RAW transcription per page (assembly-independent signal)
  out_<doc>/<sid>/<docid>/ledger.jsonl + document.semantic.json -> parse-anything's product view
summary.jsonl -> per model/doc run status.

Emits a Markdown report: a status/timing table, a raw-output-size table, parse-anything
structure stats, and a per-page raw side-by-side excerpt so quality is eyeballable.

stdlib only. Usage: python make_report.py --results results/ --out results/report.md
"""
from __future__ import annotations

import argparse
import glob
import json
import os


def read_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


def model_dirs(results: str) -> list[str]:
    return sorted(d for d in glob.glob(os.path.join(results, "*")) if os.path.isdir(d))


def semantic_stats(out_dir: str) -> dict:
    hits = glob.glob(os.path.join(out_dir, "*", "*", "document.semantic.json"))
    if not hits:
        return {}
    try:
        s = json.load(open(hits[0], encoding="utf-8"))
    except Exception:
        return {}
    tree = s.get("section_tree") or s.get("sections") or []
    n_sec = 0
    stack = list(tree if isinstance(tree, list) else [tree])
    while stack:
        n = stack.pop()
        if isinstance(n, dict):
            n_sec += 1
            stack.extend(n.get("children", []) or [])
    return {"nodes": len(s.get("nodes", [])), "sections": n_sec, "zones": len(s.get("zones", []))}


def ledger_stats(out_dir: str) -> dict:
    hits = glob.glob(os.path.join(out_dir, "*", "*", "ledger.jsonl"))
    if not hits:
        return {}
    rows = read_jsonl(hits[0])
    flags = sum(len(r.get("flags", [])) for r in rows)
    chars = sum(r.get("markdown_chars", 0) for r in rows)
    return {"pages": len(rows), "md_chars": chars, "flags": flags}


def metric_summary(rows: list[dict]) -> dict:
    done = [r for r in rows if r.get("state") == "done"]
    failed = [r for r in rows if r.get("state") == "failed"]
    lat = [r["latency_ms"] for r in done if "latency_ms" in r]
    chars = [r.get("chars", 0) for r in done]
    return {
        "pages": len(rows), "done": len(done), "failed": len(failed),
        "avg_latency_s": round(sum(lat) / len(lat) / 1000, 1) if lat else 0.0,
        "total_latency_s": round(sum(lat) / 1000, 1) if lat else 0.0,
        "avg_chars": int(sum(chars) / len(chars)) if chars else 0,
    }


def table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def raw_pages(mdir: str, doc: str, model_sane: str) -> list[str]:
    d = os.path.join(mdir, f"raw_{doc}", model_sane)
    return sorted(glob.glob(os.path.join(d, "*.md")))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--excerpt-page", type=int, default=1, help="1-based page for the side-by-side excerpt")
    ap.add_argument("--excerpt-chars", type=int, default=800)
    args = ap.parse_args()

    dirs = model_dirs(args.results)
    docs = ["born", "scan"]

    lines = ["# parse-anything OCR model sweep - comparison report", ""]
    lines.append(f"Models: {len(dirs)} | docs: born-digital (grounded) + scanned (raw-OCR stress)")
    lines.append("")

    # Status + timing per model/doc
    lines.append("## Status & timing")
    rows = []
    for mdir in dirs:
        model = os.path.basename(mdir)
        for doc in docs:
            metrics = read_jsonl(os.path.join(mdir, f"metrics_{doc}.jsonl"))
            if not metrics and not os.path.exists(os.path.join(mdir, f"out_{doc}")):
                continue
            ms = metric_summary(metrics)
            status = "ok" if ms["done"] and not ms["failed"] else ("partial" if ms["done"] else "FAIL")
            rows.append([model, doc, status, ms["pages"], ms["done"], ms["failed"],
                         ms["avg_latency_s"], ms["total_latency_s"], ms["avg_chars"]])
    lines.append(table(["model", "doc", "status", "pages", "done", "fail",
                        "avg_lat_s", "total_s", "avg_chars"], rows))
    lines.append("")

    # parse-anything product-view structure (should be ~invariant across models on born-digital)
    lines.append("## parse-anything artifact stats (product view)")
    rows = []
    for mdir in dirs:
        model = os.path.basename(mdir)
        for doc in docs:
            out_dir = os.path.join(mdir, f"out_{doc}")
            if not os.path.isdir(out_dir):
                continue
            ss, ls = semantic_stats(out_dir), ledger_stats(out_dir)
            if not ss and not ls:
                continue
            rows.append([model, doc, ls.get("pages", "-"), ls.get("md_chars", "-"),
                         ls.get("flags", "-"), ss.get("nodes", "-"), ss.get("sections", "-"),
                         ss.get("zones", "-")])
    lines.append(table(["model", "doc", "pages", "md_chars", "oracle_flags",
                        "nodes", "sections", "zones"], rows))
    lines.append("")

    # Raw side-by-side excerpt on one page (the honest OCR-quality signal)
    pg = args.excerpt_page
    lines.append(f"## Raw transcription excerpt - page {pg} (scanned doc)")
    lines.append("The scanned doc has no text layer, so this is each model's unaided OCR.")
    lines.append("")
    for mdir in dirs:
        model = os.path.basename(mdir)
        pages = raw_pages(mdir, "scan", model)
        lines.append(f"### {model}")
        if len(pages) >= pg:
            txt = open(pages[pg - 1], encoding="utf-8").read()[: args.excerpt_chars]
            lines.append("```")
            lines.append(txt.rstrip())
            lines.append("```")
        else:
            lines.append("_(no output for this page - runner failed or model errored)_")
        lines.append("")

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"[report] wrote {args.out} ({len(dirs)} models)")


if __name__ == "__main__":
    main()
