from __future__ import annotations

from odl_vl.pipeline.odl_extract import _FIGURE_LABEL_RE, _TABLE_LABEL_RE, parse_document


def test_label_regex_handles_japanese_marks_and_unicode_dashes():
    assert _TABLE_LABEL_RE.match("表146−5 世界主要国")   # JP 表 + U+2212 minus
    assert _TABLE_LABEL_RE.match("表146-5")              # ASCII hyphen
    assert _TABLE_LABEL_RE.match("表 146-5")             # space after the mark
    assert _FIGURE_LABEL_RE.match("図147-2 主要国")       # JP 図
    assert _TABLE_LABEL_RE.match("Table 5-2") and _FIGURE_LABEL_RE.match("그림 3")
    assert not _TABLE_LABEL_RE.match("本表146は参照")     # an inline mention is not a caption


def test_label_regex_strips_leading_brackets_korean_japanese():
    assert _TABLE_LABEL_RE.match("<표 5-1> 의료 동향").group(1) == "표 5-1"   # angle-bracketed KO form
    assert _FIGURE_LABEL_RE.match("〈図3〉 推移").group(1) == "図3"
    assert _TABLE_LABEL_RE.match("表146−5 世界").group(1) == "表146−5"        # bare form unaffected


def test_parse_binds_table_caption_from_a_heading_block():
    # ODL frequently tags a table title as a "heading", not a "caption" node; it must still bind.
    data = {
        "number of pages": 1,
        "kids": [
            {"type": "heading", "page number": 1, "bounding box": [10, 100, 200, 112],
             "content": "表5-1 売上推移", "id": 1},
            {"type": "table", "page number": 1, "bounding box": [10, 40, 200, 95], "id": 2,
             "number of rows": 1, "number of columns": 2,
             "rows": [{"cells": [{"content": "a"}, {"content": "b"}]}]},
        ],
    }
    table = parse_document(data).pages[0].tables[0]
    assert table.label == "表5-1" and table.caption == "表5-1 売上推移"


def test_parse_prefers_title_caption_over_footnote():
    data = {
        "number of pages": 1,
        "kids": [
            {"type": "caption", "page number": 1, "bounding box": [10, 20, 200, 30],
             "content": "資料：統計局", "id": 1, "linked content id": 3},
            {"type": "heading", "page number": 1, "bounding box": [10, 100, 200, 112],
             "content": "表5-1 売上推移", "id": 2},
            {"type": "table", "page number": 1, "bounding box": [10, 40, 200, 95], "id": 3,
             "number of rows": 1, "number of columns": 1, "rows": [{"cells": [{"content": "x"}]}]},
        ],
    }
    table = parse_document(data).pages[0].tables[0]
    assert table.caption == "表5-1 売上推移"   # the title wins the caption field over the 資料 footnote
