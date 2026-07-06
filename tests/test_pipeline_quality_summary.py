from __future__ import annotations

import io
import json
from types import SimpleNamespace

from parse_anything.pipeline.output import _quality_summary


def test_quality_summary_tallies_flags_kinds_and_pages():
    pages = [
        SimpleNamespace(flags=["unsourced_number:1234", "odl_dropped_number:56"], route="det"),   # 1 page, 2 flags
        SimpleNamespace(flags=[], route="det"),                       # no flags
        SimpleNamespace(flags=["unsourced_number:9"], route="folded"),  # folded -> excluded even though flagged
    ]
    blocks = [{"id": "b1"}]
    tables = [{"id": "t1"}]
    figures = [
        {"id": "f1", "description_flags": ["unsourced_number:99999", "unit_unstated:천"]},
        {"id": "f2", "description_flags": ["unverifiable_number:88888"], "kind_confidence": "low"},
        {"id": "f3", "kind_confidence": "low"},             # low-confidence kind, but no description flags
    ]
    q = _quality_summary(pages, blocks, tables, figures)
    assert q["elements"] == 5                                # 1 block + 1 table + 3 figures
    assert q["flagged_elements"] == 2                        # f1, f2 (f3 has no description_flags)
    assert q["flag_counts"] == {"unsourced_number": 1, "unit_unstated": 1, "unverifiable_number": 1}
    assert q["low_confidence_figures"] == 2                  # f2, f3
    assert q["pages_flagged"] == 1                           # folded page excluded
    # page-level oracle/completeness signals are tallied by prefix (not just a bare pages_flagged count)
    assert q["page_flag_counts"] == {"unsourced_number": 1, "odl_dropped_number": 1}


def test_quality_summary_clean_document_is_all_zeros():
    pages = [SimpleNamespace(flags=[], route="det")]
    q = _quality_summary(pages, [{"id": "b1"}], [], [])
    assert q == {"elements": 1, "flagged_elements": 0, "flag_counts": {}, "low_confidence_figures": 0,
                 "pages_flagged": 0, "page_flag_counts": {}}


def test_document_json_carries_quality_but_structure_json_strips_it(tmp_path):
    # FR-6: the honesty summary is a document.json overlay; it must NOT leak into the typed structure contract
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    import parse_anything.cli as cli

    pdf = tmp_path / "doc.pdf"
    c = canvas.Canvas(str(pdf), pagesize=letter)
    c.drawString(72, 720, "Plain prose page.")
    c.showPage()
    c.save()
    out = tmp_path / "out"
    assert cli.run_cli(["--pdf", str(pdf), "--out", str(out), "--no-vlm"],
                       cli.Runtime(environ={}, stdout=io.StringIO()), env_file=tmp_path / "absent.env") == 0
    docdir = list((out / "default").glob("*"))[0]
    doc = json.loads((docdir / "document.json").read_text(encoding="utf-8"))
    assert "quality" in doc and "elements" in doc["quality"]
    structure = json.loads((docdir / "document.structure.json").read_text(encoding="utf-8"))
    assert "quality" not in structure   # overlay stripped from the contract surface
