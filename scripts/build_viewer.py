#!/usr/bin/env python3
"""Build a self-contained, dependency-free HTML viewer for an odl-vl conversion output dir.

Reads one conversion output directory (``document.semantic.json`` + ``document.chunks.jsonl``
required, ``document.provenance.json`` optional) and writes a single ``viewer.html`` INTO the
same directory with all data inlined as JSON in a ``<script>`` tag. Double-clickable; no server
needed (assets load via relative paths since the html sits next to ``assets/``).

Stdlib only -- the repo's parsers are intentionally dependency-free and this matches that.

    uv run --no-sync python scripts/build_viewer.py --dir <output_dir> [--out viewer.html]
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

VIEWER_VERSION = "1.0"


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _load_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _inject_json(obj) -> str:
    """Serialize ``obj`` for safe embedding inside a ``<script>`` tag.

    JSON is a subset of JS object-literal syntax, so ``const DATA = <blob>`` parses directly.
    We only neutralize the sequences that would break out of the script element or the JS
    string state: ``</`` (script-close) and the two line-separator code points illegal in JS.
    """
    blob = json.dumps(obj, ensure_ascii=False)
    blob = blob.replace("</", "<\\/")
    blob = blob.replace(" ", "\\u2028").replace(" ", "\\u2029")
    return blob


def build(out_dir: Path, out_name: str) -> Path:
    sem_path = out_dir / "document.semantic.json"
    chunks_path = out_dir / "document.chunks.jsonl"
    prov_path = out_dir / "document.provenance.json"

    if not sem_path.exists():
        raise SystemExit(f"[ERROR] required file not found: {sem_path}")
    if not chunks_path.exists():
        raise SystemExit(f"[ERROR] required file not found: {chunks_path}")

    semantic = _load_json(sem_path)
    chunks = _load_jsonl(chunks_path)

    prov_map: dict = {}
    prov_present = False
    if prov_path.exists():
        try:
            prov_doc = _load_json(prov_path)
            prov_map = prov_doc.get("prov", {}) or {}
            prov_present = True
        except (json.JSONDecodeError, OSError) as exc:  # pragma: no cover - defensive
            print(f"[WARN] could not read provenance ({exc}); continuing without it", file=sys.stderr)

    payload = {
        "semantic": semantic,
        "chunks": chunks,
        "prov": prov_map,
        "meta": {
            "generated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "generator_version": VIEWER_VERSION,
            "dir_name": out_dir.name,
            "prov_present": prov_present,
        },
    }

    html = HTML_TEMPLATE
    html = html.replace("/*__DATA__*/{}", _inject_json(payload))
    html = html.replace("__GENERATED_AT__", payload["meta"]["generated_at"])
    html = html.replace("__VIEWER_VERSION__", VIEWER_VERSION)

    out_path = out_dir / out_name
    out_path.write_text(html, encoding="utf-8")

    kb = out_path.stat().st_size / 1024
    print(
        f"[OK] wrote {out_path}  ({kb:.0f} KB)  "
        f"nodes={len(semantic.get('nodes', []))} sections={len(semantic.get('sections', []))} "
        f"chunks={len(chunks)} prov={'yes' if prov_present else 'no'}"
    )
    return out_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build a self-contained HTML viewer for an odl-vl output dir.")
    ap.add_argument("--dir", required=True, help="conversion output directory (contains document.semantic.json)")
    ap.add_argument("--out", default="viewer.html", help="output filename written INTO --dir (default: viewer.html)")
    args = ap.parse_args(argv)

    out_dir = Path(args.dir).expanduser().resolve()
    if not out_dir.is_dir():
        raise SystemExit(f"[ERROR] not a directory: {out_dir}")

    build(out_dir, args.out)
    return 0


# ============================================================================================
# The whole viewer (HTML + CSS + vanilla JS) lives here. The data blob replaces the
# ``/*__DATA__*/{}`` token; no framework, no build step. Raw string so JS escape sequences
# (e.g. "\n") survive verbatim into the output.
# ============================================================================================
HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>odl-vl viewer</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css"
      integrity="sha384-n8MVd4RsNIU0tAv4ct0nTaAbDJwPJzDEaqSD1odI+WdtXRGWt2kTvGFasHpSy3SV" crossorigin="anonymous">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"
        integrity="sha384-XjKyOOlGwcjNTAIQHIpgOno0Hl1YQqzUOEleOLALmuqehneUG+vnGctmUb0ZY0l8" crossorigin="anonymous"></script>
<style>
:root{
  --bg:#f4f5f7; --panel:#ffffff; --ink:#181c22; --ink-soft:#5b6472; --ink-faint:#8a93a3;
  --line:#e5e8ec; --line-soft:#eef0f3; --accent:#4f46e5; --accent-soft:#eef0ff;
  --side:#14181f; --side-2:#1b212b; --side-ink:#c9d2df; --side-faint:#7c8697; --side-line:#2a313d;
  --radius:12px; --radius-sm:8px; --shadow:0 1px 2px rgba(20,24,31,.04),0 8px 24px rgba(20,24,31,.05);
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --t-title:#4f46e5; --t-heading:#7c3aed; --t-paragraph:#64748b; --t-list_item:#0891b2;
  --t-caption:#b45309; --t-reference:#0d9488; --t-figure:#ea580c; --t-table:#e11d48; --t-equation:#9333ea;
  --z-cover:#6366f1; --z-metadata:#0ea5e9; --z-toc:#14b8a6; --z-body:#94a3b8;
  --z-references:#f59e0b; --z-appendix:#ec4899; --z-furniture:#a3a3a3;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{font-family:var(--sans);color:var(--ink);background:var(--bg);font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none}
code,.mono{font-family:var(--mono)}
::selection{background:var(--accent-soft)}

.app{display:grid;grid-template-columns:280px 1fr;min-height:100vh}

/* ---------- sidebar ---------- */
.side{position:sticky;top:0;align-self:start;height:100vh;overflow-y:auto;background:var(--side);color:var(--side-ink);
  border-right:1px solid var(--side-line);display:flex;flex-direction:column}
.side::-webkit-scrollbar{width:8px}
.side::-webkit-scrollbar-thumb{background:#333d4c;border-radius:8px}
.brand{padding:18px 18px 14px;border-bottom:1px solid var(--side-line)}
.brand .logo{font-family:var(--mono);font-weight:700;font-size:14px;letter-spacing:.02em;color:#fff}
.brand .logo .dot{color:var(--accent);display:inline-block}
.brand .sub{font-size:11px;color:var(--side-faint);margin-top:3px;font-family:var(--mono)}
.brand .docname{font-size:12.5px;color:var(--side-ink);margin-top:10px;line-height:1.4;font-weight:500}

.nav{padding:10px 10px 4px}
.nav button{display:flex;align-items:center;gap:10px;width:100%;text-align:left;background:transparent;border:0;color:var(--side-ink);
  font:inherit;font-size:13.5px;padding:9px 12px;border-radius:var(--radius-sm);cursor:pointer;transition:background .12s,color .12s}
.nav button .idx{font-family:var(--mono);font-size:11px;color:var(--side-faint);width:14px}
.nav button:hover{background:var(--side-2);color:#fff}
.nav button.active{background:var(--accent);color:#fff}
.nav button.active .idx{color:rgba(255,255,255,.7)}

.side-sec{padding:14px 18px;border-top:1px solid var(--side-line)}
.side-sec h4{margin:0 0 10px;font-size:10.5px;text-transform:uppercase;letter-spacing:.09em;color:var(--side-faint);font-weight:600}
.stat-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.stat{background:var(--side-2);border-radius:var(--radius-sm);padding:8px 10px}
.stat .v{font-family:var(--mono);font-size:17px;font-weight:600;color:#fff;line-height:1.1}
.stat .k{font-size:10.5px;color:var(--side-faint);margin-top:2px}

.filter-block{margin-bottom:14px}
.chk{display:flex;align-items:center;gap:8px;padding:4px 2px;cursor:pointer;font-size:12.5px;color:var(--side-ink);user-select:none;border-radius:6px}
.chk:hover{background:var(--side-2)}
.chk input{display:none}
.chk .sw{width:11px;height:11px;border-radius:3px;flex:0 0 auto;box-shadow:inset 0 0 0 1px rgba(255,255,255,.15)}
.chk .lab{flex:1;text-transform:capitalize}
.chk .cnt{font-family:var(--mono);font-size:11px;color:var(--side-faint)}
.chk.off{opacity:.38}
.chk.off .sw{background:transparent!important;box-shadow:inset 0 0 0 1.5px var(--side-faint)}
.filter-tools{display:flex;gap:6px;margin-top:8px}
.filter-tools button{flex:1;background:var(--side-2);border:0;color:var(--side-faint);font:inherit;font-size:11px;padding:6px;border-radius:6px;cursor:pointer}
.filter-tools button:hover{color:#fff}

/* ---------- main ---------- */
.main{min-width:0;display:flex;flex-direction:column}
.topbar{position:sticky;top:0;z-index:20;background:rgba(244,245,247,.86);backdrop-filter:saturate(1.4) blur(8px);
  border-bottom:1px solid var(--line);padding:14px 26px;display:flex;align-items:center;gap:16px}
.topbar .title{font-size:15px;font-weight:600;letter-spacing:-.01em;line-height:1.3;min-width:0;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}
.chips{display:flex;gap:6px;flex:0 0 auto;flex-wrap:wrap;justify-content:flex-end}
.chip{font-family:var(--mono);font-size:11px;color:var(--ink-soft);background:var(--panel);border:1px solid var(--line);
  padding:3px 9px;border-radius:999px}
.chip b{color:var(--ink);font-weight:600}

.search-wrap{position:relative;flex:0 0 240px}
.search-wrap input{width:100%;font:inherit;font-size:13px;padding:7px 12px 7px 30px;border:1px solid var(--line);
  border-radius:999px;background:var(--panel);color:var(--ink);outline:none}
.search-wrap input:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.search-wrap .mag{position:absolute;left:11px;top:50%;transform:translateY(-50%);width:12px;height:12px;border:1.6px solid var(--ink-faint);
  border-radius:50%}
.search-wrap .mag::after{content:"";position:absolute;right:-4px;bottom:-4px;width:6px;height:1.6px;background:var(--ink-faint);transform:rotate(45deg)}

.view{padding:26px;max-width:1180px;width:100%;margin:0 auto;display:none}
.view.active{display:block}
.view h2.vh{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--ink-faint);margin:0 0 16px;font-weight:600}

/* ---------- overview ---------- */
.ov-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px;margin-bottom:22px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:18px 20px;box-shadow:var(--shadow)}
.card h3{margin:0 0 14px;font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--ink-faint);font-weight:600}
.kv{display:flex;justify-content:space-between;gap:14px;padding:6px 0;border-bottom:1px dashed var(--line-soft);font-size:13px}
.kv:last-child{border-bottom:0}
.kv .k{color:var(--ink-soft)}
.kv .v{font-family:var(--mono);font-size:12.5px;text-align:right;word-break:break-word;max-width:60%}
.hero{background:linear-gradient(135deg,#1b212b,#14181f);color:#fff;border:0;grid-column:1/-1}
.hero h3{color:rgba(255,255,255,.55)}
.hero .doctitle{font-size:23px;font-weight:600;letter-spacing:-.02em;line-height:1.28;margin:2px 0 16px}
.hero .metarow{display:flex;flex-wrap:wrap;gap:10px}
.hero .mchip{font-family:var(--mono);font-size:11.5px;background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.12);
  padding:5px 11px;border-radius:8px;color:#dfe5ee}
.hero .mchip b{color:#fff}

/* ---------- badges / rails shared ---------- */
.badge{display:inline-flex;align-items:center;gap:5px;font-family:var(--mono);font-size:10.5px;font-weight:600;
  padding:2px 7px;border-radius:5px;letter-spacing:.01em;text-transform:lowercase;color:#fff;white-space:nowrap}
.ztag{font-family:var(--mono);font-size:10.5px;color:var(--ink-soft);border:1px solid var(--line);border-radius:5px;padding:1px 6px}
.nid{font-family:var(--mono);font-size:11px;color:var(--ink-faint)}

/* ---------- reading view ---------- */
.reading{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:8px 8px;box-shadow:var(--shadow)}
.rnode{position:relative;padding:11px 16px 11px 18px;border-left:3px solid transparent;border-radius:8px;margin:2px 0;transition:background .12s}
.rnode:hover{background:var(--line-soft)}
.rnode.flash{animation:flash 1.4s ease}
@keyframes flash{0%,30%{background:var(--accent-soft)}100%{background:transparent}}
.rhead{display:flex;align-items:center;gap:8px;margin-bottom:5px;flex-wrap:wrap}
.rbody{}
.rbody .n-title{font-size:24px;font-weight:700;letter-spacing:-.02em;line-height:1.25}
.rbody .n-heading{font-weight:650;letter-spacing:-.01em}
.rbody .n-h1{font-size:20px}.rbody .n-h2{font-size:17px}.rbody .n-h3{font-size:15px}
.rbody .n-paragraph{color:#2a3038}
.rbody .n-list{display:flex;gap:10px;color:#2a3038}
.rbody .n-list .bullet{color:var(--t-list_item);font-weight:700;flex:0 0 auto}
.rbody .n-caption{font-style:italic;color:#4a525e;font-size:13.5px}
.rbody .n-caption .capfor{font-style:normal;font-family:var(--mono);font-size:11px;color:var(--t-caption);margin-right:6px}
.rbody .n-reference{display:flex;gap:10px;font-size:13px;color:#3a424d}
.rbody .n-reference .marker{font-family:var(--mono);color:var(--t-reference);font-weight:600;flex:0 0 auto;min-width:22px}
.figbox{margin-top:2px}
.figbox img{max-width:100%;max-height:520px;border:1px solid var(--line);border-radius:8px;background:#fafbfc;display:block}
.figbox .noimg{display:flex;align-items:center;justify-content:center;height:120px;border:1px dashed var(--line);border-radius:8px;
  color:var(--ink-faint);font-size:12.5px;background:repeating-linear-gradient(45deg,#fbfbfc,#fbfbfc 10px,#f5f6f8 10px,#f5f6f8 20px)}
.figbox .fcap{font-size:13px;font-style:italic;color:#4a525e;margin-top:8px}
.figbox .fdesc{font-size:12.5px;color:var(--ink-soft);margin-top:6px;background:var(--line-soft);border-radius:8px;padding:8px 11px}
.figbox .flabel{font-family:var(--mono);font-size:11px;color:var(--t-figure);font-weight:600;margin-bottom:6px}
.tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:8px;margin-top:2px}
table.dtab{border-collapse:collapse;width:100%;font-size:12.5px}
table.dtab td{border:1px solid var(--line);padding:6px 9px;vertical-align:top;color:#2a3038}
table.dtab tr:nth-child(even){background:var(--line-soft)}
.tcap{font-size:12.5px;font-style:italic;color:#4a525e;margin-top:7px}
.eqbox{overflow-x:auto;padding:6px 2px}
.eqbox .katex-display{margin:.3em 0}
.eqfallback{font-family:var(--mono);font-size:12.5px;background:var(--line-soft);border-radius:8px;padding:9px 12px;color:#2a3038;white-space:pre-wrap;word-break:break-word}
mark{background:#fff2a8;color:inherit;border-radius:2px;padding:0 1px}
.empty{color:var(--ink-faint);font-size:13px;padding:40px;text-align:center}

/* ---------- structure + chunks ---------- */
.split{display:grid;grid-template-columns:minmax(260px,340px) 1fr;gap:18px;align-items:start}
@media(max-width:900px){.split{grid-template-columns:1fr}.app{grid-template-columns:1fr}.side{position:static;height:auto}}
.tree{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:12px;box-shadow:var(--shadow);
  position:sticky;top:88px;max-height:calc(100vh - 110px);overflow:auto}
.trow{display:flex;align-items:flex-start;gap:6px;padding:5px 6px;border-radius:6px;cursor:pointer;font-size:13px}
.trow:hover{background:var(--line-soft)}
.trow .tw-toggle{width:14px;flex:0 0 auto;color:var(--ink-faint);font-size:10px;line-height:1.5}
.trow .th{flex:1;min-width:0}
.trow .tlvl{font-family:var(--mono);font-size:10px;color:var(--ink-faint)}
.trow .thead{color:var(--ink);overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.tchildren.collapsed{display:none}

.chunk-intro{background:var(--accent-soft);border:1px solid #dfe1ff;border-radius:var(--radius);padding:14px 18px;margin-bottom:16px;font-size:13px;color:#3a3f66}
.chunk-intro b{color:var(--accent)}
.chunk-intro .legend{display:flex;gap:16px;margin-top:10px;flex-wrap:wrap}
.chunk-intro .li{display:flex;align-items:center;gap:7px;font-size:12px}
.pill{font-family:var(--mono);font-size:10px;font-weight:700;padding:2px 8px;border-radius:999px;text-transform:uppercase;letter-spacing:.04em}
.pill.parent{background:#1b212b;color:#fff}
.pill.child{background:#fff;color:#1b212b;border:1.5px solid #1b212b}

.pchunk{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);margin-bottom:16px;overflow:hidden}
.pchunk>.phead{display:flex;align-items:center;gap:10px;padding:13px 16px;background:#1b212b;color:#fff;cursor:pointer;flex-wrap:wrap}
.pchunk>.phead .pcrumb{flex:1;min-width:120px;font-size:13px;font-weight:600;color:#fff;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pchunk>.phead .pid{font-family:var(--mono);font-size:11px;color:#9aa5b5}
.pchunk>.phead .pmeta{font-family:var(--mono);font-size:11px;color:#c9d2df;display:flex;gap:10px;flex-wrap:wrap}
.pchunk .children{padding:12px 14px;display:flex;flex-direction:column;gap:10px}
.pchunk .children.collapsed{display:none}
.cchunk{border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:8px;padding:11px 13px;background:#fcfcfd}
.cchunk .chead{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-bottom:2px}
.cchunk .cmeta{font-family:var(--mono);font-size:11px;color:var(--ink-soft);display:flex;gap:9px;flex-wrap:wrap;align-items:center}
.cchunk .cmeta .lk{color:var(--ink-faint)}
.cchunk .disp{font-size:13px;color:#2f3540;margin-top:6px;max-height:120px;overflow:hidden;position:relative;
  -webkit-mask-image:linear-gradient(#000 70%,transparent);mask-image:linear-gradient(#000 70%,transparent)}
.cchunk .disp.open{max-height:none;-webkit-mask-image:none;mask-image:none}
.cchunk .emb{margin-top:8px}
.cchunk .emb summary{cursor:pointer;font-size:11.5px;color:var(--accent);font-family:var(--mono);list-style:none}
.cchunk .emb summary::-webkit-details-marker{display:none}
.cchunk .emb .embtext{font-size:12px;color:#3a424d;background:var(--line-soft);border-radius:8px;padding:9px 11px;margin-top:7px;white-space:pre-wrap;word-break:break-word;max-height:260px;overflow:auto}
.cchunk .emb .crumbtag{display:inline-block;font-family:var(--mono);font-size:10px;color:var(--t-heading);background:#f3edff;border-radius:4px;padding:1px 6px;margin-bottom:6px}
.tag-atomic{background:#fef2f2;color:#b91c1c;border:1px solid #fecaca;border-radius:5px;font-family:var(--mono);font-size:10px;padding:1px 6px;font-weight:600}
.tag-cont{background:#fffbeb;color:#b45309;border:1px solid #fde68a;border-radius:5px;font-family:var(--mono);font-size:10px;padding:1px 6px}
.jump{cursor:pointer;color:var(--accent);font-family:var(--mono);font-size:11px}
.jump:hover{text-decoration:underline}

/* ---------- zones + stats ---------- */
.zwrap{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:18px 20px;box-shadow:var(--shadow);margin-bottom:20px}
.ruler{display:flex;font-family:var(--mono);font-size:9.5px;color:var(--ink-faint);margin:2px 0 6px;padding-left:96px}
.ruler span{flex:1;text-align:center;border-left:1px solid var(--line-soft)}
.ztrack{display:flex;align-items:center;margin:5px 0}
.ztrack .zname{flex:0 0 90px;font-family:var(--mono);font-size:11.5px;text-transform:capitalize;color:var(--ink-soft);display:flex;align-items:center;gap:6px}
.ztrack .zname .sw{width:9px;height:9px;border-radius:2px}
.ztrack .zcells{flex:1;display:flex;height:22px;border-radius:5px;overflow:hidden;background:var(--line-soft)}
.ztrack .zcell{flex:1;border-right:1px solid rgba(255,255,255,.6)}
.ztrack .zcell:last-child{border-right:0}
.zlegend{display:flex;gap:14px;flex-wrap:wrap;margin-top:14px;padding-top:12px;border-top:1px solid var(--line-soft)}
.zlegend .li{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--ink-soft)}
.zlegend .sw{width:11px;height:11px;border-radius:3px}

.hist .hrow{display:flex;align-items:center;gap:10px;margin:7px 0}
.hist .hname{flex:0 0 96px;font-family:var(--mono);font-size:12px;text-transform:capitalize;color:var(--ink-soft);text-align:right}
.hist .hbar-wrap{flex:1;background:var(--line-soft);border-radius:5px;overflow:hidden;height:20px}
.hist .hbar{height:100%;border-radius:5px 0 0 5px;min-width:2px;transition:width .5s cubic-bezier(.22,1,.36,1)}
.hist .hval{flex:0 0 46px;font-family:var(--mono);font-size:12px;color:var(--ink);text-align:right}

/* ---------- galleries ---------- */
.gal{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px}
.gcard{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;box-shadow:var(--shadow);display:flex;flex-direction:column}
.gcard .gthumb{background:#fafbfc;aspect-ratio:4/3;display:flex;align-items:center;justify-content:center;overflow:hidden;border-bottom:1px solid var(--line)}
.gcard .gthumb img{width:100%;height:100%;object-fit:contain}
.gcard .gthumb .noimg{color:var(--ink-faint);font-size:12px;text-align:center;padding:12px}
.gcard .gbody{padding:11px 13px}
.gcard .glabel{font-family:var(--mono);font-size:11px;color:var(--t-figure);font-weight:600}
.gcard .gcap{font-size:12px;color:var(--ink-soft);margin-top:5px;font-style:italic;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden}
.eqlist,.reflist{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);padding:6px 8px}
.eqrow{display:flex;gap:12px;align-items:flex-start;padding:12px 12px;border-bottom:1px solid var(--line-soft)}
.eqrow:last-child{border-bottom:0}
.eqrow .eqnum{font-family:var(--mono);font-size:11px;color:var(--ink-faint);flex:0 0 60px}
.eqrow .eqrender{flex:1;min-width:0;overflow-x:auto}
.eqrow .copy{flex:0 0 auto;background:var(--line-soft);border:1px solid var(--line);border-radius:6px;font:inherit;font-size:11px;
  font-family:var(--mono);padding:4px 9px;cursor:pointer;color:var(--ink-soft)}
.eqrow .copy:hover{background:var(--accent-soft);color:var(--accent)}
.eqrow .copy.done{background:#dcfce7;color:#15803d;border-color:#bbf7d0}
.refrow{display:flex;gap:12px;padding:9px 12px;border-bottom:1px solid var(--line-soft);font-size:13px;color:#3a424d}
.refrow:last-child{border-bottom:0}
.refrow .rmk{font-family:var(--mono);color:var(--t-reference);font-weight:600;flex:0 0 30px}

.subhead{display:flex;align-items:center;gap:10px;margin:26px 0 12px}
.subhead h3{font-size:14px;margin:0;font-weight:650}
.subhead .cnt{font-family:var(--mono);font-size:12px;color:var(--ink-faint)}
.subhead .rule{flex:1;height:1px;background:var(--line)}

/* ---------- tooltip ---------- */
#tt{position:fixed;z-index:100;pointer-events:none;background:#14181f;color:#e6ebf2;font-family:var(--mono);font-size:11px;
  padding:7px 10px;border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,.28);opacity:0;transition:opacity .1s;max-width:340px;line-height:1.5}
#tt .ttk{color:#8a93a3}
</style>
</head>
<body>
<div class="app">
  <aside class="side">
    <div class="brand">
      <div class="logo">odl<span class="dot">-</span>vl <span style="color:var(--side-faint);font-weight:400">viewer</span></div>
      <div class="sub" id="brandsub"></div>
      <div class="docname" id="branddoc"></div>
    </div>
    <nav class="nav" id="nav"></nav>
    <div class="side-sec">
      <h4>Document</h4>
      <div class="stat-grid" id="stats"></div>
    </div>
    <div class="side-sec" id="filtersec">
      <h4>Filter reading view</h4>
      <div class="filter-block" id="typefilter"></div>
      <h4 style="margin-top:6px">Zones</h4>
      <div class="filter-block" id="zonefilter"></div>
      <div class="filter-tools">
        <button id="fall">All</button><button id="fnone">None</button>
      </div>
    </div>
  </aside>

  <main class="main">
    <div class="topbar">
      <div class="title" id="doctitle"></div>
      <div class="search-wrap"><span class="mag"></span><input id="search" type="search" placeholder="Search node text..."></div>
      <div class="chips" id="chips"></div>
    </div>
    <section class="view" id="v-overview"></section>
    <section class="view" id="v-reading"><h2 class="vh">Reading order</h2><div class="reading" id="readingbox"></div></section>
    <section class="view" id="v-structure">
      <h2 class="vh">Structure &amp; chunks (small-to-big)</h2>
      <div class="split">
        <div class="tree" id="tree"></div>
        <div id="chunkarea"></div>
      </div>
    </section>
    <section class="view" id="v-zones"><h2 class="vh">Zones, stats &amp; distribution</h2><div id="zonesarea"></div></section>
    <section class="view" id="v-media"><h2 class="vh">Figures, equations &amp; references</h2><div id="mediaarea"></div></section>
  </main>
</div>

<div id="tt"></div>

<script>
const DATA = /*__DATA__*/{};
</script>
<script>
/* ==== data + indices ==================================================== */
const SEM  = (DATA && DATA.semantic) || {};
const CHUNKS = (DATA && DATA.chunks) || [];
const PROV = (DATA && DATA.prov) || {};
const META = (DATA && DATA.meta) || {};
const NODES = SEM.nodes || [];
const SECTIONS = SEM.sections || [];
const READING = SEM.reading_order || [];
const ZONES = SEM.zones || [];
const N_PAGES = SEM.n_pages || (function(){let m=0;ZONES.forEach(z=>(z.pages||[]).forEach(p=>{if(p>m)m=p}));return m||1;})();

const nodeById = {}; NODES.forEach(n=>{nodeById[n.id]=n;});
const sectionById = {}; SECTIONS.forEach(s=>{sectionById[s.id]=s;});
const chunkById = {}; CHUNKS.forEach(c=>{chunkById[c.id]=c;});
const capByTarget = {}; NODES.forEach(n=>{ if(n.type==='caption' && n.caption_of) capByTarget[n.caption_of]=n; });
// captions rendered attached to a figure/table (skip them in the flat reading stream)
const claimedCap = new Set();
NODES.forEach(n=>{ if((n.type==='figure'||n.type==='table') && n.caption_ref && nodeById[n.caption_ref]) claimedCap.add(n.caption_ref); });
NODES.forEach(n=>{ if(n.type==='caption' && n.caption_of && nodeById[n.caption_of]) claimedCap.add(n.id); });

const TYPE_ORDER=['title','heading','paragraph','list_item','caption','reference','figure','table','equation'];
const TYPE_COLOR={title:'#4f46e5',heading:'#7c3aed',paragraph:'#64748b',list_item:'#0891b2',caption:'#b45309',reference:'#0d9488',figure:'#ea580c',table:'#e11d48',equation:'#9333ea'};
const ZONE_ORDER=['cover','metadata','toc','body','references','appendix','furniture'];
const ZONE_COLOR={cover:'#6366f1',metadata:'#0ea5e9',toc:'#14b8a6',body:'#94a3b8',references:'#f59e0b',appendix:'#ec4899',furniture:'#a3a3a3'};

const typeCounts={}; TYPE_ORDER.forEach(t=>typeCounts[t]=0);
NODES.forEach(n=>{ typeCounts[n.type]=(typeCounts[n.type]||0)+1; });
const presentTypes=TYPE_ORDER.filter(t=>typeCounts[t]>0);
const presentZones=ZONE_ORDER.filter(z=>ZONES.some(x=>x.zone===z)).concat(
  ZONES.map(z=>z.zone).filter(z=>ZONE_ORDER.indexOf(z)<0));

/* ==== helpers =========================================================== */
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function tc(t){return TYPE_COLOR[t]||'#64748b';}
function zc(z){return ZONE_COLOR[z]||'#94a3b8';}
function pagesSpan(sr){ if(!sr||!sr.pages||!sr.pages.length) return null; const p=sr.pages; const a=p[0],b=p[p.length-1]; return a===b?('p.'+a):('p.'+a+'–'+b); }
function badge(t){return '<span class="badge" style="background:'+tc(t)+'">'+esc(t)+'</span>';}
function provOf(id){return PROV[id]||null;}
function provStr(id){const p=provOf(id);if(!p)return null;const a=[];if(p.page!=null)a.push('page '+p.page);if(p.order!=null)a.push('order '+p.order);if(p.font_size!=null)a.push('font '+p.font_size);if(p.bbox&&p.bbox.length===4)a.push('bbox ['+p.bbox.map(x=>Math.round(x*10)/10).join(', ')+']');return a.length?a.join('  ·  '):null;}

/* ==== sidebar =========================================================== */
function fmtId(id){return id?(id.length>12?id.slice(0,10)+'…':id):'—';}
document.getElementById('brandsub').textContent='v__VIEWER_VERSION__ · '+(META.dir_name||'');
document.getElementById('branddoc').textContent=(SEM.original_filename||SEM.document_id||'document');

const NAV=[['overview','Overview'],['reading','Reading'],['structure','Structure + Chunks'],['zones','Zones + Stats'],['media','Figures / Eq / Refs']];
const nav=document.getElementById('nav');
NAV.forEach((it,i)=>{const b=document.createElement('button');b.dataset.view=it[0];
  b.innerHTML='<span class="idx">'+(i+1)+'</span>'+esc(it[1]);b.onclick=()=>showView(it[0]);nav.appendChild(b);});

const parentChunks=CHUNKS.filter(c=>c.level==='parent');
const childChunks=CHUNKS.filter(c=>c.level==='child');
const STATS=[['pages',N_PAGES],['nodes',NODES.length],['sections',SECTIONS.length],['chunks',CHUNKS.length],
  ['parents',parentChunks.length],['children',childChunks.length]];
document.getElementById('stats').innerHTML=STATS.map(s=>'<div class="stat"><div class="v">'+s[1]+'</div><div class="k">'+s[0]+'</div></div>').join('');

/* filters */
const typeOn={}; presentTypes.forEach(t=>typeOn[t]=true);
const zoneOn={}; presentZones.forEach(z=>zoneOn[z]=true);
function renderFilters(){
  document.getElementById('typefilter').innerHTML=presentTypes.map(t=>
    '<label class="chk'+(typeOn[t]?'':' off')+'" data-type="'+t+'"><span class="sw" style="background:'+tc(t)+'"></span>'+
    '<span class="lab">'+esc(t)+'</span><span class="cnt">'+typeCounts[t]+'</span></label>').join('');
  document.getElementById('zonefilter').innerHTML=presentZones.map(z=>
    '<label class="chk'+(zoneOn[z]?'':' off')+'" data-zone="'+z+'"><span class="sw" style="background:'+zc(z)+'"></span>'+
    '<span class="lab">'+esc(z)+'</span></label>').join('');
  document.querySelectorAll('#typefilter .chk').forEach(el=>el.onclick=()=>{const t=el.dataset.type;typeOn[t]=!typeOn[t];el.classList.toggle('off',!typeOn[t]);applyFilter();});
  document.querySelectorAll('#zonefilter .chk').forEach(el=>el.onclick=()=>{const z=el.dataset.zone;zoneOn[z]=!zoneOn[z];el.classList.toggle('off',!zoneOn[z]);applyFilter();});
}
document.getElementById('fall').onclick=()=>{presentTypes.forEach(t=>typeOn[t]=true);presentZones.forEach(z=>zoneOn[z]=true);renderFilters();applyFilter();};
document.getElementById('fnone').onclick=()=>{presentTypes.forEach(t=>typeOn[t]=false);presentZones.forEach(z=>zoneOn[z]=false);renderFilters();applyFilter();};
renderFilters();

/* ==== topbar ============================================================ */
const title=(SEM.metadata&&SEM.metadata.title)||SEM.original_filename||SEM.document_id||'Untitled';
document.getElementById('doctitle').textContent=title;
const prof=SEM.profile||{};
document.getElementById('chips').innerHTML=[
  ['id',fmtId(SEM.document_id||'')],['pages',N_PAGES],['mode',SEM.mode||'—'],
  ['ontology',(prof.family||'?')+' '+(prof.version||'')]
].map(c=>'<span class="chip">'+c[0]+' <b>'+esc(c[1])+'</b></span>').join('');

/* ==== OVERVIEW ========================================================== */
function renderOverview(){
  const c=SEM.contract||{}; const src=SEM.source||{};
  const zoneSummary=ZONES.map(z=>{const p=z.pages||[];const a=p.length?p[0]:'?';const b=p.length?p[p.length-1]:'?';
    return '<span class="chip" style="border-color:'+zc(z.zone)+'"><span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:'+zc(z.zone)+';margin-right:5px"></span>'+esc(z.zone)+' <b>'+a+(a===b?'':('–'+b))+'</b></span>';}).join(' ');
  const idv=SEM.document_id||'';
  const el=document.getElementById('v-overview');
  el.innerHTML=
   '<div class="card hero"><h3>Document</h3><div class="doctitle">'+esc(title)+'</div>'+
     '<div class="metarow">'+
       '<span class="mchip">file <b>'+esc(SEM.original_filename||'—')+'</b></span>'+
       '<span class="mchip">pages <b>'+N_PAGES+'</b></span>'+
       '<span class="mchip">mode <b>'+esc(SEM.mode||'—')+'</b></span>'+
       '<span class="mchip">source <b>'+esc(src.source_id||'—')+'</b></span>'+
     '</div></div>'+
   '<div class="ov-grid">'+
     '<div class="card"><h3>Identity</h3>'+
       kv('document_id',idv)+kv('content_sha256',(SEM.content_sha256||'').slice(0,24)+'…')+
       kv('original_filename',SEM.original_filename||'—')+kv('ingested_from',src.ingested_from||'—')+'</div>'+
     '<div class="card"><h3>Contracts</h3>'+
       kv('semantic',(c.name||'?')+' v'+(c.version||'?'))+
       kv('provenance',META.prov_present?'present':'absent')+
       kv('generator','viewer v'+(META.generator_version||''))+
       kv('generated',(META.generated_at||'').replace('T',' '))+'</div>'+
     '<div class="card"><h3>Ontology profile</h3>'+
       kv('id',prof.id||'—')+kv('family',prof.family||'—')+kv('version',prof.version||'—')+
       kv('conformsTo',prof.conformsTo?shortUrl(prof.conformsTo):'—')+'</div>'+
     '<div class="card"><h3>Composition</h3>'+
       kv('nodes',String(NODES.length))+kv('sections',String(SECTIONS.length))+
       kv('reading_order',String(READING.length))+
       kv('chunks',parentChunks.length+' parent / '+childChunks.length+' child')+'</div>'+
   '</div>'+
   '<div class="card"><h3>Zones ('+ZONES.length+')</h3><div style="display:flex;gap:8px;flex-wrap:wrap">'+(zoneSummary||'<span class="empty">none</span>')+'</div></div>';
}
function kv(k,v){return '<div class="kv"><span class="k">'+esc(k)+'</span><span class="v" title="'+esc(v)+'">'+esc(v)+'</span></div>';}
function shortUrl(u){return u.replace(/^https?:\/\//,'').replace(/\/$/,'');}

/* ==== READING =========================================================== */
function capBlock(node){ // caption attached to a figure/table
  const cap=node.caption_ref?nodeById[node.caption_ref]:capByTarget[node.id];
  if(!cap||!cap.text) return '';
  return '<div class="fcap">'+esc(cap.text)+'</div>';
}
function nodeBodyHTML(n){
  const t=n.type;
  if(t==='title') return '<div class="n-title">'+esc(n.text)+'</div>';
  if(t==='heading'){const lv=Math.min(Math.max(parseInt(n.level)||1,1),3);return '<div class="n-heading n-h'+lv+'">'+esc(n.text)+'</div>';}
  if(t==='paragraph') return '<div class="n-paragraph">'+esc(n.text)+'</div>';
  if(t==='list_item') return '<div class="n-list"><span class="bullet">–</span><span>'+esc(n.text)+'</span></div>';
  if(t==='caption'){const tgt=n.caption_of&&nodeById[n.caption_of];const lab=tgt&&tgt.label?tgt.label:(n.caption_of||'');
    return '<div class="n-caption">'+(lab?'<span class="capfor">caption of '+esc(lab)+'</span>':'')+esc(n.text)+'</div>';}
  if(t==='reference') return '<div class="n-reference"><span class="marker">'+(n.marker!=null?esc(n.marker)+'.':'•')+'</span><span>'+esc(n.text)+'</span></div>';
  if(t==='equation') return '<div class="eqbox" data-latex="'+esc(n.latex||'')+'" data-display="'+(n.display?1:0)+'"></div>';
  if(t==='figure'){
    let h='<div class="figbox">';
    if(n.label) h+='<div class="flabel">'+esc(n.label)+'</div>';
    if(n.file) h+='<img loading="lazy" src="'+esc(n.file)+'" alt="'+esc(n.label||n.id)+'" onerror="this.outerHTML=\'<div class=&quot;noimg&quot;>image not found: '+esc(n.file)+'</div>\'">';
    else h+='<div class="noimg">no raster image · source: '+esc(n.source||'?')+'</div>';
    h+=capBlock(n);
    if(n.description) h+='<div class="fdesc">'+esc(n.description)+'</div>';
    return h+'</div>';
  }
  if(t==='table') return tableHTML(n);
  return '<div class="n-paragraph">'+esc(n.text||'')+'</div>';
}
function tableHTML(n){
  let h='<div class="figbox">';
  if(n.label) h+='<div class="flabel" style="color:var(--t-table)">'+esc(n.label)+((n.n_rows!=null)?(' · '+n.n_rows+'×'+n.n_cols):'')+'</div>';
  const cells=n.cells||[];
  if(cells.length){
    h+='<div class="tablewrap"><table class="dtab"><tbody>';
    cells.forEach(row=>{h+='<tr>';(row||[]).forEach(cell=>{const cs=cell&&cell.col_span?(' colspan="'+cell.col_span+'"'):'';const rs=cell&&cell.row_span?(' rowspan="'+cell.row_span+'"'):'';h+='<td'+cs+rs+'>'+esc(cell?cell.text:'')+'</td>';});h+='</tr>';});
    h+='</tbody></table></div>';
  } else { h+='<div class="noimg">no cell data</div>'; }
  const cap=n.caption_ref?nodeById[n.caption_ref]:capByTarget[n.id];
  if(cap&&cap.text) h+='<div class="tcap">'+esc(cap.text)+'</div>';
  return h+'</div>';
}
function renderReading(){
  const box=document.getElementById('readingbox');
  const seen=new Set(); let html=''; let count=0;
  READING.forEach(id=>{
    const n=nodeById[id];
    if(!n) return;                       // reading_order may list region/vector ids w/o a node
    if(n.type==='caption'&&claimedCap.has(n.id)) return; // rendered with its figure/table
    if(seen.has(id)) return; seen.add(id); count++;
    const hasProv=!!provOf(id);
    html+='<article class="rnode" id="n-'+esc(id)+'" data-type="'+esc(n.type)+'" data-zone="'+esc(n.zone||'')+'" '+
      (hasProv?'data-prov="1"':'')+' style="border-left-color:'+tc(n.type)+'">'+
      '<div class="rhead">'+badge(n.type)+'<span class="ztag">'+esc(n.zone||'?')+'</span>'+
      '<span class="nid">'+esc(id)+'</span>'+(hasProv?'<span class="nid" style="color:'+tc(n.type)+'">● prov</span>':'')+'</div>'+
      '<div class="rbody">'+nodeBodyHTML(n)+'</div></article>';
  });
  box.innerHTML=count?html:'<div class="empty">no nodes in reading order</div>';
  renderEquationsIn(box);
  applyFilter();
}

/* ==== equations (KaTeX with graceful fallback) ========================== */
function renderOneEq(el){
  const latex=el.getAttribute('data-latex')||'';
  const disp=el.getAttribute('data-display')==='1';
  if(!latex){el.innerHTML='<div class="eqfallback">(empty)</div>';return;}
  if(window.katex){
    try{ katex.render(latex,el,{displayMode:disp,throwOnError:false}); return; }
    catch(e){ /* fall through */ }
  }
  el.innerHTML='<div class="eqfallback">'+esc(latex)+'</div>';
}
function renderEquationsIn(root){ root.querySelectorAll('.eqbox[data-latex]').forEach(renderOneEq); }

/* ==== STRUCTURE: section tree =========================================== */
function buildTree(){
  const roots=SECTIONS.filter(s=>!s.parent||!sectionById[s.parent]);
  const tree=document.getElementById('tree');
  if(!SECTIONS.length){tree.innerHTML='<div class="empty">no sections</div>';return;}
  let html='';
  function walk(s,depth){
    const kids=(s.children||[]).map(id=>sectionById[id]).filter(Boolean);
    const hasKids=kids.length>0;
    html+='<div class="tnode">'+
      '<div class="trow" style="padding-left:'+(depth*14+6)+'px" data-ref="'+esc(s.heading_ref||'')+'"'+(hasKids?' data-toggle="1"':'')+'>'+
      '<span class="tw-toggle">'+(hasKids?'▾':'')+'</span>'+
      '<span class="th"><span class="thead">'+esc(s.heading||'(untitled)')+'</span> '+
      '<span class="tlvl">L'+(s.level!=null?s.level:'?')+' · '+esc(s.zone||'?')+(hasKids?(' · '+kids.length):'')+'</span></span></div>';
    if(hasKids){html+='<div class="tchildren">';kids.forEach(k=>walk(k,depth+1));html+='</div>';}
    html+='</div>';
  }
  roots.forEach(r=>walk(r,0));
  tree.innerHTML=html;
  tree.querySelectorAll('.trow').forEach(row=>{
    row.onclick=(e)=>{
      if(row.dataset.toggle && (e.target.classList.contains('tw-toggle'))){
        const kids=row.parentElement.querySelector('.tchildren');
        if(kids){kids.classList.toggle('collapsed');row.querySelector('.tw-toggle').textContent=kids.classList.contains('collapsed')?'▸':'▾';}
        return;
      }
      const ref=row.dataset.ref;
      if(ref) gotoNode(ref);
    };
  });
}

/* ==== STRUCTURE: chunks ================================================= */
function chunkMeta(c){
  const bits=[];
  bits.push('<span class="ztag">'+esc(c.zone||'?')+'</span>');
  const sp=pagesSpan(c.source_refs);
  if(sp) bits.push('<span>'+esc(sp)+'</span>');
  if(c.token_count!=null) bits.push('<span>'+c.token_count+' tok</span>');
  if(c.tokenizer) bits.push('<span class="lk">'+esc(c.tokenizer)+'</span>');
  return bits.join(' · ');
}
function renderChildChunk(c){
  const st=c.structural_type||'text';
  const col=({text:'#64748b',figure:'#ea580c',table:'#e11d48',equation:'#9333ea'})[st]||'#64748b';
  const tags=[];
  if(c.atomic) tags.push('<span class="tag-atomic">atomic</span>');
  if(c.is_continuation) tags.push('<span class="tag-cont">cont’d</span>');
  const nav=[];
  if(c.prev) tags.push('<span class="cmeta" style="color:var(--ink-faint)">‹ prev</span>');
  if(c.next) tags.push('<span class="cmeta" style="color:var(--ink-faint)">next ›</span>');
  const srcNodes=(c.source_refs&&c.source_refs.nodes)||[];
  const firstSrc=srcNodes.find(id=>nodeById[id]);
  const ntypes=(c.node_types||[]);
  const disp=c.display_text||c.text||'';
  const emb=c.embedding_text||'';
  const crumb=(c.heading_path&&c.heading_path.length)?c.heading_path.join('  ›  '):'';
  let h='<div class="cchunk" style="border-left-color:'+col+'">'+
    '<div class="chead"><span class="pill child">child</span>'+
      '<span class="badge" style="background:'+col+'">'+esc(st)+'</span>'+
      '<span class="nid">'+esc(c.id)+'</span>'+tags.join('')+'</div>'+
    '<div class="cmeta">'+chunkMeta(c)+
      (firstSrc?(' · <span class="jump" data-goto="'+esc(firstSrc)+'">→ '+esc(firstSrc)+'</span>'):'')+
      (ntypes.length?(' · <span class="lk">['+esc(ntypes.slice(0,6).join(', '))+(ntypes.length>6?'…':'')+']</span>'):'')+
    '</div>';
  if(disp) h+='<div class="disp" onclick="this.classList.toggle(\'open\')" title="click to expand">'+esc(disp)+'</div>';
  if(emb) h+='<details class="emb"><summary>embedding_text (with breadcrumb prefix)</summary>'+
    '<div class="embtext">'+(crumb?'<span class="crumbtag">'+esc(crumb)+'</span>\n':'')+esc(emb)+'</div></details>';
  return h+'</div>';
}
function renderChunks(){
  const area=document.getElementById('chunkarea');
  if(!CHUNKS.length){area.innerHTML='<div class="empty">no chunks</div>';return;}
  let html='<div class="chunk-intro">Small-to-big retrieval: index the <b>children</b> (focused leaves), '+
    'then return the <b>parent</b> (whole section / page group) for context. '+
    'Parent cards below hold their nested children.'+
    '<div class="legend"><span class="li"><span class="pill parent">parent</span> returned unit</span>'+
    '<span class="li"><span class="pill child">child</span> indexed leaf</span>'+
    '<span class="li"><span class="tag-atomic">atomic</span> kept whole (table/figure/equation)</span></div></div>';
  parentChunks.forEach(p=>{
    const kids=(p.children||[]).map(id=>chunkById[id]).filter(Boolean);
    const crumb=(p.heading_path&&p.heading_path.length)?p.heading_path.join('  ›  '):(p.structural_type==='page'?'(page group)':'(section)');
    html+='<div class="pchunk"><div class="phead" data-toggle="1">'+
      '<span class="pill parent">parent</span>'+
      '<span class="badge" style="background:#3b4453">'+esc(p.structural_type||'?')+'</span>'+
      '<span class="pcrumb">'+esc(crumb)+'</span>'+
      '<span class="pid">'+esc(p.id)+'</span>'+
      '<span class="pmeta">'+chunkMeta(p)+' · '+kids.length+' child'+(kids.length===1?'':'ren')+'</span></div>'+
      '<div class="children">'+(kids.length?kids.map(renderChildChunk).join(''):'<div class="empty" style="padding:14px">no children</div>')+'</div></div>';
  });
  area.innerHTML=html;
  area.querySelectorAll('.phead[data-toggle]').forEach(h=>h.onclick=()=>{
    const kids=h.parentElement.querySelector('.children');kids.classList.toggle('collapsed');});
  area.querySelectorAll('[data-goto]').forEach(el=>el.onclick=(e)=>{e.stopPropagation();gotoNode(el.dataset.goto);});
  renderEquationsIn(area);
}

/* ==== ZONES + STATS ===================================================== */
function renderZones(){
  const area=document.getElementById('zonesarea');
  // page ruler ticks
  let ruler='<div class="ruler">';
  for(let i=1;i<=N_PAGES;i++){ ruler+='<span>'+((N_PAGES<=30||i===1||i===N_PAGES||i%5===0)?i:'')+'</span>'; }
  ruler+='</div>';
  let tracks='';
  ZONES.forEach(z=>{
    const set=new Set(z.pages||[]);
    let cells='';
    for(let i=1;i<=N_PAGES;i++){ cells+='<div class="zcell" style="background:'+(set.has(i)?zc(z.zone):'transparent')+'" title="'+esc(z.zone)+' p.'+i+'"></div>'; }
    tracks+='<div class="ztrack"><div class="zname"><span class="sw" style="background:'+zc(z.zone)+'"></span>'+esc(z.zone)+'</div><div class="zcells">'+cells+'</div></div>';
  });
  const legend='<div class="zlegend">'+ZONES.map(z=>{const p=z.pages||[];const a=p.length?p[0]:'?';const b=p.length?p[p.length-1]:'?';
    return '<span class="li"><span class="sw" style="background:'+zc(z.zone)+'"></span>'+esc(z.zone)+' <span class="mono" style="color:var(--ink-faint)">'+a+(a===b?'':('–'+b))+' ('+p.length+'p)</span></span>';}).join('')+'</div>';
  const zoneBlock='<div class="zwrap"><div class="subhead" style="margin-top:0"><h3>Zone map</h3><span class="cnt">'+ZONES.length+' zones across '+N_PAGES+' pages</span><span class="rule"></span></div>'+
    ruler+(ZONES.length?tracks:'<div class="empty">no zones</div>')+(ZONES.length?legend:'')+'</div>';

  // histogram
  const maxc=Math.max(1,...presentTypes.map(t=>typeCounts[t]));
  const hist=presentTypes.slice().sort((a,b)=>typeCounts[b]-typeCounts[a]).map(t=>
    '<div class="hrow"><div class="hname">'+esc(t)+'</div>'+
    '<div class="hbar-wrap"><div class="hbar" style="width:'+(typeCounts[t]/maxc*100)+'%;background:'+tc(t)+'"></div></div>'+
    '<div class="hval">'+typeCounts[t]+'</div></div>').join('');
  const histBlock='<div class="zwrap"><div class="subhead" style="margin-top:0"><h3>Node type distribution</h3><span class="cnt">'+NODES.length+' nodes</span><span class="rule"></span></div><div class="hist">'+hist+'</div></div>';

  // per-zone node counts
  const zn={}; NODES.forEach(n=>{zn[n.zone]=(zn[n.zone]||0)+1;});
  const zkeys=Object.keys(zn).sort((a,b)=>zn[b]-zn[a]);
  const maxz=Math.max(1,...zkeys.map(k=>zn[k]));
  const zhist=zkeys.map(z=>'<div class="hrow"><div class="hname">'+esc(z)+'</div>'+
    '<div class="hbar-wrap"><div class="hbar" style="width:'+(zn[z]/maxz*100)+'%;background:'+zc(z)+'"></div></div>'+
    '<div class="hval">'+zn[z]+'</div></div>').join('');
  const zhistBlock='<div class="zwrap"><div class="subhead" style="margin-top:0"><h3>Nodes per zone</h3><span class="rule"></span></div><div class="hist">'+zhist+'</div></div>';

  area.innerHTML=zoneBlock+histBlock+zhistBlock;
}

/* ==== MEDIA: figures / equations / references =========================== */
function renderMedia(){
  const area=document.getElementById('mediaarea');
  const figs=NODES.filter(n=>n.type==='figure');
  const eqs=NODES.filter(n=>n.type==='equation');
  const tbls=NODES.filter(n=>n.type==='table');
  const refs=NODES.filter(n=>n.type==='reference').slice().sort((a,b)=>{
    const ma=parseInt(a.marker),mb=parseInt(b.marker);
    if(!isNaN(ma)&&!isNaN(mb))return ma-mb; if(!isNaN(ma))return -1; if(!isNaN(mb))return 1; return 0;});

  let html='';
  // figures
  html+='<div class="subhead" style="margin-top:0"><h3>Figures</h3><span class="cnt">'+figs.length+'</span><span class="rule"></span></div>';
  if(figs.length){
    html+='<div class="gal">'+figs.map(f=>{
      const cap=f.caption_ref?nodeById[f.caption_ref]:capByTarget[f.id];
      const thumb=f.file?('<img loading="lazy" src="'+esc(f.file)+'" alt="'+esc(f.label||f.id)+'" onerror="this.outerHTML=\'<div class=&quot;noimg&quot;>no image<br>('+esc(f.source||'?')+')</div>\'">'):
        ('<div class="noimg">no raster<br>source: '+esc(f.source||'?')+'</div>');
      return '<div class="gcard" id="fig-'+esc(f.id)+'"><div class="gthumb">'+thumb+'</div><div class="gbody">'+
        '<div class="glabel">'+esc(f.label||f.id)+'</div>'+
        (cap&&cap.text?('<div class="gcap">'+esc(cap.text)+'</div>'):'')+
        '<div class="cmeta" style="margin-top:7px"><span class="jump" data-goto="'+esc(f.id)+'">→ in reading</span></div></div></div>';
    }).join('')+'</div>';
  } else html+='<div class="empty">no figures</div>';

  // tables (if any)
  if(tbls.length){
    html+='<div class="subhead"><h3>Tables</h3><span class="cnt">'+tbls.length+'</span><span class="rule"></span></div>';
    html+='<div>'+tbls.map(t=>'<div class="card" style="margin-bottom:14px" id="tbl-'+esc(t.id)+'">'+tableHTML(t)+
      '<div class="cmeta" style="margin-top:8px"><span class="nid">'+esc(t.id)+'</span> · <span class="jump" data-goto="'+esc(t.id)+'">→ in reading</span></div></div>').join('')+'</div>';
  }

  // equations
  html+='<div class="subhead"><h3>Equations</h3><span class="cnt">'+eqs.length+'</span><span class="rule"></span></div>';
  if(eqs.length){
    html+='<div class="eqlist">'+eqs.map((e,i)=>
      '<div class="eqrow"><div class="eqnum">'+esc(e.id)+'</div>'+
      '<div class="eqrender eqbox" data-latex="'+esc(e.latex||'')+'" data-display="'+(e.display?1:0)+'"></div>'+
      '<button class="copy" data-copy="'+esc(e.latex||'')+'">copy TeX</button></div>').join('')+'</div>';
  } else html+='<div class="empty">no equations</div>';

  // references
  html+='<div class="subhead"><h3>References</h3><span class="cnt">'+refs.length+'</span><span class="rule"></span></div>';
  if(refs.length){
    html+='<div class="reflist">'+refs.map(r=>'<div class="refrow"><span class="rmk">'+(r.marker!=null?esc(r.marker):'•')+'</span><span>'+esc(r.text)+'</span></div>').join('')+'</div>';
  } else html+='<div class="empty">no references</div>';

  area.innerHTML=html;
  renderEquationsIn(area);
  area.querySelectorAll('[data-goto]').forEach(el=>el.onclick=()=>gotoNode(el.dataset.goto));
  area.querySelectorAll('.copy').forEach(btn=>btn.onclick=()=>{
    const tex=btn.getAttribute('data-copy')||'';
    const done=()=>{btn.textContent='copied';btn.classList.add('done');setTimeout(()=>{btn.textContent='copy TeX';btn.classList.remove('done');},1200);};
    if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(tex).then(done,()=>fallbackCopy(tex,done));}
    else fallbackCopy(tex,done);
  });
}
function fallbackCopy(text,cb){try{const ta=document.createElement('textarea');ta.value=text;ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.select();document.execCommand('copy');document.body.removeChild(ta);cb();}catch(e){}}

/* ==== filter + search =================================================== */
function applyFilter(){
  const q=(document.getElementById('search').value||'').trim().toLowerCase();
  const nodesEls=document.querySelectorAll('#readingbox .rnode');
  let shown=0;
  nodesEls.forEach(el=>{
    const t=el.dataset.type,z=el.dataset.zone;
    let ok=(typeOn[t]!==false)&&(zoneOn[z]!==false);
    if(ok&&q){ ok=(el.textContent||'').toLowerCase().indexOf(q)>=0; }
    el.style.display=ok?'':'none';
    if(ok)shown++;
    // highlight
    if(ok&&q) highlight(el,q); else if(el.dataset.hl){ clearHighlight(el); }
  });
  const box=document.getElementById('readingbox');
  let e=box.querySelector('.filter-empty');
  if(shown===0){ if(!e){e=document.createElement('div');e.className='empty filter-empty';box.appendChild(e);} e.textContent='no nodes match the current filter / search'; }
  else if(e){ e.remove(); }
}
function highlight(el,q){
  const body=el.querySelector('.rbody'); if(!body)return;
  if(el.dataset.hl===q) return;
  if(el.dataset.hl) clearHighlight(el);
  el.dataset.origHTML=el.dataset.origHTML||body.innerHTML;
  // only highlight plain-text nodes (avoid katex/img/table markup damage)
  const t=el.dataset.type;
  if(t==='equation'||t==='figure'||t==='table'){el.dataset.hl=q;return;}
  const re=new RegExp('('+q.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+')','ig');
  walkText(body,re);
  el.dataset.hl=q;
}
function walkText(node,re){
  for(let i=node.childNodes.length-1;i>=0;i--){
    const ch=node.childNodes[i];
    if(ch.nodeType===3){
      const txt=ch.nodeValue;
      if(re.test(txt)){ const span=document.createElement('span'); span.innerHTML=esc(txt).replace(re,'<mark>$1</mark>'); ch.replaceWith(span); }
    } else if(ch.nodeType===1 && ch.tagName!=='MARK'){ walkText(ch,re); }
  }
}
function clearHighlight(el){ const body=el.querySelector('.rbody'); if(body&&el.dataset.origHTML!=null){body.innerHTML=el.dataset.origHTML;} delete el.dataset.hl; }
document.getElementById('search').addEventListener('input',()=>{ if(currentView!=='reading')showView('reading'); applyFilter(); });

/* ==== navigation ======================================================== */
let currentView='overview';
const RENDERED={};
function showView(name){
  currentView=name;
  document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));
  document.getElementById('v-'+name).classList.add('active');
  document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('active',b.dataset.view===name));
  if(!RENDERED[name]){ ({overview:renderOverview,reading:renderReading,structure:()=>{buildTree();renderChunks();},zones:renderZones,media:renderMedia}[name])(); RENDERED[name]=true; }
  window.scrollTo(0,0);
}
function gotoNode(id){
  if(!id)return;
  showView('reading');
  // ensure visible even if filtered
  const n=nodeById[id];
  if(n){ if(typeOn[n.type]===false){typeOn[n.type]=true;} if(zoneOn[n.zone]===false){zoneOn[n.zone]=true;} renderFilters(); }
  document.getElementById('search').value=''; applyFilter();
  requestAnimationFrame(()=>{
    const el=document.getElementById('n-'+id);
    if(el){ el.scrollIntoView({behavior:'smooth',block:'center'}); el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash'); }
  });
}

/* ==== provenance tooltip =============================================== */
const tt=document.getElementById('tt');
document.addEventListener('mouseover',e=>{
  const el=e.target.closest&&e.target.closest('.rnode[data-prov]');
  if(!el){return;}
  const id=el.id.replace(/^n-/,''); const s=provStr(id);
  if(!s){return;}
  tt.innerHTML='<span class="ttk">'+esc(id)+'</span>  ·  '+esc(s);
  tt.style.opacity='1';
});
document.addEventListener('mousemove',e=>{
  if(tt.style.opacity!=='1')return;
  let x=e.clientX+14,y=e.clientY+16;
  const w=tt.offsetWidth,h=tt.offsetHeight;
  if(x+w>window.innerWidth-8)x=e.clientX-w-14; if(y+h>window.innerHeight-8)y=e.clientY-h-16;
  tt.style.left=x+'px';tt.style.top=y+'px';
});
document.addEventListener('mouseout',e=>{ const el=e.target.closest&&e.target.closest('.rnode[data-prov]'); if(el)tt.style.opacity='0'; });

/* ==== keyboard nav ===================================================== */
document.addEventListener('keydown',e=>{
  if(e.target.tagName==='INPUT')return;
  const map={'1':'overview','2':'reading','3':'structure','4':'zones','5':'media'};
  if(map[e.key])showView(map[e.key]);
  if(e.key==='/'){e.preventDefault();document.getElementById('search').focus();}
});

/* ==== boot ============================================================= */
// KaTeX loads with `defer`; re-render any equations already on screen once it arrives.
window.addEventListener('load',()=>{ document.querySelectorAll('.eqbox[data-latex]').forEach(el=>{ if(!el.querySelector('.katex')&&!el.querySelector('.eqfallback'))renderOneEq(el); else if(el.querySelector('.eqfallback')&&window.katex)renderOneEq(el); }); });
showView('overview');
</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
