#!/usr/bin/env python3
"""Phase 9 eval harness (scaffold) for the semantic-captioning golden labels.

Scores a pipeline's per-sample output against gt/*.json golden assertions,
encoding plan risks: A(unit) B(arithmetic) C(entity) G(grounding) + caption
must/must-not. The semantic-captioning pipeline does not exist yet, so
``--selftest`` exercises the checks against synthetic good/bad outputs -- the
bad one emulates the reference parser's observed failures (unit-stripped
caption, paraphrased entity, broken sum) so the harness itself is verified.

Pipeline output schema (per label, JSON):
  {
    "caption": "<figure/chart/drawing description>",
    "elements": [{"kind": "...", "bbox": [x0,y0,x1,y1]}, ...],
    "structured": { ... mirrors the label's structured_expected ... }
  }

Usage:
  python score.py --selftest
  python score.py --out <dir>     # score <dir>/<label-stem>.json against each gt label
  python score.py --list
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

GT_DIR = Path(__file__.rsplit("/", 1)[0]) / "gt"


# --- helpers ---------------------------------------------------------------

def flatten_text(obj) -> str:
    """All string leaves of a nested structure, space-joined (for substring scans)."""
    out: list[str] = []
    def walk(o):
        if isinstance(o, str):
            out.append(o)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                walk(v)
        elif o is not None:
            out.append(str(o))
    walk(obj)
    return " ".join(out)


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _walk_dicts(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _walk_dicts(value)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            yield from _walk_dicts(value)


def _structured_unit_hit(structured, unit: str) -> bool:
    target = unit.lower()
    for item in _walk_dicts(structured):
        for key in ("unit", "increment_unit", "expected_unit", "currency", "scale_unit"):
            value = item.get(key)
            if isinstance(value, str) and value.lower() == target:
                return True
    return False


def _has_currency_structure(structured, currency: str) -> bool:
    if _structured_unit_hit(structured, currency):
        return True
    if currency.upper() == "IDR":
        return bool(isinstance(structured, dict) and structured.get("line_items") and structured.get("totals"))
    return False


def _scale_hit(blob: str, structured, expected: str) -> bool:
    m = re.search(r"(\d+\s*:\s*\d+)", expected)
    if not m:
        return False
    wanted = re.sub(r"\s+", "", m.group(1))
    for item in _walk_dicts(structured):
        value = item.get("scale")
        if isinstance(value, str) and re.sub(r"\s+", "", value) == wanted:
            return True
    wanted_pattern = r"\s*:\s*".join(re.escape(part) for part in wanted.split(":"))
    return bool(re.search(rf"(?:scale|maßstab|masstab).{{0,24}}{wanted_pattern}", blob, re.IGNORECASE))


def _unit_attached_to_value(blob: str, unit: str) -> bool:
    if unit == "%":
        return bool(re.search(r"\d[\d,.]*\s*%", blob))
    if unit == "시:분":
        return bool(re.search(r"\b\d{1,2}:\d{2}\b", blob))
    return bool(re.search(rf"\d[\d,.:\-]*{re.escape(unit)}", blob))


def _implied_unit_hit(blob: str, structured, unit: str) -> bool:
    if unit.upper() == "IDR":
        return _has_currency_structure(structured, unit)
    if unit.lower() == "mm":
        return "dimensions" in (structured if isinstance(structured, dict) else {}) or bool(
            re.search(r"(?:\bdia|[ø⌀]|[rR]\d|\d[\d,.]*(?:\s*[±-]|\s*x\s*45))", blob)
        )
    return unit.lower() in blob.lower()


def _unit_requirement_hit(requirement: str, blob: str, structured) -> bool:
    req = requirement.strip()
    low = req.lower()
    if not req or low in ("none", "n/a"):
        return True
    if "scale" in low:
        return _scale_hit(blob, structured, req)
    if "(implied)" in low:
        return _implied_unit_hit(blob, structured, req.split("(", 1)[0].strip())
    return _structured_unit_hit(structured, req) or _unit_attached_to_value(blob, req)


def sum_residual(parts, total) -> float:
    """abs(sum(parts) - total) -- mirrors guards.sum_residual (F7)."""
    return abs(sum(parts) - total)


def _bboxes(output: dict) -> int:
    return sum(1 for e in output.get("elements", []) if e.get("bbox"))


def _bbox_iou(a, b) -> float:
    ax0, ay0, ax1, ay1 = [float(v) for v in a]
    bx0, by0, bx1, by1 = [float(v) for v in b]
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    union = area_a + area_b - inter
    return inter / union if union else 0.0


# --- checks (each returns (check_id, status, detail)) ----------------------
# status: PASS / FAIL / SKIP

def check_must_not(label, output):
    # SCHEMA: must_not_include fails when a token appears in the DESCRIPTION (caption) -- it guards against
    # the VLM FABRICATING a value/unit into prose. The same value legitimately lives verbatim in structured
    # data (chart_data/tables/extractions, quoted not generated per plan 5-C), so structured is NOT scanned
    # -- doing so flagged real born-digital chart values as fabrications. Mirrors check_must_include (caption-only).
    cap = output.get("caption") or ""
    bad = [t for t in label.get("caption_expected", {}).get("must_not_include", []) if t and t in cap]
    return ("caption_must_not", "FAIL" if bad else "PASS", f"present={bad}" if bad else "ok")


def check_must_include(label, output):
    toks = label.get("caption_expected", {}).get("must_include", [])
    if not toks:
        return ("caption_must_include", "SKIP", "no tokens")
    cap = (output.get("caption") or "")
    miss = [t for t in toks if t not in cap]
    return ("caption_must_include", "FAIL" if miss else "PASS", f"missing={miss}" if miss else "ok")


def check_A_unit(label, output):
    a = label.get("risk_checks", {}).get("A_unit")
    if not a:
        return ("A_unit", "SKIP", "n/a")
    units = [part.strip() for unit in _as_list(a.get("expected_unit")) for part in str(unit).split(",")]
    cap = (output.get("caption") or "") + " " + flatten_text(output.get("structured"))
    if any(u and u.lower() in ("none", "n/a") for u in units):
        return ("A_unit", "PASS", "no-unit expected (negative control)")
    hit = [u for u in units if _unit_requirement_hit(u, cap, output.get("structured"))]
    miss = [u for u in units if u and u not in hit]
    return ("A_unit", "PASS" if not miss else "FAIL",
            f"units_found={hit}" if not miss else f"missing_or_detached={miss}")


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _arithmetic_checks(structured) -> list[dict]:
    if not isinstance(structured, dict):
        return []
    checks = structured.get("arithmetic_checks")
    if isinstance(checks, dict):
        return [checks]
    if isinstance(checks, list):
        return [c for c in checks if isinstance(c, dict)]
    return []


def check_B_arithmetic(label, output):
    b = label.get("risk_checks", {}).get("B_arithmetic")
    if not b:
        return ("B_arithmetic", "SKIP", "n/a")
    relation = str(b.get("relation", "")).lower()
    assertion = str(b.get("assert", "")).lower()
    if relation.startswith("none") or assertion in ("n/a", "none"):
        return ("B_arithmetic", "PASS", "no arithmetic expected")
    st = output.get("structured", {})
    explicit = []
    for check in _arithmetic_checks(st):
        parts = [_to_float(v) for v in _as_list(check.get("parts"))]
        total = _to_float(check.get("total"))
        tolerance = _to_float(check.get("tolerance")) or 0.0
        if total is None or any(v is None for v in parts):
            explicit.append(("invalid", None))
            continue
        residual = sum_residual([v for v in parts if v is not None], total)
        explicit.append(("ok" if residual <= tolerance else "fail", residual))
    if explicit:
        failed = [r for status, r in explicit if status != "ok"]
        return ("B_arithmetic", "FAIL" if failed else "PASS",
                f"residuals={failed}" if failed else "explicit arithmetic checks ok")
    li = st.get("line_items")
    tot = st.get("totals")
    if not (li and tot):
        return ("B_arithmetic", "SKIP", "no arithmetic structure in output")
    prices = [x.get("price", 0) for x in li]
    r1 = sum_residual(prices, tot.get("sub_total", 0))
    comps = [tot.get(k, 0) for k in ("sub_total", "service", "pb1", "rounding")]
    r2 = sum_residual(comps, tot.get("grand_total", 0))
    ok = r1 == 0 and r2 == 0
    return ("B_arithmetic", "PASS" if ok else "FAIL", f"residuals sub={r1} grand={r2}")


def check_C_entity(label, output):
    c = label.get("risk_checks", {}).get("C_entity")
    if not c:
        return ("C_entity", "SKIP", "n/a")
    verbatim = [v for v in c.get("verbatim", []) if v and not v.endswith("as written") and " as " not in v]
    blob = (output.get("caption") or "") + " " + flatten_text(output.get("structured"))
    miss = [v for v in verbatim if v not in blob]
    return ("C_entity", "FAIL" if miss else "PASS", f"missing/paraphrased={miss}" if miss else "ok")


def check_G_grounding(label, output):
    exp = len(label.get("elements_expected", []))
    got = _bboxes(output)
    if exp == 0:
        return ("G_grounding", "SKIP", "no elements")
    expected_boxes = [e for e in label.get("elements_expected", []) if e.get("bbox")]
    if expected_boxes:
        threshold = float(label.get("grounding_iou_threshold", 0.5))
        actual = [e for e in output.get("elements", []) if e.get("bbox")]
        missed = []
        for expected in expected_boxes:
            expected_kind = (expected.get("kind") or "").lower()
            candidates = [
                _bbox_iou(expected["bbox"], candidate["bbox"])
                for candidate in actual
                if not expected_kind or (candidate.get("kind") or "").lower() == expected_kind
            ]
            if max(candidates, default=0.0) < threshold:
                missed.append(expected)
        return ("G_grounding", "FAIL" if missed else "PASS",
                f"missed_iou={len(missed)} threshold={threshold}" if missed else f"{len(expected_boxes)} bbox IoU match(es)")
    return ("G_grounding", "PASS" if got >= 1 else "FAIL", f"{got} bbox'd elements (expected ~{exp})")


CHECKS = [check_must_not, check_must_include, check_A_unit,
          check_B_arithmetic, check_C_entity, check_G_grounding]


def score_one(label, output):
    return [fn(label, output) for fn in CHECKS]


# --- selftest: synthesize good / bad outputs from a label ------------------

def synth_good(label) -> dict:
    st = label.get("structured_expected", {})
    a = label.get("risk_checks", {}).get("A_unit", {})
    units = a.get("expected_unit", [])
    units = units if isinstance(units, list) else [units]
    unit_str = " ".join(u for u in units if u and u.lower() not in ("none", "n/a"))
    verb = " ".join(v for v in label.get("risk_checks", {}).get("C_entity", {}).get("verbatim", [])
                    if v and " as " not in v and not v.endswith("as written"))
    inc = " ".join(label.get("caption_expected", {}).get("must_include", []))
    cap = f"{inc} {unit_str} {verb}".strip()
    return {"caption": cap,
            "elements": [{"kind": e.get("kind"), "bbox": [0, 0, 1, 1]}
                         for e in label.get("elements_expected", [])],
            "structured": st}


def synth_bad(label) -> dict:
    """Emulate the reference parser's failures: strip units, paraphrase an entity,
    break the sum."""
    out = synth_good(label)
    mn = label.get("caption_expected", {}).get("must_not_include", [])
    # unit-stripped / fabricated: inject a must_not token if the label defines one
    out["caption"] = (mn[0] if mn else "").join([out["caption"], ""]) if mn else out["caption"]
    # drop units and one verbatim entity from the caption
    a = label.get("risk_checks", {}).get("A_unit", {})
    units = a.get("expected_unit", [])
    units = units if isinstance(units, list) else [units]
    for u in units:
        if u:
            out["caption"] = out["caption"].replace(u, "")
    verb = [v for v in label.get("risk_checks", {}).get("C_entity", {}).get("verbatim", [])
            if v and " as " not in v]
    if verb:
        out["caption"] = out["caption"].replace(verb[0], "<paraphrased>")
        dumped = json.dumps(out["structured"], ensure_ascii=False)  # keep non-ASCII so replace matches
        out["structured"] = json.loads(dumped.replace(verb[0], "<paraphrased>"))
    # break arithmetic
    st = out.get("structured", {})
    if isinstance(st.get("totals"), dict):
        st["totals"] = dict(st["totals"], sub_total=st["totals"].get("sub_total", 0) + 999)
    return out


def run_selftest(labels) -> int:
    print("=== SELFTEST (synthetic good should PASS, bad should FAIL the risk checks) ===")
    bad_leaks = 0
    for lb in labels:
        name = lb["domain"] + "/" + Path(lb["_file"]).stem
        good = score_one(lb, synth_good(lb))
        bad = score_one(lb, synth_bad(lb))
        g_fail = [c for c, s, _ in good if s == "FAIL"]
        b_fail = [c for c, s, _ in bad if s == "FAIL"]
        gstat = "ok" if not g_fail else f"UNEXPECTED-FAIL {g_fail}"
        # bad output must trip at least one risk check (else the check is toothless)
        toothless = not b_fail
        if g_fail or toothless:
            bad_leaks += 1
        print(f"  {name:34} good={gstat:24} bad_caught={b_fail or 'NONE(!)'}")
    print(f"--- {'OK' if bad_leaks == 0 else f'{bad_leaks} PROBLEM(S)'} ---")
    return 1 if bad_leaks else 0


def score_out(labels, out_dir: Path) -> int:
    print(f"=== SCORE against {out_dir} ===")
    total_fail = 0
    for lb in labels:
        stem = Path(lb["_file"]).stem
        of = out_dir / f"{stem}.json"
        if not of.exists():
            print(f"  {stem:24} MISSING output ({of})")
            total_fail += 1
            continue
        output = json.loads(of.read_text())
        res = score_one(lb, output)
        fails = [c for c, s, _ in res if s == "FAIL"]
        total_fail += len(fails)
        print(f"  {stem:24} " + " ".join(f"{c}:{s}" for c, s, _ in res))
    print(f"--- {total_fail} failing check(s) ---")
    return 1 if total_fail else 0


def load_labels():
    labels = []
    for f in sorted(GT_DIR.glob("*.json")):
        d = json.loads(f.read_text())
        d["_file"] = f.name
        labels.append(d)
    return labels


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--out", type=str, help="dir with <label-stem>.json pipeline outputs")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    labels = load_labels()
    if a.list:
        for lb in labels:
            print(f"{lb['_file']:26} domain={lb['domain']:12} kind={lb.get('figure_kind')}")
        return 0
    if a.selftest:
        return run_selftest(labels)
    if a.out:
        return score_out(labels, Path(a.out))
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
