from __future__ import annotations

from pathlib import Path

import pytest

from odl_vl.pipeline.ontology import compute_font_ranks, load_ontology, tag_nodes
from odl_vl.pipeline.sections import _assign_heading_levels, build_sections

_ONTOLOGY_DIR = Path(__file__).resolve().parents[1] / "ontology"


def _load(family: str = "default"):
    return load_ontology(family, _ONTOLOGY_DIR)


def test_ontology_load_parses_frontmatter_subset():
    o = _load("default")
    assert o.id == "odl:ontology/default" and o.version == "1.0.0"
    assert len(o.sha256) == 64                                   # bytes hashed for provenance
    assert "body" in o.zones and "references" in o.zones and "cover" in o.zones
    assert o.node_types["figure"].atomic is True                # nested flow map parsed
    assert [r.id for r in o.rules][:2] == ["doc-title", "references-zone"]   # rule ORDER preserved
    dt = next(r for r in o.rules if r.id == "doc-title")         # deeply-nested flow: {all: [{...}, {...}]}
    assert "all" in dt.when and dt.then["type"] == "title" and dt.then["zone"] == "cover"


def test_classify_axes_for_common_nodes():
    o = _load("default")

    def role_zone(sig):
        v = o.classify(sig)
        return v.role, v.zone, v.opens_zone

    assert role_zone({"page_index": 0, "odl_role": "Doctitle", "odl_type": "heading", "text": "A Title"}) == ("title", "cover", False)
    assert role_zone({"odl_type": "heading", "text": "References"})[1:] == ("references", True)
    assert role_zone({"odl_type": "heading", "text": "6. References"})[1:] == ("references", True)   # numbered ref heading
    assert role_zone({"odl_type": "heading", "text": "Contents"})[1:] == ("toc", True)
    assert o.classify({"odl_type": "paragraph", "text": "1.2 Method details"}).role == "heading"    # numbered
    assert o.classify({"odl_type": "heading", "text": "Introduction"}).role == "heading"            # prose
    assert o.classify({"odl_type": "paragraph", "text": "We present a pipeline."}).role == "paragraph"
    assert o.classify({"odl_type": "list item", "text": "first bullet"}).role == "list_item"


def test_unknown_predicate_raises_loudly(tmp_path):
    (tmp_path / "bad.md").write_text(
        "---\nid: t\nversion: 1\nrules:\n  - {id: r, when: {bogus: 1}, then: {type: paragraph}}\n---\nbody\n",
        encoding="utf-8")
    o = load_ontology("bad", tmp_path)
    with pytest.raises(ValueError):
        o.classify({"text": "x"})                               # an undefined predicate must fail, not silently pass


_BODY = "We present a deterministic-first pipeline that separates document structure from content quality."


def test_unnumbered_headings_are_admitted_only_with_the_ontology():
    # csnl/rats-shape: ODL typed the headings as "heading" but they carry NO numbering. Without an ontology
    # the numbering-only gate abstains (0 sections); with it, a heading FOLLOWED BY BODY prose is admitted
    # and leveled by font rank.
    blocks = [
        {"id": "b1", "type": "heading", "page": 1, "order": 1, "text": "Introduction", "font_size": 13.0},
        {"id": "b2", "type": "paragraph", "page": 1, "order": 2, "text": _BODY, "font_size": 10.0},
        {"id": "b3", "type": "heading", "page": 1, "order": 3, "text": "Methods", "font_size": 13.0},
        {"id": "b4", "type": "paragraph", "page": 2, "order": 4, "text": _BODY, "font_size": 10.0},
        {"id": "b5", "type": "heading", "page": 2, "order": 5, "text": "Results", "font_size": 13.0},
        {"id": "b6", "type": "paragraph", "page": 2, "order": 6, "text": _BODY, "font_size": 10.0},
    ]
    fr = compute_font_ranks(blocks)
    off, _ = _assign_heading_levels(blocks)                     # no ontology -> abstains
    assert off == {}
    on, _ = _assign_heading_levels(blocks, ontology=_load(), font_ranks=fr)
    assert set(on) == {"b1", "b3", "b5"} and set(on.values()) == {1}   # headings only, all top-level
    assert "b2" not in on and "b4" not in on                    # body prose is NOT over-fired into headings
    secs, _ = build_sections(blocks, [], [], on)
    assert [s["heading"] for s in secs] == ["Introduction", "Methods", "Results"]


