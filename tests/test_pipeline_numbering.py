from __future__ import annotations

import pytest

from odl_vl.pipeline.numbering import classify_numbering


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
