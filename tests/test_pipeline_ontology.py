from __future__ import annotations

from pathlib import Path

import pytest

from parse_anything.pipeline.ontology import compute_font_ranks, load_ontology, tag_nodes
from parse_anything.pipeline.sections import _assign_heading_levels, build_sections

_ONTOLOGY_DIR = Path(__file__).resolve().parents[1] / "ontology"


def _load(family: str = "default"):
    return load_ontology(family, _ONTOLOGY_DIR)


def test_ontology_load_parses_frontmatter_subset():
    o = _load("default")
    assert o.id == "pa:ontology/default" and o.version == "1.0.0"
    assert len(o.sha256) == 64                                   # bytes hashed for provenance
    assert "body" in o.zones and "references" in o.zones and "cover" in o.zones
    assert o.node_types["figure"].atomic is True                # nested flow map parsed
    assert [r.id for r in o.rules][:3] == ["noise-furniture", "math-garble-furniture", "doc-title"]  # rule ORDER preserved
    dt = next(r for r in o.rules if r.id == "doc-title")         # deeply-nested flow: {all: [{...}, {...}]}
    assert "all" in dt.when and dt.then["type"] == "title" and dt.then["zone"] == "cover"


def test_classify_axes_for_common_nodes():
    o = _load("default")

    def role_zone(sig):
        v = o.classify(sig)
        return v.role, v.zone, v.opens_zone

    assert role_zone({"page_index": 0, "odl_role": "Doctitle", "odl_type": "heading", "text": "A Title"}) == ("title", "cover", False)
    # references/appendix are back-matter: they open only in the document tail (page_frac gate)
    assert role_zone({"odl_type": "heading", "text": "References", "page_frac": 0.9})[1:] == ("references", True)
    assert role_zone({"odl_type": "heading", "text": "6. References", "page_frac": 0.95})[1:] == ("references", True)
    assert role_zone({"odl_type": "heading", "text": "References", "page_frac": 0.1})[1:] == (None, False)  # early TOC mention -> no open
    assert role_zone({"odl_type": "heading", "text": "Contents"})[1:] == ("toc", False)  # toc tags only its own line (no span)
    assert o.classify({"odl_type": "paragraph", "text": "1.2 Method details"}).role == "heading"    # numbered
    assert o.classify({"odl_type": "heading", "text": "Introduction"}).role == "heading"            # prose
    assert o.classify({"odl_type": "paragraph", "text": "We present a pipeline."}).role == "paragraph"
    assert o.classify({"odl_type": "list item", "text": "first bullet"}).role == "list_item"


def test_degenerate_extraction_noise_is_zoned_furniture():
    o = _load("default")
    noise = ("a1111111111 a1111111111 a1111111111 a1111111111 a1111111111",
             "x x x x x x", "──────────", "..........")
    for text in noise:
        v = o.classify({"odl_type": "paragraph", "text": text})
        assert v.zone == "furniture", f"{text!r} -> {v.zone}"
    # real prose and short/varied lines are NOT furniture (abstain-safe)
    for text in ("We present a deterministic pipeline.", "the cat sat on the mat", "hi hi", "10 20 30 40"):
        assert o.classify({"odl_type": "paragraph", "text": text}).zone != "furniture", text


def test_math_garble_fragments_are_zoned_furniture():
    o = _load("default")
    garbled = ("LLðy;modelÞ ¼ log pðdatajy;modelÞ ¼", "log pðCi;j;kjy; modelÞ;",
               "d ¼ r QlargeðsmallÞ ¼ r pðCL ¼ largeðsmallÞÞ VlargeðsmallÞ;", "k¼1", "i¼1")
    for text in garbled:
        assert o.classify({"odl_type": "paragraph", "text": text}).zone == "furniture", text
    # clean prose / a real quarter-fraction phrase are NOT furniture
    assert o.classify({"odl_type": "paragraph", "text": "Add ¼ cup of sugar to the mix."}).zone != "furniture"
    assert o.classify({"odl_type": "paragraph", "text": "The model was fit to the data."}).zone != "furniture"


