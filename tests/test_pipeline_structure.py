from __future__ import annotations

from parse_anything.pipeline.odl_extract import OdlDocument, OdlImage, OdlPage, OdlParagraph, OdlTable
from parse_anything.pipeline.structure import _merge_blocks, build_graph


def _para(eid, order, text, kind="paragraph", font=None):
    return OdlParagraph(0, kind, (0.0, 0.0, 10.0, 10.0), text, element_id=eid, font_size=font, order=order)


def _blk(text, bbox, kind="paragraph", font=10.0):
    return OdlParagraph(0, kind, bbox, text, font_size=font, order=0)


def test_merge_stitches_vertically_adjacent_wrap_split():
    a = _blk("規模の経済の利点を活かしながら引き続", (0, 90, 100, 100))
    b = _blk("きグローバルな事業活動を行う。", (0, 78, 100, 90))   # directly below, no gap
    out = _merge_blocks((a, b))
    assert len(out) == 1 and out[0].text.endswith("行う。") and "引き続き" in out[0].text


def test_no_merge_when_a_gap_separates_distinct_labels():
    a = _blk("El titular o representante", (0, 90, 100, 100))
    b = _blk("The owner or representative", (0, 50, 100, 62))   # large vertical gap -> separate
    assert len(_merge_blocks((a, b))) == 2


def test_no_merge_into_heading_marker_or_complete_sentence():
    assert len(_merge_blocks((_blk("①今後の対応", (0, 90, 100, 100)), _blk("本文", (0, 78, 100, 90))))) == 2
    assert len(_merge_blocks((_blk("完成した文。", (0, 90, 100, 100)), _blk("次段落", (0, 78, 100, 90))))) == 2


def test_no_merge_across_columns():
    a = _blk("left column tail no period", (0, 90, 100, 100))
    b = _blk("right column top", (120, 90, 220, 100))   # different column -> no x-overlap
    assert len(_merge_blocks((a, b))) == 2


def test_content_stream_interleaves_blocks_tables_figures_in_reading_order():
    table = OdlTable(0, 1, 1, (0, 0, 100, 100), (("x",),), table_id=100, order=2)
    fig = OdlImage(0, (0, 0, 50, 50), element_id=200, order=4)
    page = OdlPage(0, "first third", tables=(table,), images=(fig,),
                   paragraphs=(_para(1, 1, "first"), _para(3, 3, "third")))
    pages, blocks, tables, figs = build_graph(OdlDocument(1, (page,)), {})
    # page-namespaced ids ("p{page}_{odl_id}") -- ODL ids collide across pages, so this makes them unique
    assert pages[0]["content"] == ["p1_1", "p1_100", "p1_3", "p1_200"]   # para, table, para, figure
    assert pages[0]["blocks"] == ["p1_1", "p1_3"] and pages[0]["tables"] == ["p1_100"] and pages[0]["figures"] == ["p1_200"]
    assert {b["id"]: b["type"] for b in blocks} == {"p1_1": "paragraph", "p1_3": "paragraph"}


def test_caption_binding_and_page_element_bidirectional():
    fig = OdlImage(0, (0, 0, 50, 50), element_id=77, caption="A plot", caption_id=78, kind="figure", order=1)
    pages, blocks, tables, figs = build_graph(OdlDocument(1, (OdlPage(0, "", (), (fig,)),)), {})
    assert figs[0]["id"] == "p1_77" and figs[0]["caption"] == "A plot" and figs[0]["caption_id"] == "p1_78"
    assert figs[0]["page"] == 1               # element -> page back-reference
    assert pages[0]["figures"] == ["p1_77"]   # page -> element forward reference


def test_cross_page_table_is_one_node_present_in_both_pages():
    t1 = OdlTable(0, 1, 2, (0, 0, 100, 100), (("H1", "H2"),), table_id=10, order=1)
    t2 = OdlTable(1, 1, 2, (0, 0, 100, 100), (("a", "b"),), table_id=11, previous_table_id=10, order=5)
    doc = OdlDocument(2, (OdlPage(0, "", (t1,), ()), OdlPage(1, "", (t2,), ())))
    pages, blocks, tables, figs = build_graph(doc, {})
    assert len(tables) == 1 and tables[0]["id"] == "p1_10" and tables[0]["pages"] == [1, 2] and tables[0]["continued"]
    assert pages[0]["tables"] == ["p1_10"] and pages[1]["tables"] == ["p1_10"]   # one node referenced by both pages
    assert "p1_10" in pages[0]["content"] and "p1_10" in pages[1]["content"]


def test_same_page_tables_are_not_merged():
    # ODL links distinct same-page tables 1->2 via previous_table_id (its generic prev pointer); the
    # graph must keep them separate -- a same-page link is not a spanning continuation.
    t1 = OdlTable(0, 1, 1, (0, 0, 100, 100), (("x",),), table_id=1, order=1)
    t2 = OdlTable(0, 1, 1, (0, 0, 100, 100), (("y",),), table_id=2, previous_table_id=1, order=2)
    pages, blocks, tables, figs = build_graph(OdlDocument(1, (OdlPage(0, "", (t1, t2), ()),)), {})
    assert {t["id"] for t in tables} == {"p1_1", "p1_2"} and all(not t["continued"] for t in tables)


def test_cell_spans_emitted_only_when_merged():
    table = OdlTable(0, 1, 2, (0, 0, 100, 100), (("merged", "b"),),
                     cell_spans=(((1, 2), (1, 1)),), table_id=5, order=1)
    pages, blocks, tables, figs = build_graph(OdlDocument(1, (OdlPage(0, "", (table,), ()),)), {})
    cells = tables[0]["cells"][0]
    assert cells[0] == {"text": "merged", "bbox": None, "row_span": 1, "col_span": 2}
    assert "col_span" not in cells[1]   # a 1x1 cell stays lean


def test_vlm_only_figure_gets_synthetic_id_at_tail():
    labels = {0: ({"kind": "figure", "label": "Figure 9", "caption": "Fig 9: x"},)}
    pages, blocks, tables, figs = build_graph(OdlDocument(1, (OdlPage(0, "body", (), ()),)), labels)
    assert len(figs) == 1 and "vlm" in str(figs[0]["id"]) and figs[0]["bbox"] is None
    assert figs[0]["label"] == "Figure 9"


def test_block_carries_font_size_and_kind():
    page = OdlPage(0, "Heading", tables=(), images=(),
                   paragraphs=(_para(1, 1, "Heading", kind="heading", font=18.0),))
    pages, blocks, tables, figs = build_graph(OdlDocument(1, (page,)), {})
    assert blocks[0]["type"] == "heading" and blocks[0]["font_size"] == 18.0
