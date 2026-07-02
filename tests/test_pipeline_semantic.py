from __future__ import annotations

from pathlib import Path

from parse_anything.pipeline.ontology import load_ontology
from parse_anything.pipeline.output import (_build_semantic, _display_equations_by_page, _zones_summary)

_ONTOLOGY_DIR = Path(__file__).resolve().parents[1] / "ontology"
_ONTO = load_ontology("default", _ONTOLOGY_DIR)
_META = {"document_id": "d", "content_sha256": "s", "original_filename": "f.pdf", "source": {},
         "n_pages": 1, "mode": "det_vlm", "producer": {}}


def _sem(blocks, tables=(), figures=(), sections=(), pages_content=None, page_md=None, meta=None):
    pages_content = pages_content if pages_content is not None else [(0, [b["id"] for b in blocks])]
    doc, prov = _build_semantic(list(blocks), list(tables), list(figures), list(sections),
                                pages_content, meta or _META, _ONTO, page_md)
    return doc, prov, {n["id"]: n for n in doc["nodes"]}


def _blk(i, role="paragraph", zone="body", text="x", **kw):
    return {"id": i, "role": role, "type": "paragraph" if role != "heading" else "heading",
            "zone": zone, "text": text, "page": 1, "order": kw.pop("order", 1), **kw}


# ---- geometry demotion -----------------------------------------------------------------------------
def test_all_geometry_is_demoted_to_provenance():
    blocks = [_blk("b1", bbox=[1, 2, 3, 4], font_size=10.0, order=7)]
    doc, prov, nodes = _sem(blocks)
    assert not ({"bbox", "order", "font_size", "page"} & set(nodes["b1"]))
    assert prov["b1"] == {"page": 1, "order": 7, "bbox": [1, 2, 3, 4], "font_size": 10.0}


def test_block_without_font_size_has_no_font_key_in_provenance():
    doc, prov, _ = _sem([_blk("b1")])          # no bbox/font -> only page/order demoted
    assert "font_size" not in prov["b1"] and "bbox" not in prov["b1"]


# ---- caption promotion -----------------------------------------------------------------------------
def test_caption_promotion_from_an_existing_caption_block():
    blocks = [_blk("cap", role="paragraph", text="Fig 1. A chart.")]
    figs = [{"id": "f1", "role": "figure", "type": "figure", "zone": "body", "label": "Fig 1",
             "caption": "Fig 1. A chart.", "caption_id": "cap", "page": 1, "order": 2}]
    doc, prov, nodes = _sem(blocks, figures=figs, pages_content=[(0, ["cap", "f1"])])
    assert nodes["cap"]["type"] == "caption" and nodes["cap"]["caption_of"] == "f1"   # block re-typed
    assert nodes["f1"]["caption_ref"] == "cap" and "caption" not in nodes["f1"]


def test_caption_promotion_synthesizes_when_only_a_field():
    figs = [{"id": "f1", "role": "figure", "type": "figure", "zone": "body", "label": "Fig 1",
             "caption": "only a field", "caption_id": None, "page": 1, "order": 1}]
    doc, prov, nodes = _sem([], figures=figs, pages_content=[(0, ["f1"])])
    assert nodes["f1_cap"]["type"] == "caption" and nodes["f1_cap"]["text"] == "only a field"
    assert nodes["f1"]["caption_ref"] == "f1_cap"


def test_figure_with_no_caption_gets_no_caption_ref():
    figs = [{"id": "f1", "role": "figure", "type": "figure", "zone": "body", "page": 1, "order": 1}]
    _, _, nodes = _sem([], figures=figs, pages_content=[(0, ["f1"])])
    assert "caption_ref" not in nodes["f1"]


# ---- equation extraction ---------------------------------------------------------------------------
def test_display_equations_by_page_extracts_multiple():
    md = {0: "a $$x=1$$ b $$y=2$$", 1: "no math here", 2: "$$  z = 3  $$"}
    got = _display_equations_by_page(md)
    assert got == {0: ["x=1", "y=2"], 2: ["z = 3"]}


def test_standalone_single_dollar_line_is_harvested_as_display_equation():
    # the VLM often wraps a DISPLAY equation in single $ on its own line -> harvest it as clean LaTeX,
    # even though the deterministic layer only had glyph-garbled fragments of the same equation.
    md = {0: ("For any model, the log likelihood is:\n\n"
              "$LL(\\theta, model) = \\log p(data|\\theta, model) = \\sum_{k=1}^{K} \\log p(C|\\theta),$\n\n"
              "where the value is $N \\leq 170$ inline.")}
    got = _display_equations_by_page(md)
    assert 0 in got and len(got[0]) == 1                        # the standalone line, NOT the inline $N \leq 170$
    assert got[0][0].startswith("LL(\\theta, model) =") and got[0][0].endswith("\\log p(C|\\theta)")  # trailing ',' stripped