def test_front_matter_labels_are_zoned_metadata_near_the_front():
    o = _load("default")
    fm = ("OPEN ACCESS", "Citation: Lee H-J, Lee H", "Received: February 14, 2023",
          "Copyright: © 2023 Lee et al.", "Competing interests: none", "Funding: This research was supported",
          "Data Availability Statement: on GitHub", "Abbreviations: PDM, perceptual decision-making")
    for text in fm:
        v = o.classify({"odl_type": "paragraph", "text": text, "page_frac": 0.03})
        assert v.zone == "metadata", f"{text!r} -> {v.zone}"
        assert v.role == "paragraph" and v.opens_zone is False       # per-node only, does not span
    # the same label deep in the document is NOT reclassified (front-only, avoids body false positives)
    assert o.classify({"odl_type": "paragraph", "text": "Funding: ...", "page_frac": 0.8}).zone is None
    # real front-page prose (abstract body) stays body/unzoned -- only the labels match
    assert o.classify({"odl_type": "paragraph", "text": "Corrective feedback received on decisions is crucial.",
                       "page_frac": 0.03}).zone is None


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
    from parse_anything.pipeline.outline import HeadingAuthority, OutlineEntry
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


def test_backmatter_zone_opens_only_in_the_document_tail():
    # a 'References' MENTION early in the document (a table-of-contents entry) must NOT open the references
    # zone; the real heading in the tail does. Fixes the labchip over-extension (TOC on p2 swept the body).
    onto = _load()
    blocks = [
        {"id": "toc", "type": "heading", "page": 2, "order": 1, "text": "7. 참고문헌"},        # TOC entry, early
        {"id": "b1", "type": "paragraph", "page": 2, "order": 2, "text": "서론 본문이 이어진다."},
        {"id": "ref", "type": "heading", "page": 21, "order": 3, "text": "7. 참고문헌"},        # the real one, tail
        {"id": "e1", "type": "paragraph", "page": 21, "order": 4, "text": "1. Gold JI. A paper. 2020."},
    ]
    tag_nodes(blocks, [], [], onto, n_pages=22)
    z = {b["id"]: b["zone"] for b in blocks}
    assert z["toc"] == "body" and z["b1"] == "body"            # early TOC mention did NOT open references
    assert z["ref"] == "references" and z["e1"] == "references"  # the tail heading does


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


def test_toc_zone_does_not_span_to_the_body():
    # a table of contents has no closing marker before the body -> toc must NOT open a spanning zone,
    # else every body node after "Contents" is mislabeled toc (regression guard).
    blocks = [
        {"id": "t", "type": "heading", "page": 1, "order": 1, "text": "Contents"},
        {"id": "b1", "type": "paragraph", "page": 2, "order": 2, "text": "Body text after the ToC."},
        {"id": "b2", "type": "paragraph", "page": 3, "order": 3, "text": "More body."},
    ]
    tag_nodes(blocks, [], [], _load(), n_pages=3)
    zones = {b["id"]: b["zone"] for b in blocks}
    assert zones["t"] == "toc"                                   # only the Contents line is toc
    assert zones["b1"] == "body" and zones["b2"] == "body"       # body is not swept into toc


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
    from parse_anything.pipeline.sections import _is_prose_not_heading
    assert _is_prose_not_heading("(2020).") and _is_prose_not_heading("(13)")   # citation year / eq number
    assert not _is_prose_not_heading("(2) Results follow from the fitted model")  # a real numbered heading is fine


