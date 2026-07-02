from __future__ import annotations

import pytest

from parse_anything.pipeline.numbering import classify_numbering


@pytest.mark.parametrize("text,rank", [
    ("第1章 我が国製造業の特徴", 1), ("제1장 총칙", 1), ("Chapter 3 Methods", 1), ("Ⅰ. 정책축AI혁신", 1),
    ("第4節 主要製造業の課題", 2), ("제2절 정의", 2), ("Section 2", 2), ("6 セメント産業", 2), ("1. AI고속도로", 2),
    ("（１）現状（表146-1）", 3), ("제3항 적용", 3), ("1.1 Background", 3),
    ("①強み", 4), ("(a) first", 4), ("1.1.1 Detail", 4),
])
def test_recognized_prefixes_rank_by_class(text, rank):
    nc = classify_numbering(text)
    assert nc is not None and nc.rank == rank


@pytest.mark.parametrize("text", [
    "2003年の全世界のセメント需要量は",   # leading number but no space + sentence
    "我が国セメント産業の2003年度",
    "6,874万トンに占める割合",            # thousands separator, not a label
    "El titular o representante",          # plain label, no numbering
    "Datos del Titular / Host Data",
    "",
])
def test_unrecognized_prefixes_abstain(text):
    assert classify_numbering(text) is None


def test_decimal_depth_increases_rank():
    assert classify_numbering("2. x").rank == 2
    assert classify_numbering("2.3 x").rank == 3
    assert classify_numbering("2.3.4 x").rank == 4
    assert classify_numbering("2.3.4.5 x").rank == 4   # clamped at item depth


def test_signature_carries_style_tier_dec_depth():
    assert classify_numbering("第1章 概要").tier == 0 and classify_numbering("第1章 概要").style == "chapter"
    assert classify_numbering("第4節 課題").tier == 1
    assert classify_numbering("（１）現状").style == "paren" and classify_numbering("（１）現状").tier == 2
    d = classify_numbering("1.1 背景")
    assert d.style == "decimal:2" and d.dec_depth == 2 and d.tier == 2
    assert classify_numbering("① 強み").style == "circled"


def test_new_korean_markers_recognized_with_styles():
    assert classify_numbering("1) 항목").style == "num_paren" and classify_numbering("1) 항목").rank == 3
    assert classify_numbering("가. 세부").style == "hangul_letter"
    assert classify_numbering("나) 항목").style == "hangul_letter"
    assert classify_numbering("제3조 적용").style == "ko_article" and classify_numbering("제3조 적용").rank == 2
    assert classify_numbering("제2항 정의").style == "ko_subdiv"
    assert classify_numbering("가능하다는 점은") is None      # an arbitrary hangul word is not a marker
    assert classify_numbering("것을 의미한다.") is None
