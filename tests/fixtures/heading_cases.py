"""Heading-vs-not fixtures -- across document types, which numbered lines are real section headings
and which are list items / references / citations / prose. Tests that detection generalizes (the
numbering classifier + the conservative guards) rather than overfitting. Add a doc type -> add a case.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class HeadingCase:
    text: str
    is_heading: bool
    note: str = ""


HEADING_CASES: list[HeadingCase] = [
    # --- real section headings (various scripts / marker styles) ---
    HeadingCase("第1章 我が国製造業の特徴", True, "JP chapter"),
    HeadingCase("第4節 主要製造業の課題", True, "JP section"),
    HeadingCase("（１）現状", True, "JP paren subsection"),
    HeadingCase("6 セメント産業", True, "bare decimal section"),
    HeadingCase("①強み", True, "circled item"),
    HeadingCase("1) AI고속도로 구축", True, "KR num-paren"),
    HeadingCase("가. 세부 항목", True, "KR hangul ordinal"),
    HeadingCase("제3조 적용범위", True, "KR legal article"),
    HeadingCase("1.1 Background", True, "decimal depth 2"),
    HeadingCase("Ⅰ. 정책축AI혁신 생태계 조성", True, "roman chapter"),
    HeadingCase("1. Introduction", True, "EN numbered section"),
    HeadingCase("3. Materials and methods.", True, "EN heading w/ trailing period"),
    # --- NOT headings: references / citations / prose that lead with a number ---
    HeadingCase("13. Daw ND, Doya K. The computational neurobiology of learning and reward. "
                "Curr Opin Neurobiol. 2006;", False, "reference entry: multiple sentence boundaries"),
    HeadingCase("(1):2757. https://doi.org/10.1038/s41467-020-16196-7 PMID: 32488065", False,
                "citation fragment: URL/DOI/PMID"),
    HeadingCase("47. Mochol G, Kiani R, Moreno-Bote R. Prefrontal cortex represents heuristics that "
                "shape choice bias. Curr Biol. 2021. https://doi.org/10.1016/j.cub.2021.01.068", False,
                "reference entry: URL + sentences"),
    HeadingCase("1. See the appendix for the full derivation, and visit https://example.com for code.",
                False, "numbered prose with a URL"),
    HeadingCase("(3):213–224.", False, "volume:page citation tail"),
    HeadingCase("(1):2757", False, "bare volume:page"),
    HeadingCase("0.3 s | 0.9 s | 0.5 s", False, "table data row rendered inline"),
]