def test_build_semantic_separates_geometry_into_a_provenance_sidecar():
    from parse_anything.pipeline.output import _build_semantic
    onto = _load()
    blocks = [
        {"id": "t1", "role": "title", "zone": "cover", "type": "heading", "text": "A Title",
         "page": 1, "order": 1, "bbox": [0, 0, 10, 10], "font_size": 18.0},
        {"id": "h1", "role": "heading", "zone": "body", "type": "heading", "text": "Introduction",
         "page": 1, "order": 2, "bbox": [0, 0, 5, 5], "font_size": 13.0},
        {"id": "p1", "role": "paragraph", "zone": "body", "type": "paragraph", "text": "Body text.",
         "page": 1, "order": 3, "bbox": [0, 0, 5, 5], "font_size": 10.0, "refs": ["fig1"]},
    ]
    figures = [{"id": "fig1", "role": "figure", "zone": "body", "type": "figure", "label": "Figure 1",
                "caption": "cap", "kind": "chart", "file": "assets/fig1.png", "page": 1, "order": 4,
                "bbox": [1, 2, 3, 4], "source": "vector", "description": "a chart"}]
    tables = [{"id": "tb1", "role": "table", "zone": "body", "type": "table", "label": "Table 1",
               "caption": "tc", "n_rows": 1, "n_cols": 2, "views": {"md": "tables/tb1.md"},
               "cells": [[{"text": "a", "bbox": [0, 0, 1, 1]}, {"text": "b"}]],
               "regions": [{"page": 1, "bbox": [0, 0, 9, 9]}], "order": 5}]
    sections = [{"id": "sec1", "heading": "Introduction", "level": 1, "zone": "body", "block_id": "h1",
                 "page": 1, "parent": None, "children": [], "content": ["p1"]}]
    meta = {"document_id": "d1", "content_sha256": "x", "original_filename": "f.pdf", "source": {},
            "n_pages": 1, "mode": "det_vlm", "producer": {"title": "prod"}}
    pages_content = [(0, ["t1", "h1", "p1", "fig1", "tb1"])]
    page_md = {0: "Some text with a display equation $$E = mc^2$$ and more prose."}
    doc, prov = _build_semantic(blocks, tables, figures, sections, pages_content, meta, onto, page_md)
    nodes = {n["id"]: n for n in doc["nodes"]}

    for n in doc["nodes"]:                                       # semantic nodes carry NO geometry
        assert not ({"bbox", "order", "font_size"} & set(n)), n
    assert prov["p1"]["bbox"] == [0, 0, 5, 5] and prov["p1"]["font_size"] == 10.0   # geometry -> sidecar
    assert prov["fig1"]["bbox"] == [1, 2, 3, 4] and "regions" in prov["tb1"]
    assert nodes["h1"]["level"] == 1 and nodes["h1"]["type"] == "heading"           # heading shows section level
    assert doc["metadata"]["title"] == "A Title"                # title from the role=title node
    assert nodes["p1"]["refs"] == ["fig1"]                      # cross-refs preserved
    assert nodes["tb1"]["cells"] == [[{"text": "a"}, {"text": "b"}]]                # cell bbox stripped

    # caption promotion: fig1/tb1 captions become caption nodes; the host references them, no dup text
    assert nodes["fig1"]["caption_ref"] == "fig1_cap" and "caption" not in nodes["fig1"]
    assert nodes["fig1_cap"]["type"] == "caption" and nodes["fig1_cap"]["caption_of"] == "fig1"
    assert nodes["fig1_cap"]["text"] == "cap" and nodes["tb1_cap"]["caption_of"] == "tb1"

    # equation promotion: the display equation from the markdown becomes an equation node in reading order
    assert nodes["eq_p1_0"]["type"] == "equation" and nodes["eq_p1_0"]["latex"] == "E = mc^2"
    assert nodes["eq_p1_0"]["display"] is True and nodes["eq_p1_0"]["zone"] == "body"
    assert "eq_p1_0" in doc["reading_order"] and doc["reading_order"][0] == "t1"


def test_injecting_a_different_ontology_changes_the_tagging():
    # the exact same node tags differently under 'default' vs 'paper' -- proving runtime injection, no code change.
    sig = {"page_index": 0, "odl_type": "paragraph", "text": "Abstract  We present a deterministic pipeline."}
    assert _load("default").classify(sig).zone is None          # default has no abstract rule
    assert _load("paper").classify(sig).zone == "metadata"      # paper zones the abstract into metadata