def test_unnumbered_headings_nest_by_document_outline_authority():
    # when the document declares its own hierarchy (a PDF outline / printed TOC), unnumbered headings are
    # nested by THAT authority (reliable), not by font. Without an authority they stay flat (level 1).
    from odl_vl.pipeline.outline import HeadingAuthority, OutlineEntry
    blocks = [
        {"id": "h1", "type": "heading", "page": 1, "order": 1, "text": "Introduction", "font_size": 13.0},
        {"id": "p1", "type": "paragraph", "page": 1, "order": 2, "text": _BODY, "font_size": 10.0},
        {"id": "h2", "type": "heading", "page": 1, "order": 3, "text": "Methods", "font_size": 13.0},
        {"id": "p2", "type": "paragraph", "page": 1, "order": 4, "text": _BODY, "font_size": 10.0},
        {"id": "h3", "type": "heading", "page": 1, "order": 5, "text": "Participants", "font_size": 11.0},
        {"id": "p3", "type": "paragraph", "page": 1, "order": 6, "text": _BODY, "font_size": 10.0},
    ]
    fr = compute_font_ranks(blocks)
    # no authority -> flat
    flat, _ = _assign_heading_levels(blocks, ontology=_load(), font_ranks=fr)
    assert flat == {"h1": 1, "h2": 1, "h3": 1}
    # authority declares Participants a subsection of Methods -> real nesting, from the document itself
    auth = HeadingAuthority(entries=[
        OutlineEntry("Introduction", 1, None, 0, "pdf_outline"),
        OutlineEntry("Methods", 1, None, 0, "pdf_outline"),
        OutlineEntry("Participants", 2, None, 0, "pdf_outline"),
    ], toc_page_indices=frozenset(), source="pdf_outline")
    nested, _ = _assign_heading_levels(blocks, authority=auth, ontology=_load(), font_ranks=fr)
    assert nested == {"h1": 1, "h2": 1, "h3": 2}
    secs, _ = build_sections(blocks, [], [], nested)
    methods = next(s for s in secs if s["heading"] == "Methods")
    participants = next(s for s in secs if s["heading"] == "Participants")
    assert participants["parent"] == methods["id"]   # Participants nests under Methods, by the outline


def test_author_lines_and_chart_labels_are_not_admitted_as_sections():
    # a real section heading is followed by body prose; an author/affiliation line and a chart label
    # (surrounded by more labels, no following body) must NOT become sections.
    blocks = [
        {"id": "a1", "type": "heading", "page": 1, "order": 1, "text": "Hyang-Jung Lee1, Heeseung Lee1", "font_size": 11.0},
        {"id": "h1", "type": "heading", "page": 1, "order": 2, "text": "Introduction", "font_size": 13.0},
        {"id": "p1", "type": "paragraph", "page": 1, "order": 3, "text": _BODY, "font_size": 10.0},
        {"id": "x1", "type": "heading", "page": 3, "order": 4, "text": "Chart title label here", "font_size": 6.0},
        {"id": "x2", "type": "heading", "page": 3, "order": 5, "text": "Another label", "font_size": 6.0},
    ]
    fr = compute_font_ranks(blocks)
    lvl, _ = _assign_heading_levels(blocks, ontology=_load(), font_ranks=fr)
    assert set(lvl) == {"h1"}                                   # author (affil marker) + unfollowed labels dropped


