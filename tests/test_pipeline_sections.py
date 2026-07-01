from __future__ import annotations

from odl_vl.pipeline.sections import (
    apply_heading_levels, build_sections, heading_levels, strip_page_furniture,
)


def _b(bid, order, text, *, page=1, kind="paragraph"):
    return {"id": bid, "type": kind, "page": page, "order": order, "text": text}


def test_numbered_heading_detected_body_and_caption_abstain():
    blocks = [_b("h1", 1, "第1章 概要"), _b("p1", 2, "これは本文です。"),
              _b("h2", 3, "（１）現状"), _b("cap", 4, "表1 データの推移")]
    lm = heading_levels(blocks)
    assert lm["h1"] == 1 and lm["h2"] == 2   # （１） nests DIRECTLY under 第1章 (no 節 between) -> gapless 2
    assert "p1" not in lm and "cap" not in lm   # plain body + a table-caption label abstain


def test_enumerated_item_run_demoted_section_kept():
    blocks = [_b("s", 1, "第1節 전환 조건", kind="paragraph"),
              _b("i1", 2, "① 첫째 조건", kind="list item"),
              _b("i2", 3, "② 둘째 조건", kind="list item"),
              _b("i3", 4, "③ 셋째 조건", kind="list item")]
    lm = heading_levels(blocks)
    assert lm.get("s") == 1 and not ({"i1", "i2", "i3"} & set(lm))   # mid-doc 節 (no 章) is top; ①②③ demoted


def test_subsection_with_body_between_is_kept():
    blocks = [_b("a", 1, "（１）現状"), _b("body", 2, "ここに本文がある。"), _b("b", 3, "（２）展望")]
    lm = heading_levels(blocks)
    assert lm.get("a") == 1 and lm.get("b") == 1   # body between siblings -> both kept; paren is top here


def _seq_levels(*headings):
    """Levels of a heading sequence with body between each (so the enumerated-list demote never fires)."""
    blocks = []
    for k, h in enumerate(headings):
        blocks += [_b(f"h{k}", 2 * k, h), _b(f"x{k}", 2 * k + 1, "본문 문장이 여기 있다.")]
    lm = heading_levels(blocks)
    return [lm.get(f"h{k}") for k in range(len(headings))]


def test_levels_document_relative_paren_above_circled_jp():
    # 章>節>decimal>（N）>① : gapless, and paren is SHALLOWER than circled (the white-paper order)
    assert _seq_levels("第1章 A", "第1節 B", "6 C", "（１）D", "①E", "②F", "（２）G", "7 H", "第2節 I") \
        == [1, 2, 3, 4, 5, 5, 4, 3, 2]


def test_levels_inverted_circled_above_paren_korean_legal():
    # 제N조>①>가.>(1) : circled is SHALLOWER than paren -- the REVERSE order, learned from this document
    assert _seq_levels("제1조 적용", "① 조건", "가. 세부", "(1) 항목", "제2조 정의", "① 조건") \
        == [1, 2, 3, 4, 1, 2]


def test_no_level_skip_chapter_to_enumerator():
    assert _seq_levels("第1章 A", "（１）B") == [1, 2]   # paren directly under chapter -> 2 (gapless), not 3


def test_mid_document_section_is_top_level():
    assert _seq_levels("第1節 A", "（１）B") == [1, 2]   # no chapter present -> 節 is the top level


def test_decimal_depth_monotonic_in_context():
    assert _seq_levels("第1節 A", "1.1 B", "1.1.1 C") == [1, 2, 3]   # decimal chain stays gapless


def test_apply_heading_levels_uses_style_levels_not_absolute_rank():
    out = apply_heading_levels("（１）現状\n\n①強み", page_headings=[],
                               style_levels={"paren": 2, "circled": 3}).split("\n")
    assert "## （１）現状" in out and "### ①強み" in out   # document-learned scale, not fixed rank 3/4


