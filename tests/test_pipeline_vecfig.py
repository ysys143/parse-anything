from __future__ import annotations

import pytest

from fixtures.figure_cases import FIGURE_CASES
from odl_vl.pipeline.vecfig import _cluster, _in_table, _page_figures


@pytest.mark.parametrize("case", FIGURE_CASES, ids=lambda c: c.name)
def test_figure_detection_generalizes_across_doc_types(case):
    figs = _page_figures(case.paths, case.tables, case.text_blocks, width=case.width, height=case.height)
    assert len(figs) == case.expected, f"{case.name}: got {figs}"


def test_cluster_groups_nearby_paths_and_separates_distant_ones():
    boxes = [(0.0, 0.0, 10.0, 10.0), (11.0, 0.0, 20.0, 10.0),  # gap 1 -> same cluster
             (300.0, 300.0, 310.0, 310.0)]                      # far away -> its own cluster
    sizes = sorted(len(c) for c in _cluster(boxes, gap=5.0))
    assert sizes == [1, 2]


def test_cluster_gap_controls_grouping():
    boxes = [(0.0, 0.0, 10.0, 10.0), (25.0, 0.0, 35.0, 10.0)]   # 15 apart
    assert len(_cluster(boxes, gap=5.0)) == 2     # gap too small to bridge
    assert len(_cluster(boxes, gap=20.0)) == 1    # gap bridges them


def test_page_sized_cluster_is_a_background_not_a_chart():
    # a vector cluster covering ~the whole page is a slide / page background (its decorative paths),
    # not a chart. Detecting it as a figure would crop the whole slide and suppress all its text as
    # 'chart-internal'. Reject it; a normal chart region (a fraction of the page) is still detected.
    page_bg = [(0.0, 0.0, 960.0, 540.0)] * 10                    # 10 paths spanning the full slide
    assert _page_figures(page_bg, [], [], width=960.0, height=540.0) == []
    chart = [(100.0, 100.0, 400.0, 350.0)] * 10                  # ~24% of the page -> a real chart
    assert len(_page_figures(chart, [], [], width=960.0, height=540.0)) == 1


def test_in_table_excludes_paths_inside_a_table_region():
    table = (50.0, 50.0, 150.0, 150.0)
    assert _in_table((90.0, 90.0, 110.0, 110.0), [table])       # center inside the table
    assert not _in_table((0.0, 0.0, 10.0, 10.0), [table])       # well outside
    assert not _in_table((90.0, 90.0, 110.0, 110.0), [])        # no tables -> never excluded
