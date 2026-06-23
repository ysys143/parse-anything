from __future__ import annotations

from odl_vl.pipeline.triage import PageSignals, Route, TriagePolicy, decide_route


def test_no_text_layer_routes_to_scan():
    assert decide_route(PageSignals(text_chars=0, table_rows=0, image_count=1)) == Route.SCAN_VLM


def test_born_digital_table_routes_to_oracle_vlm():
    assert decide_route(PageSignals(text_chars=3000, table_rows=29, image_count=0)) == Route.ORACLE_VLM


def test_born_digital_figures_route_to_figure_vlm():
    assert decide_route(PageSignals(text_chars=500, table_rows=0, image_count=4)) == Route.FIGURE_VLM


def test_plain_prose_skips_vlm():
    assert decide_route(PageSignals(text_chars=2000, table_rows=0, image_count=0)) == Route.DETERMINISTIC


def test_scan_takes_precedence_over_table_signal():
    # No text layer wins even if a (spurious) table signal is present.
    assert decide_route(PageSignals(text_chars=5, table_rows=10, image_count=0)) == Route.SCAN_VLM


def test_policy_thresholds_are_tunable_not_hardcoded():
    s = PageSignals(text_chars=2000, table_rows=2, image_count=0)
    # default min_table_rows=3 -> not a table
    assert decide_route(s) == Route.DETERMINISTIC
    # a stricter domain policy that treats 2 rows as a table
    assert decide_route(s, TriagePolicy(min_table_rows=2)) == Route.ORACLE_VLM
