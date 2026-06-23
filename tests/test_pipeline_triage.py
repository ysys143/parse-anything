from __future__ import annotations

from odl_vl.pipeline.triage import PageSignals, Route, TriagePolicy, decide_route


def test_no_text_layer_routes_to_scan():
    assert decide_route(PageSignals(text_chars=0, table_rows=0, image_count=1)) == Route.SCAN_VLM


def test_born_digital_table_routes_to_table_vlm():
    assert decide_route(PageSignals(text_chars=3000, table_rows=29, image_count=0)) == Route.TABLE_VLM


def test_born_digital_figures_route_to_figure_vlm():
    assert decide_route(PageSignals(text_chars=500, table_rows=0, image_count=4)) == Route.FIGURE_VLM


def test_plain_prose_skips_vlm():
    assert decide_route(PageSignals(text_chars=2000, table_rows=0, image_count=0)) == Route.DETERMINISTIC


def test_scan_takes_precedence_over_table_signal():
    # No text layer wins even if a (spurious) table signal is present.
    assert decide_route(PageSignals(text_chars=5, table_rows=10, image_count=0)) == Route.SCAN_VLM


def test_vector_figure_routes_to_figure_vlm_over_table():
    # real-corpus case: a multi-panel plot page has a figure caption and hundreds of path
    # objects, and its plot grid spuriously trips the table detector. It must go to FIGURE_VLM
    # (not TABLE_VLM) so the numeric oracle is not applied to axis ticks.
    s = PageSignals(text_chars=3000, table_rows=4, image_count=0, vector_paths=585, figure_caption=True)
    assert decide_route(s) == Route.FIGURE_VLM


def test_heavy_vector_without_caption_still_routes_to_figure_vlm():
    s = PageSignals(text_chars=500, table_rows=0, image_count=0, vector_paths=300)
    assert decide_route(s) == Route.FIGURE_VLM


def test_real_table_without_figure_caption_stays_table_vlm():
    # a bordered data table has paths from cell borders but no figure caption -> keep the oracle
    s = PageSignals(text_chars=3000, table_rows=29, image_count=0, vector_paths=120, figure_caption=False)
    assert decide_route(s) == Route.TABLE_VLM


def test_prose_page_merely_citing_a_figure_is_not_figure_vlm():
    # "see Fig. 12" on a text page (low path count) must not route to FIGURE_VLM
    s = PageSignals(text_chars=3000, table_rows=0, image_count=0, vector_paths=5, figure_caption=True)
    assert decide_route(s) == Route.DETERMINISTIC


def test_policy_thresholds_are_tunable_not_hardcoded():
    s = PageSignals(text_chars=2000, table_rows=2, image_count=0)
    # default min_table_rows=3 -> not a table
    assert decide_route(s) == Route.DETERMINISTIC
    # a stricter domain policy that treats 2 rows as a table
    assert decide_route(s, TriagePolicy(min_table_rows=2)) == Route.TABLE_VLM
