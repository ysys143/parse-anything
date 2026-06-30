from __future__ import annotations

from odl_vl.pipeline.sections import apply_heading_levels, build_sections, heading_levels


def _b(bid, order, text, *, page=1, kind="paragraph"):
    return {"id": bid, "type": kind, "page": page, "order": order, "text": text}


def test_numbered_heading_detected_body_and_caption_abstain():
    blocks = [_b("h1", 1, "第1章 概要"), _b("p1", 2, "これは本文です。"),
              _b("h2", 3, "（１）現状"), _b("cap", 4, "表1 データの推移")]
    lm = heading_levels(blocks)
    assert lm["h1"] == 1 and lm["h2"] == 3
    assert "p1" not in lm and "cap" not in lm   # plain body + a table-caption label abstain


def test_enumerated_item_run_demoted_section_kept():
    blocks = [_b("s", 1, "第1節 전환 조건", kind="paragraph"),
              _b("i1", 2, "① 첫째 조건", kind="list item"),
              _b("i2", 3, "② 둘째 조건", kind="list item"),
              _b("i3", 4, "③ 셋째 조건", kind="list item")]
    lm = heading_levels(blocks)
    assert lm.get("s") == 2 and not ({"i1", "i2", "i3"} & set(lm))   # ①②③ are a list, demoted


def test_subsection_with_body_between_is_kept():
    blocks = [_b("a", 1, "（１）現状"), _b("body", 2, "ここに本文がある。"), _b("b", 3, "（２）展望")]
    lm = heading_levels(blocks)
    assert lm.get("a") == 3 and lm.get("b") == 3   # body between siblings -> both kept


def test_build_sections_nests_and_backrefs():
    blocks = [_b("h1", 1, "第1章 A"), _b("p", 2, "body"), _b("h2", 3, "（１）B")]
    secs, sbn = build_sections(blocks, [], [], heading_levels(blocks))
    assert len(secs) == 2 and secs[1]["parent"] == secs[0]["id"]
    assert sbn["p"] == secs[0]["id"] and "p" in secs[0]["content"]   # body attaches to its section


def test_apply_heading_levels_prefixes_and_relevels():
    md = "第1章 概要\n\n本文\n\n# （１）現状"
    lines = apply_heading_levels(md, [("第1章 概要", 1), ("（１）現状", 3)]).split("\n")
    assert "# 第1章 概要" in lines       # deterministic line (no #) gets a prefix
    assert "### （１）現状" in lines      # VLM's single # is re-leveled to ###
    assert "本文" in lines               # body untouched
