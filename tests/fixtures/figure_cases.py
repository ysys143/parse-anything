"""Figure-detection fixtures -- diverse page geometries to test that ``vecfig._page_figures``
generalizes across document types instead of overfitting to one. Each case is bbox geometry in PDF
space (origin bottom-left): vector paths, ODL table regions, ODL text blocks, and the expected number
of detected figures. Add a new document type by appending a case here.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FigureCase:
    name: str
    paths: list[tuple]
    tables: list[tuple] = field(default_factory=list)
    text_blocks: list[tuple] = field(default_factory=list)
    width: float = 595.0
    height: float = 842.0
    expected: int = 0       # expected number of detected figure regions


def _packed(x0: float, y0: float, x1: float, y1: float, n: int) -> list[tuple]:
    """``n`` adjacent stroke boxes tiling ``[x0,y0,x1,y1]`` -- one dense cluster (a chart-like region)."""
    step = (x1 - x0) / n
    return [(x0 + i * step, y0, x0 + (i + 1) * step, y1) for i in range(n)]


FIGURE_CASES: list[FigureCase] = [
    # white-paper line/bar chart: a dense path cluster, no prose over it -> a figure
    FigureCase("dense_chart", _packed(100, 400, 500, 700, 20), expected=1),
    # same chart with a few short axis-label/legend blocks -> still a figure (labels cover a tiny slice)
    FigureCase("chart_with_sparse_axis_labels", _packed(100, 400, 500, 700, 20),
               text_blocks=[(90, 395, 150, 405), (90, 690, 115, 700), (120, 390, 480, 398)], expected=1),
    # academic page: section rules + underlines cluster, but two prose columns fill the bbox -> NOT a figure
    FigureCase("text_region_with_rules", _packed(80, 300, 520, 540, 12),
               text_blocks=[(80, 300, 300, 540), (305, 300, 520, 540)], expected=0),
    # a hairline rule / 9x12 icon -> below min area
    FigureCase("hairline_icon", _packed(40, 438, 49, 450, 8), expected=0),
    # a table's cell borders are paths too -> excluded by the table region
    FigureCase("table_grid", _packed(64, 325, 532, 425, 30), tables=[(64, 325, 532, 425)], expected=0),
]
