from __future__ import annotations

from odl_vl.pipeline.output import _resolve_cross_references


def test_cross_references_link_intext_mentions_robust_to_wrap_and_dashes():
    tables = [{"id": "t1", "label": "表146−5"}, {"id": "t2", "label": "表146−2"}]
    figures = [{"id": "f1", "label": "図146−4"}]
    blocks = [
        {"id": "b1", "text": "国別に見ると…（図146− 4、表146-5）。"},  # wrap-space + ASCII dash variant
        {"id": "b2", "text": "表146−5 世界主要国のセメント"},          # caption itself -> not a self ref
        {"id": "b3", "text": "本文に番号はない。"},
    ]
    _resolve_cross_references(blocks, tables, figures)
    assert set(blocks[0]["refs"]) == {"t1", "f1"}   # 図146−4 (despite wrap space) + 表146-5 (ASCII dash)
    assert "refs" not in blocks[1]                  # a node's own leading caption is not a reference
    assert "refs" not in blocks[2]                  # no mention -> no edge


def test_cross_reference_does_not_confuse_numeric_prefixes():
    tables = [{"id": "t14", "label": "表14"}, {"id": "t146", "label": "表146"}]
    blocks = [{"id": "b1", "text": "（表146）を参照"}]
    _resolve_cross_references(blocks, tables, [])
    assert blocks[0]["refs"] == ["t146"]            # 表14 must NOT match inside 表146 (digit boundary)
