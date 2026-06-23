from __future__ import annotations

import json

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from odl_vl.pipeline.docmeta import DocumentMeta
from odl_vl.pipeline.odl_extract import OdlDocument, OdlImage, OdlPage, OdlTable
from odl_vl.pipeline.output import document_dir, write_outputs
from odl_vl.pipeline.run import DocumentResult, PageOutcome


def _one_page_pdf(path) -> str:
    c = canvas.Canvas(str(path), pagesize=letter)
    c.drawString(72, 700, "page with a figure region")
    c.showPage()
    c.save()
    return str(path)


def test_assets_crops_figure_image_and_sets_pointer(tmp_path):
    pdf = _one_page_pdf(tmp_path / "d.pdf")
    figure = OdlImage(0, (72, 600, 300, 720), element_id="i1", label="Figure 1", kind="figure")
    structure = OdlDocument(1, (OdlPage(0, "text", (), (figure,)),))
    meta = DocumentMeta("id1234567890abcd", "id1234567890abcdff", "d.pdf", n_pages=1, mode="deterministic")
    result = DocumentResult((PageOutcome(0, "deterministic", False, "md", 0.0, ()),), structure=structure, meta=meta)

    out = document_dir(tmp_path, result)
    write_outputs(result, out, pdf_path=pdf)

    assert (out / "assets" / "f001.png").exists()
    doc = json.loads((out / "document.json").read_text(encoding="utf-8"))
    assert doc["figures"][0]["file"] == "assets/f001.png"


def test_rich_output_document_json_and_tables(tmp_path):
    table = OdlTable(0, 2, 2, (50, 500, 400, 600), (("H", "V"), ("a", "1")), label="표 1", caption="cap")
    figure = OdlImage(0, (50, 100, 400, 300), element_id="i1", label="Figure 2", caption="figcap", kind="figure")
    structure = OdlDocument(1, (OdlPage(0, "text", (table,), (figure,)),))
    meta = DocumentMeta(document_id="abc123def4567890", content_sha256="abc123def4567890ff", original_filename="d.pdf",
                        source_id="csnl", n_pages=1, mode="deterministic")
    result = DocumentResult((PageOutcome(0, "deterministic", False, "# md", 0.0, ()),), structure=structure, meta=meta)

    out = document_dir(tmp_path, result)
    assert out == tmp_path / "csnl" / "abc123def4567890"   # <root>/<source_id>/<document_id>
    write_outputs(result, out)

    doc = json.loads((out / "document.json").read_text(encoding="utf-8"))
    assert doc["document_id"] == "abc123def4567890" and doc["original_filename"] == "d.pdf"
    assert doc["source"]["source_id"] == "csnl"
    assert len(doc["tables"]) == 1 and doc["tables"][0]["label"] == "표 1"
    assert doc["tables"][0]["cells"] == [["H", "V"], ["a", "1"]]
    assert doc["figures"][0]["label"] == "Figure 2" and doc["figures"][0]["kind"] == "figure"
    assert doc["pages"][0]["tables"] == ["t001"] and doc["pages"][0]["figures"] == ["f001"]
    assert (out / "tables" / "t001.json").exists()
    assert "| H | V |" in (out / "tables" / "t001.md").read_text(encoding="utf-8")


def test_vlm_labels_fill_table_label_and_add_missing_figures(tmp_path):
    # ODL has an unlabeled table and NO figures (Latimer-like); the VLM read a table + figure caption.
    table = OdlTable(0, 1, 2, (50, 50, 400, 200), (("H", "V"),), label=None, caption=None)
    structure = OdlDocument(1, (OdlPage(0, "text", (table,), ()),))
    meta = DocumentMeta("idabc1234567890a", "idabc1234567890aff", "d.pdf", n_pages=1, mode="det_vlm")
    labels = ({"kind": "table", "label": "Table 2", "caption": "Table 2: data"},
              {"kind": "figure", "label": "Figure 1", "caption": "Figure 1: a plot"})
    result = DocumentResult((PageOutcome(0, "det_vlm", True, "md", 0.0, (), labels),), structure=structure, meta=meta)

    out = document_dir(tmp_path, result)
    write_outputs(result, out)
    doc = json.loads((out / "document.json").read_text(encoding="utf-8"))
    assert doc["tables"][0]["label"] == "Table 2" and doc["tables"][0]["source"] == "odl"  # backfilled
    figs = doc["figures"]
    assert len(figs) == 1 and figs[0]["label"] == "Figure 1" and figs[0]["source"] == "vlm" and figs[0]["bbox"] is None


def _result() -> DocumentResult:
    return DocumentResult(
        (
            PageOutcome(0, "table_vlm", True, "# Page 0\n\n| a | 1 |", 12.0, ("spanning_table:0-1",)),
            PageOutcome(1, "folded", False, "", 0.0, ("folded_into:0",)),
            PageOutcome(2, "deterministic", False, "plain text page", 1.0, ()),
        )
    )


def test_write_outputs_creates_pages_doc_and_jsonl(tmp_path):
    write_outputs(_result(), tmp_path)
    # per-page markdown only for non-folded pages
    assert (tmp_path / "pages" / "page-000.md").read_text(encoding="utf-8").startswith("# Page 0")
    assert (tmp_path / "pages" / "page-002.md").exists()
    assert not (tmp_path / "pages" / "page-001.md").exists()  # folded -> no file
    # document assembly excludes folded pages
    doc = (tmp_path / "document.md").read_text(encoding="utf-8")
    assert "# Page 0" in doc and "plain text page" in doc


def test_results_jsonl_records_every_page_including_folded(tmp_path):
    write_outputs(_result(), tmp_path)
    rows = [json.loads(line) for line in (tmp_path / "results.jsonl").read_text().splitlines()]
    assert [r["page_index"] for r in rows] == [0, 1, 2]
    folded = next(r for r in rows if r["page_index"] == 1)
    assert folded["route"] == "folded" and "folded_into:0" in folded["flags"]
    assert "markdown_file" not in folded


def test_ledger_jsonl_has_one_row_per_page(tmp_path):
    write_outputs(_result(), tmp_path)
    rows = [json.loads(line) for line in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert len(rows) == 3
    assert rows[0]["route"] == "table_vlm" and rows[0]["used_vlm"] is True
