from __future__ import annotations

import json

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from parse_anything.pipeline.docmeta import DocumentMeta
from parse_anything.pipeline.odl_extract import OdlDocument, OdlImage, OdlPage, OdlTable
from parse_anything.pipeline.output import document_dir, write_outputs
from parse_anything.pipeline.run import DocumentResult, PageOutcome


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

    assert (out / "assets" / "p1_i1.png").exists()   # asset named by the figure's page-namespaced id
    doc = json.loads((out / "document.json").read_text(encoding="utf-8"))
    assert doc["figures"][0]["id"] == "p1_i1" and doc["figures"][0]["file"] == "assets/p1_i1.png"


def test_rich_output_document_json_and_tables(tmp_path):
    table = OdlTable(0, 2, 2, (50, 500, 400, 600), (("H", "V"), ("a", "1")), label="표 1", caption="cap",
                     cell_boxes=(((10, 10, 20, 20), (30, 10, 40, 20)), ((10, 30, 20, 40), (30, 30, 40, 40))))
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
    cells = doc["tables"][0]["cells"]                          # rich per-cell {text, bbox}
    assert cells[0][0] == {"text": "H", "bbox": [10, 10, 20, 20]}
    assert cells[1][1] == {"text": "1", "bbox": [30, 30, 40, 40]}
    assert doc["figures"][0]["label"] == "Figure 2" and doc["figures"][0]["kind"] == "figure"
    tid, fid = doc["tables"][0]["id"], doc["figures"][0]["id"]
    # graph: page references its elements by id, and the reading-order content stream holds them
    assert doc["pages"][0]["tables"] == [tid] and doc["pages"][0]["figures"] == [fid]
    assert tid in doc["pages"][0]["content"] and fid in doc["pages"][0]["content"]
    assert (out / "tables" / f"{tid}.json").exists()
    assert "| H | V |" in (out / "tables" / f"{tid}.md").read_text(encoding="utf-8")


def test_spanning_tables_merge_into_one_logical_table(tmp_path):
    # ODL splits a table across pages and links them with previous_table_id -> one logical table.
    t1 = OdlTable(0, 2, 2, (50, 400, 400, 600), (("H1", "H2"), ("a", "1")), table_id="tbl-1")
    t2 = OdlTable(1, 1, 2, (50, 600, 400, 700), (("b", "2"),), table_id="tbl-2", previous_table_id="tbl-1")
    structure = OdlDocument(2, (OdlPage(0, "", (t1,), ()), OdlPage(1, "", (t2,), ())))
    meta = DocumentMeta("idspanning123456", "idspanning123456ff", "d.pdf", n_pages=2, mode="deterministic")
    pages = (PageOutcome(0, "deterministic", False, "p1", 0.0, ()), PageOutcome(1, "deterministic", False, "p2", 0.0, ()))
    result = DocumentResult(pages, structure=structure, meta=meta)

    out = document_dir(tmp_path, result)
    write_outputs(result, out)
    doc = json.loads((out / "document.json").read_text(encoding="utf-8"))
    assert len(doc["tables"]) == 1                                  # merged, not two
    merged = doc["tables"][0]
    assert merged["pages"] == [1, 2] and merged["continued"] is True
    assert [c["text"] for row in merged["cells"] for c in row] == ["H1", "H2", "a", "1", "b", "2"]
    tid = merged["id"]                                              # one node spanning both pages
    assert doc["pages"][0]["tables"] == [tid] and doc["pages"][1]["tables"] == [tid]


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
    assert doc["tables"][0]["label"] == "Table 2"                   # ODL label backfilled from VLM caption
    figs = doc["figures"]
    # the VLM-detected figure ODL missed entirely: synthetic id, no bbox
    assert len(figs) == 1 and figs[0]["label"] == "Figure 1" and figs[0]["bbox"] is None
    assert "vlm" in str(figs[0]["id"])


def test_document_json_carries_specialized_ocr_routing_hints(tmp_path):
    figure = OdlImage(
        0,
        (72, 520, 180, 620),
        element_id="stamp",
        label="Approval stamp",
        caption="Approval stamp with handwritten signature",
        kind="stamp",
    )
    structure = OdlDocument(1, (OdlPage(0, "", (), (figure,)),))
    meta = DocumentMeta("idroutehint12345", "idroutehint12345ff", "d.pdf", n_pages=1, mode="deterministic")
    result = DocumentResult((PageOutcome(0, "deterministic", False, "", 0.0, ()),), structure=structure, meta=meta)

    out = document_dir(tmp_path, result)
    write_outputs(result, out, chunk=False)

    doc = json.loads((out / "document.json").read_text(encoding="utf-8"))
    hints = doc["routing_hints"]
    assert hints == [
        {
            "target": "p1_stamp",
            "page": 1,
            "bbox": [72, 520, 180, 620],
            "route": "doc_specialized_ocr",
            "reason": "handwriting",
        },
        {
            "target": "p1_stamp",
            "page": 1,
            "bbox": [72, 520, 180, 620],
            "route": "doc_specialized_ocr",
            "reason": "stamp",
        },
    ]


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
