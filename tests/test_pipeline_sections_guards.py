from __future__ import annotations

from parse_anything.pipeline.sections import (_AUTHOR_AFFIL, _is_list_not_heading, _is_prose_not_heading,
                                      _looks_like_equation)


def test_looks_like_equation():
    assert _looks_like_equation("C = (K + I)X")                 # carries '='
    assert _looks_like_equation("x^2 + y (13)")                # trailing equation number
    assert _looks_like_equation("N(0, 1)")                     # no real word (symbols/single letters)
    assert _looks_like_equation("a - b")
    assert _looks_like_equation("A B")                         # a chart-label fragment
    assert not _looks_like_equation("Introduction")            # a real heading survives
    assert not _looks_like_equation("Materials and methods")
    assert not _looks_like_equation("참고문헌")                  # CJK word counts


def test_is_prose_not_heading():
    assert _is_prose_not_heading("0.3 s | 0.9 s | 0.7 s")      # inline table data row
    assert _is_prose_not_heading("(2020).")                    # a bare citation-year / eq number
    assert _is_prose_not_heading("(13)")
    assert _is_prose_not_heading("See https://doi.org/x for the data")   # carries a URL/DOI
    assert _is_prose_not_heading("First sentence. Second sentence. Third one.")  # >= 2 sentence boundaries
    assert _is_prose_not_heading("12: 345-360.")               # 'marker:digits' volume:page citation
    assert not _is_prose_not_heading("Introduction")
    assert not _is_prose_not_heading("1. Method")
    assert not _is_prose_not_heading("2.1 Dimensionality reduction")


def test_is_list_not_heading():
    assert _is_list_not_heading("A bullet that ends with a period.", "list item")   # list item + terminator
    assert _is_list_not_heading("x" * 70, "list item")                              # list item + long
    assert not _is_list_not_heading("Short label", "list item")
    assert _is_list_not_heading("y" * 130 + ".", "paragraph")                       # very long prose + terminator
    assert not _is_list_not_heading("A normal heading", "heading")


def test_author_affiliation_marker():
    assert _AUTHOR_AFFIL.search("Kenneth W. Latimer1")         # letter bonded to a superscript digit
    assert _AUTHOR_AFFIL.search("Hyang-Jung Lee1, Heeseung Lee1")
    assert _AUTHOR_AFFIL.search("A. Author*")
    assert not _AUTHOR_AFFIL.search("Introduction")
    assert not _AUTHOR_AFFIL.search("Materials and methods")


def test_numbered_heading_levels_are_overridden_by_the_outline_authority():
    from parse_anything.pipeline.outline import HeadingAuthority, OutlineEntry
    from parse_anything.pipeline.sections import _assign_heading_levels
    blocks = [
        {"id": "h1", "type": "heading", "page": 1, "order": 1, "text": "1 Introduction"},
        {"id": "h2", "type": "heading", "page": 1, "order": 2, "text": "1.1 Background"},
    ]
    auth = HeadingAuthority(entries=[
        OutlineEntry("Introduction", 1, None, 0, "pdf_outline"),
        OutlineEntry("Background", 2, None, 0, "pdf_outline"),
    ], toc_page_indices=frozenset(), source="pdf_outline")
    lvl, _ = _assign_heading_levels(blocks, authority=auth)
    assert lvl == {"h1": 1, "h2": 2}                           # authority levels win (override path)


def test_authority_override_pops_deeper_open_sections():
    # a heading that returns to a shallower authority level must pop the deeper open frames off the stack.
    from parse_anything.pipeline.outline import HeadingAuthority, OutlineEntry
    from parse_anything.pipeline.sections import _assign_heading_levels
    blocks = [
        {"id": "a", "type": "heading", "page": 1, "order": 1, "text": "1 Alpha"},
        {"id": "b", "type": "heading", "page": 1, "order": 2, "text": "1.1 Beta"},
        {"id": "c", "type": "heading", "page": 1, "order": 3, "text": "2 Gamma"},
    ]
    auth = HeadingAuthority(entries=[
        OutlineEntry("Alpha", 1, None, 0, "pdf_outline"),
        OutlineEntry("Beta", 2, None, 0, "pdf_outline"),
        OutlineEntry("Gamma", 1, None, 0, "pdf_outline"),
    ], toc_page_indices=frozenset(), source="pdf_outline")
    lvl, _ = _assign_heading_levels(blocks, authority=auth)
    assert lvl == {"a": 1, "b": 2, "c": 1}


def test_authority_level_skips_entries_with_empty_titles():
    from parse_anything.pipeline.outline import HeadingAuthority, OutlineEntry
    from parse_anything.pipeline.sections import _authority_level
    auth = HeadingAuthority(entries=[
        OutlineEntry("", 1, None, 0, "pdf_outline"),           # empty title -> skipped
        OutlineEntry("Methods", 2, None, 0, "pdf_outline"),
    ], toc_page_indices=frozenset(), source="pdf_outline")
    assert _authority_level("Methods", 1, auth, {}) == 2


def test_apply_heading_levels_renders_numbered_and_demotes_enumerated_runs():
    from parse_anything.pipeline.sections import apply_heading_levels
    md = "1. Introduction\n\nSome body sentence here.\n\n① first item\n② second item"
    out = apply_heading_levels(md)
    lines = out.split("\n")
    assert any(ln.startswith("#") and "Introduction" in ln for ln in lines)   # numbered heading -> '#'
    assert "① first item" in out and not any(ln.startswith("#") and "first item" in ln for ln in lines)
