from __future__ import annotations

from odl_vl.pipeline.odl_extract import OdlDocument, OdlPage, OdlParagraph
from odl_vl.pipeline.outline import parse_printed_toc, resolve_heading_authority


def _p(text):
    return OdlParagraph(1, "paragraph", (0.0, 0.0, 10.0, 10.0), text)


def test_printed_toc_cluster_parsed_with_levels_and_pages():
    toc = (_p("Ⅰ. 정책축 생태계 ········ 1"), _p("1. AI고속도로 ········ 1"),
           _p("2. 차세대 기술 ········ 17"), _p("Ⅱ. 대전환 ········ 57"), _p("9. 문화강국 ········ 109"))
    doc = OdlDocument(2, (OdlPage(0, "", (), ()), OdlPage(1, "", (), (), toc)))
    auth = parse_printed_toc(doc)
    assert auth is not None and auth.source == "printed_toc" and 1 in auth.toc_page_indices
    assert auth.entries[0].level == 1 and auth.entries[0].printed_page == "1"   # Ⅰ -> chapter
    assert auth.entries[1].level == 2 and auth.entries[1].printed_page == "1"   # 1. -> section
    assert auth.entries[3].level == 1 and auth.entries[3].printed_page == "57"  # Ⅱ -> chapter


def test_printed_toc_levels_are_document_relative_gapless():
    # （1） nests directly under "1." -> level 2 (gapless), NOT the old fixed rank 3
    toc = (_p("1. 총칙 ········ 1"), _p("（1） 목적 ········ 1"), _p("（2） 정의 ········ 3"),
           _p("2. 본칙 ········ 5"), _p("（1） 적용 ········ 5"))
    doc = OdlDocument(2, (OdlPage(0, "", (), ()), OdlPage(1, "", (), (), toc)))
    auth = parse_printed_toc(doc)
    assert [e.level for e in auth.entries] == [1, 2, 2, 1, 2]


def test_single_dotted_line_is_not_a_toc():
    doc = OdlDocument(1, (OdlPage(0, "", (), (), (_p("See the appendix ········ 12"),)),))
    assert parse_printed_toc(doc) is None   # cluster threshold (>=4) rejects a lone leader line


def test_resolve_returns_none_without_pdf_or_toc():
    doc = OdlDocument(1, (OdlPage(0, "body", (), (), (_p("just a body paragraph."),)),))
    assert resolve_heading_authority(None, doc) is None   # -> caller falls back to numbering inference