def test_numbered_headings_are_unchanged_by_the_ontology():
    # a numbered document must level identically with or without the ontology (no regression).
    blocks = [
        {"id": "n1", "type": "heading", "page": 1, "order": 1, "text": "1 Introduction", "font_size": 13.0},
        {"id": "n2", "type": "paragraph", "page": 1, "order": 2, "text": "Body.", "font_size": 10.0},
        {"id": "n3", "type": "heading", "page": 1, "order": 3, "text": "1.1 Setup", "font_size": 11.0},
        {"id": "n4", "type": "heading", "page": 1, "order": 4, "text": "2 Method", "font_size": 13.0},
    ]
    fr = compute_font_ranks(blocks)
    base, _ = _assign_heading_levels(blocks)
    withont, _ = _assign_heading_levels(blocks, ontology=_load(), font_ranks=fr)
    assert base == withont == {"n1": 1, "n3": 2, "n4": 1}


def test_tag_nodes_zone_spans_from_a_references_heading():
    blocks = [
        {"id": "b1", "type": "paragraph", "page": 1, "order": 1, "text": "Body text here."},
        {"id": "b2", "type": "heading", "page": 2, "order": 2, "text": "References"},
        {"id": "b3", "type": "paragraph", "page": 2, "order": 3, "text": "[1] Smith 2020."},
        {"id": "b4", "type": "paragraph", "page": 2, "order": 4, "text": "[2] Lee 2021."},
    ]
    tag_nodes(blocks, [], [], _load())
    zones = {b["id"]: b["zone"] for b in blocks}
    assert zones == {"b1": "body", "b2": "references", "b3": "references", "b4": "references"}
    assert blocks[0]["role"] == "paragraph"


def test_prose_admission_vetoes_equations_symbols_and_chart_labels():
    # ODL also types the title/author, display equations, and chart-internal labels as "heading". Only a
    # real prose heading survives the guards -- equations ('=' / '(13)'), symbol fragments (no word), and
    # chart-noise-flagged blocks are vetoed.
    blocks = [
        {"id": "h1", "type": "heading", "page": 2, "order": 1, "text": "Discussion", "font_size": 12.0},
        {"id": "p1", "type": "paragraph", "page": 2, "order": 2, "text": _BODY, "font_size": 10.0},
        {"id": "e1", "type": "heading", "page": 2, "order": 3, "text": "C = (K + I)X. (13)", "font_size": 10.0},
        {"id": "e2", "type": "heading", "page": 2, "order": 4, "text": "N(0, 1)", "font_size": 10.0},
        {"id": "c1", "type": "heading", "page": 2, "order": 5, "text": "A B", "font_size": 6.0},
        {"id": "c2", "type": "heading", "page": 2, "order": 6, "text": "total", "font_size": 6.0, "figure": "p2_vec0"},
    ]
    fr = compute_font_ranks(blocks)
    lvl, _ = _assign_heading_levels(blocks, ontology=_load(), font_ranks=fr)
    assert set(lvl) == {"h1"}                                   # equation / symbols / chart labels all vetoed


def test_bare_paren_number_is_never_a_section_heading():
    from odl_vl.pipeline.sections import _is_prose_not_heading
    assert _is_prose_not_heading("(2020).") and _is_prose_not_heading("(13)")   # citation year / eq number
    assert not _is_prose_not_heading("(2) Results follow from the fitted model")  # a real numbered heading is fine


def test_injecting_a_different_ontology_changes_the_tagging():
    # the exact same node tags differently under 'default' vs 'paper' -- proving runtime injection, no code change.
    sig = {"page_index": 0, "odl_type": "paragraph", "text": "Abstract  We present a deterministic pipeline."}
    assert _load("default").classify(sig).zone is None          # default has no abstract rule
    assert _load("paper").classify(sig).zone == "metadata"      # paper zones the abstract into metadata