def test_build_sections_nests_and_backrefs():
    blocks = [_b("h1", 1, "第1章 A"), _b("p", 2, "body"), _b("h2", 3, "（１）B")]
    secs, sbn = build_sections(blocks, [], [], heading_levels(blocks))
    assert len(secs) == 2 and secs[1]["parent"] == secs[0]["id"]
    assert sbn["p"] == secs[0]["id"] and "p" in secs[0]["content"]   # body attaches to its section


def test_build_sections_attaches_table_with_pages_list_to_open_section():
    blocks = [_b("h", 1, "第1章 A")]
    tables = [{"id": "t1", "type": "table", "pages": [1], "order": 2, "text": ""}]  # `pages`, not `page`
    secs, sbn = build_sections(blocks, tables, [], heading_levels(blocks))
    assert sbn.get("t1") == secs[0]["id"] and "t1" in secs[0]["content"]   # table attaches, not orphaned


def test_apply_heading_levels_prefixes_and_relevels():
    md = "第1章 概要\n\n本文\n\n# （１）現状"
    lines = apply_heading_levels(md, [("第1章 概要", 1), ("（１）現状", 3)]).split("\n")
    assert "# 第1章 概要" in lines       # deterministic line (no #) gets a prefix
    assert "### （１）現状" in lines      # VLM's single # is re-leveled to ###
    assert "本文" in lines               # body untouched


def test_vlm_headed_table_figure_caption_is_de_headed():
    md = "# 表145-3 機能性ガラス\n\n## 6 セメント産業\n\n# Figure 2: a plot"
    lines = apply_heading_levels(md, [("6 セメント産業", 2)]).split("\n")
    assert "## 6 セメント産業" in lines                  # the real section keeps its level
    assert "表145-3 機能性ガラス" in lines               # table caption de-headed (no #)
    assert "Figure 2: a plot" in lines                  # figure caption de-headed
    assert "# 表145-3 機能性ガラス" not in lines


def test_strip_page_furniture_removes_running_headers_and_pagenum_leak():
    from odl_vl.pipeline.textalign import norm_block
    p0 = "# 第1章 概要\n\n## 第4節 課題\n\n本文A これは十分に長い本文です\n\n## 6 セメント産業の現状\n\n128"
    p1 = "# 第1章 概要\n\n## 第4節 課題\n\nもっと本文 これも十分に長い本文です\n\n129"
    # ODL keeps the body + the one-off section, filters the running headers (第1章/第4節) -> they are absent
    odl = {0: [norm_block("本文A これは十分に長い本文です"), norm_block("6 セメント産業の現状")],
           1: [norm_block("もっと本文 これも十分に長い本文です")]}
    out = strip_page_furniture({0: p0, 1: p1}, {0: "128", 1: "129"}, odl)
    assert "第1章 概要" not in out[0] and "第4節 課題" not in out[0]   # running headers (on both pages) gone
    assert "## 6 セメント産業の現状" in out[0]                        # one-off section (in ODL) kept
    assert "128" not in out[0].split("\n") and "129" not in out[1].split("\n")  # page-number leak gone


def test_strip_page_furniture_matches_by_number_despite_text_variation():
    p0 = "# 第1章 我が国製造業第４節 主要製造業の課題"   # VLM merged two running headers onto one line
    p1 = "# 第1章 我が国製造業の特徴"                      # same header, different transcription
    out = strip_page_furniture({0: p0, 1: p1}, {}, {0: [], 1: []})  # ODL filtered these headers -> absent
    assert "第1章" not in out[0] and "第1章" not in out[1]   # keyed by the leading 第1章 token, both gone


def test_strip_page_furniture_keeps_recurring_subsections():
    out = strip_page_furniture({0: "### （１）現状\n\n本文", 1: "### （１）現状\n\n別の本文"}, {})
    assert "### （１）現状" in out[0] and "### （１）現状" in out[1]   # rank-3 subsection recurs legitimately