def test_lone_inline_symbol_line_is_not_a_display_equation():
    md = {0: "$x$\n$\\theta$"}                                  # short lone symbols -> not display equations
    assert _display_equations_by_page(md) == {}


def test_equation_nodes_are_woven_into_reading_order_per_page():
    blocks = [_blk("p0", order=1), _blk("p1", order=1)]
    pages_content = [(0, ["p0"]), (1, ["p1"])]
    page_md = {0: "text $$a=b$$", 1: "no eq"}
    doc, _, nodes = _sem(blocks, pages_content=pages_content, page_md=page_md)
    assert nodes["eq_p1_0"]["type"] == "equation" and nodes["eq_p1_0"]["latex"] == "a=b"
    assert nodes["eq_p1_0"]["display"] is True
    assert doc["reading_order"] == ["p0", "eq_p1_0", "p1"]   # equation follows its page's content


def test_no_markdown_means_no_equation_nodes():
    doc, _, _ = _sem([_blk("p0")])
    assert not any(n["type"] == "equation" for n in doc["nodes"])


def test_synthesized_caption_is_woven_into_reading_order():
    # a field-only caption becomes a synthesized `caption` node -> it must enter the reading order (right
    # after its host) so its text reaches the chunks, not just the (chunk-less) node pool.
    figs = [{"id": "f1", "role": "figure", "type": "figure", "zone": "body", "label": "Fig 1",
             "caption": "Fig 1. Important result", "caption_id": None, "page": 1, "order": 1}]
    doc, _, nodes = _sem([], figures=figs, pages_content=[(0, ["f1"])])
    assert doc["reading_order"] == ["f1", "f1_cap"]              # woven right after the host figure
    assert nodes["f1_cap"]["text"] == "Fig 1. Important result"  # caption text is retrievable, not dropped


def test_furniture_nodes_leave_reading_order_but_stay_in_the_pool():
    blocks = [_blk("p1", text="Real body sentence."), _blk("junk", zone="furniture", text="a1111 a1111 a1111")]
    doc, _, nodes = _sem(blocks, pages_content=[(0, ["p1", "junk"])])
    assert "junk" in nodes and nodes["junk"]["zone"] == "furniture"   # kept in the pool (loss-aware)
    assert doc["reading_order"] == ["p1"]                             # but out of the reading flow (and chunks)


# ---- references parsing ----------------------------------------------------------------------------
def test_references_entries_are_retyped_and_markers_lifted():
    blocks = [
        _blk("h", role="heading", zone="references", text="References"),
        _blk("r1", role="heading", zone="references", text="1. Gold JI. A paper. 2020."),
        _blk("r2", role="paragraph", zone="references", text="[2] Hwang EJ. Another. 2019."),
        _blk("r3", role="paragraph", zone="references", text="(3) Kim H. Third. 2021."),
        _blk("r4", role="paragraph", zone="references", text="① Circled entry. 2018."),
    ]
    secs = [{"id": "sec1", "heading": "References", "level": 1, "zone": "references", "block_id": "h",
             "page": 1, "parent": None, "children": [], "content": []}]
    _, _, nodes = _sem(blocks, sections=secs, pages_content=[(0, ["h", "r1", "r2", "r3", "r4"])])
    assert nodes["h"]["type"] == "heading"                     # the section heading is spared
    assert [nodes[i]["type"] for i in ("r1", "r2", "r3", "r4")] == ["reference"] * 4
    assert [nodes[i].get("marker") for i in ("r1", "r2", "r3", "r4")] == ["1", "2", "3", "①"]


def test_reference_without_a_marker_is_still_a_reference():
    blocks = [_blk("r", role="paragraph", zone="references", text="Author with no marker. 2020.")]
    _, _, nodes = _sem(blocks)
    assert nodes["r"]["type"] == "reference" and "marker" not in nodes["r"]


def test_body_zone_nodes_are_not_reference_nodes():
    _, _, nodes = _sem([_blk("p", role="paragraph", zone="body", text="1. Not a reference.")])
    assert nodes["p"]["type"] == "paragraph"


# ---- figure source unification ---------------------------------------------------------------------
def test_figure_source_unifies_three_origins():
    figs = [
        {"id": "p1_5", "role": "figure", "type": "figure", "zone": "body", "page": 1, "order": 1},
        {"id": "p1_vlm1", "role": "figure", "type": "figure", "zone": "body", "page": 1, "order": 2},
        {"id": "p1_vec0", "role": "figure", "type": "figure", "zone": "body", "page": 1, "order": 3, "source": "vector"},
    ]
    _, _, nodes = _sem([], figures=figs, pages_content=[(0, ["p1_5", "p1_vlm1", "p1_vec0"])])
    assert nodes["p1_5"]["source"] == "odl_image"
    assert nodes["p1_vlm1"]["source"] == "vlm"
    assert nodes["p1_vec0"]["source"] == "vector"


