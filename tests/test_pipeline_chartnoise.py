from __future__ import annotations

from parse_anything.pipeline.odl_extract import OdlParagraph
from parse_anything.pipeline.output import (
    _KEEP_IN_FIG, _chart_internal_noise, _mark_chart_label_blocks, _suppress_chart_noise,
)


def test_suppress_chart_noise_drops_only_matching_standalone_lines():
    md = "本文です。\n\n1,000\n\nドイツ イタリア\n\n図3 タイトル"
    out = _suppress_chart_noise(md, {"1,000", "ドイツ イタリア"})
    lines = out.split("\n")
    assert "1,000" not in lines and "ドイツ イタリア" not in lines     # chart noise gone
    assert "本文です。" in lines and "図3 タイトル" in lines           # body + caption untouched


def test_keep_in_fig_protects_caption_and_source_lines():
    assert _KEEP_IN_FIG.match("図146−3 熱エネルギー原単位")   # caption
    assert _KEEP_IN_FIG.match("資料：セメント協会")            # source
    assert _KEEP_IN_FIG.match("備考：推定値")                  # note
    assert not _KEEP_IN_FIG.match("1,000")                     # axis tick -> droppable
    assert not _KEEP_IN_FIG.match("ドイツ イタリア 中国")      # legend -> droppable


def test_chart_internal_noise_drops_ticks_inside_bbox_but_keeps_caption_and_outside():
    paras = (
        OdlParagraph(0, "paragraph", (10.0, 100.0, 50.0, 110.0), "1,000"),        # inside -> noise
        OdlParagraph(0, "heading", (10.0, 120.0, 200.0, 130.0), "図3 推移"),       # inside but caption -> keep
        OdlParagraph(0, "paragraph", (500.0, 500.0, 540.0, 510.0), "本文の段落"),  # outside -> keep
    )
    fig = {"source": "vector", "page": 1, "bbox": [0.0, 90.0, 250.0, 140.0]}
    assert _chart_internal_noise([fig], {0: paras}) == {0: {"1,000"}}


def test_mark_chart_label_blocks_flags_inside_excludes_caption_and_outside():
    blocks = [
        {"id": "b1", "page": 1, "bbox": [10.0, 100.0, 50.0, 110.0], "text": "1,000"},       # inside -> mark
        {"id": "b2", "page": 1, "bbox": [10.0, 120.0, 200.0, 130.0], "text": "図3 推移"},    # caption -> keep
        {"id": "b3", "page": 1, "bbox": [500.0, 500.0, 540.0, 510.0], "text": "本文の段落"},  # outside -> keep
    ]
    _mark_chart_label_blocks([{"source": "vector", "page": 1, "bbox": [0.0, 90.0, 250.0, 140.0], "id": "f1"}], blocks)
    assert blocks[0].get("figure") == "f1"
    assert not blocks[1].get("figure") and not blocks[2].get("figure")
