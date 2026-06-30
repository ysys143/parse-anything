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


def test_in_table_excludes_paths_inside_a_table_region():
    table = (50.0, 50.0, 150.0, 150.0)
    assert _in_table((90.0, 90.0, 110.0, 110.0), [table])       # center inside the table
    assert not _in_table((0.0, 0.0, 10.0, 10.0), [table])       # well outside
    assert not _in_table((90.0, 90.0, 110.0, 110.0), [])        # no tables -> never excluded