# ---- figure de-duplication (VLM dup of a raster figure) --------------------------------------------
def _fig(i, label=None, **kw):
    return {"id": i, "role": "figure", "type": "figure", "zone": "body", "page": kw.pop("page", 1),
            "order": kw.pop("order", 1), "label": label, **kw}


def test_vlm_figure_deduped_when_raster_shares_label():
    figs = [_fig("p5_205", "Fig 2", file="assets/p5_205.png"), _fig("p5_vlm1", "Fig 2", page=5)]
    _, _, nodes = _sem([], figures=figs, pages_content=[(0, ["p5_205", "p5_vlm1"])])
    assert "p5_205" in nodes and "p5_vlm1" not in nodes          # raster kept, VLM dup dropped
    assert sum(1 for n in nodes.values() if n.get("label") == "Fig 2") == 1


def test_vlm_only_figure_kept_when_label_is_unique():
    figs = [_fig("p2_10", "Fig 1", file="assets/p2_10.png"), _fig("p16_vlm7", "Fig 8", page=16)]
    _, _, nodes = _sem([], figures=figs, pages_content=[(0, ["p2_10", "p16_vlm7"])])
    assert "p16_vlm7" in nodes and nodes["p16_vlm7"]["source"] == "vlm"   # ODL missed it -> keep


def test_phantom_vlm_mention_on_another_page_is_deduped():
    # a VLM "Fig 2" on page 21 (a text mention) while the real raster Fig 2 is on page 5 -> dropped by label
    figs = [_fig("p5_205", "Fig 2", file="assets/p5_205.png"), _fig("p21_vlm8", "Fig 2", page=21)]
    _, _, nodes = _sem([], figures=figs, pages_content=[(0, ["p5_205", "p21_vlm8"])])
    assert "p21_vlm8" not in nodes


def test_dropped_vlm_description_is_grafted_onto_the_raster_figure():
    figs = [_fig("p7_238", "Fig 3", file="assets/p7_238.png"),
            _fig("p7_vlm2", "Fig 3", page=7, description="A bar chart of results.")]
    _, _, nodes = _sem([], figures=figs, pages_content=[(0, ["p7_238", "p7_vlm2"])])
    assert "p7_vlm2" not in nodes
    assert nodes["p7_238"]["description"] == "A bar chart of results."   # description preserved on raster


def test_unlabeled_vlm_figure_is_not_deduped():
    figs = [_fig("p1_5", file="assets/p1_5.png"), _fig("p1_vlm1", page=1)]   # both label=None
    _, _, nodes = _sem([], figures=figs, pages_content=[(0, ["p1_5", "p1_vlm1"])])
    assert "p1_vlm1" in nodes                                    # cannot dedup without a shared label


# ---- zones summary & metadata ----------------------------------------------------------------------
def test_zones_summary_orders_by_first_page():
    blocks = [{"id": "a", "zone": "cover", "page": 1}, {"id": "b", "zone": "body", "page": 2},
              {"id": "c", "zone": "references", "page": 5}, {"id": "d", "zone": "body", "page": 3}]
    z = _zones_summary(blocks, [], [])
    assert z == [{"zone": "cover", "pages": [1]}, {"zone": "body", "pages": [2, 3]},
                 {"zone": "references", "pages": [5]}]


def test_metadata_title_from_title_node_else_producer():
    doc, _, _ = _sem([_blk("t", role="title", text="The Title")])
    assert doc["metadata"]["title"] == "The Title"
    doc2, _, _ = _sem([_blk("p", role="paragraph")], meta={**_META, "producer": {"title": "ProdTitle"}})
    assert doc2["metadata"]["title"] == "ProdTitle"


def test_table_cell_bboxes_are_stripped_and_regions_demoted():
    tabs = [{"id": "tb", "role": "table", "type": "table", "zone": "body", "label": "T1",
             "n_rows": 1, "n_cols": 2, "views": {"md": "x"}, "order": 3,
             "cells": [[{"text": "a", "bbox": [0, 0, 1, 1]}, {"text": "b"}]],
             "regions": [{"page": 1, "bbox": [0, 0, 9, 9]}]}]
    doc, prov, nodes = _sem([], tables=tabs, pages_content=[(0, ["tb"])])
    assert nodes["tb"]["cells"] == [[{"text": "a"}, {"text": "b"}]]
    assert prov["tb"]["regions"] == [{"page": 1, "bbox": [0, 0, 9, 9]}] and prov["tb"]["order"] == 3
