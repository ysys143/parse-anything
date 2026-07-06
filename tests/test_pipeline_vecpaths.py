from __future__ import annotations

from parse_anything.pipeline.vecpaths import _classify_polyline, _in_region, detect_connectors


def test_classify_polyline_connector_vs_box_vs_fill():
    line = [(0.0, 0.0), (100.0, 100.0)]
    rec = _classify_polyline(line, closed=False, stroked=True, filled=False)              # connector
    assert rec == {"bbox": [0, 0, 100, 100], "points": [[0.0, 0.0], [100.0, 100.0]]}
    assert _classify_polyline(line, closed=True, stroked=True, filled=False) is None    # closed -> box outline
    assert _classify_polyline(line, closed=False, stroked=False, filled=False) is None   # not stroked
    assert _classify_polyline(line, closed=False, stroked=True, filled=True) is None      # filled -> box/arrowhead
    assert _classify_polyline([(1.0, 1.0)], closed=False, stroked=True, filled=False) is None  # <2 points


def test_classify_polyline_keeps_real_terminals_not_bbox_corners():
    # an orthogonal (L-shaped) anti-diagonal connector: its true endpoints are OFF the bbox main diagonal,
    # so `points` must carry the actual first/last polyline points, not [min]/[max] corners.
    l_shape = [(20.0, 180.0), (20.0, 20.0), (180.0, 20.0)]                 # top-left -> corner -> bottom-right
    rec = _classify_polyline(l_shape, closed=False, stroked=True, filled=False)
    assert rec["bbox"] == [20, 20, 180, 180]                              # bbox is the enclosing rect (region use)
    assert rec["points"] == [[20.0, 180.0], [180.0, 20.0]]                # real terminals, NOT (20,20)/(180,180)


def test_in_region_by_centre():
    assert _in_region([10, 10, 20, 20], [0, 0, 100, 100])
    assert not _in_region([200, 200, 210, 210], [0, 0, 100, 100])


def _make_pdf(stream: str) -> bytes:
    body = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 300]/Contents 4 0 R/Resources<<>>>>",
        b"<</Length %d>>stream\n%s\nendstream" % (len(stream.encode()), stream.encode()),
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, b in enumerate(body, 1):
        offsets.append(len(out))
        out += b"%d 0 obj" % i + b + b"endobj\n"
    xref_off = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(body) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF" % (len(body) + 1, xref_off)
    return out


def test_detect_connectors_keeps_open_line_drops_closed_box(tmp_path):
    # a stroked open line (m..l S) is a connector; a stroked rectangle (re S) is a closed box -> excluded
    pdf = tmp_path / "diagram.pdf"
    pdf.write_bytes(_make_pdf("2 w\n50 50 m 250 250 l S\n100 100 80 80 re S"))
    conns = detect_connectors(str(pdf), 0, [0, 0, 300, 300])
    assert len(conns) == 1                                   # only the open line
    x0, y0, x1, y1 = conns[0]["bbox"]
    assert (x0, y0, x1, y1) == (50.0, 50.0, 250.0, 250.0)    # the line's extent


def test_detect_connectors_region_filter(tmp_path):
    pdf = tmp_path / "diagram.pdf"
    pdf.write_bytes(_make_pdf("2 w\n50 50 m 250 250 l S"))
    assert detect_connectors(str(pdf), 0, [0, 0, 10, 10]) == []   # line's centre outside the region


def _diagram_figure():
    # two node boxes (chart_data) whose centres sit on the endpoints of the drawn connector line
    return {"source": "vector", "kind": "diagram", "page": 1, "bbox": [0, 0, 300, 300],
            "chart_data": [{"text": "A", "bbox": [40, 40, 80, 80]},
                           {"text": "B", "bbox": [220, 220, 260, 260]}]}


def test_attach_diagram_graphs_links_nodes_via_connector(tmp_path):
    # B4 wiring end-to-end: a diagram figure + a real stroked connector -> a graph with an ambiguous edge
    from parse_anything.pipeline.output import _attach_diagram_graphs
    pdf = tmp_path / "diagram.pdf"
    pdf.write_bytes(_make_pdf("2 w\n60 60 m 240 240 l S"))   # line from box A's centre to box B's
    fig = _diagram_figure()
    _attach_diagram_graphs([fig], str(pdf))
    g = fig["diagram_graph"]
    assert {n["label"] for n in g["nodes"]} == {"A", "B"}
    assert len(g["edges"]) == 1 and g["edges"][0]["direction"] == "ambiguous"


def test_attach_diagram_graphs_skips_chart_kind(tmp_path):
    # negative control: a CHART figure is never turned into a relation graph, even with a connector present
    from parse_anything.pipeline.output import _attach_diagram_graphs
    pdf = tmp_path / "chart.pdf"
    pdf.write_bytes(_make_pdf("2 w\n60 60 m 240 240 l S"))
    fig = _diagram_figure()
    fig["kind"] = "chart"
    _attach_diagram_graphs([fig], str(pdf))
    assert "diagram_graph" not in fig


def test_attach_diagram_graphs_no_connectors_no_graph(tmp_path):
    # a diagram with node labels but NO drawn links -> no edges -> no graph emitted (not an empty stub)
    from parse_anything.pipeline.output import _attach_diagram_graphs
    pdf = tmp_path / "empty.pdf"
    pdf.write_bytes(_make_pdf("100 100 80 80 re S"))   # only a closed box outline -> no connector
    fig = _diagram_figure()
    _attach_diagram_graphs([fig], str(pdf))
    assert "diagram_graph" not in fig


def test_attach_diagram_graphs_links_via_orthogonal_connector(tmp_path):
    # regression for the L-connector bug: an orthogonal anti-diagonal link must join the two REAL nodes it
    # touches (top-left box + bottom-right box), not phantom bbox corners. Nodes sit at the true terminals.
    from parse_anything.pipeline.output import _attach_diagram_graphs
    pdf = tmp_path / "ortho.pdf"
    pdf.write_bytes(_make_pdf("2 w\n40 260 m 40 40 l 260 40 l S"))   # (40,260)->(40,40)->(260,40): L-shape
    fig = {"source": "vector", "kind": "diagram", "page": 1, "bbox": [0, 0, 300, 300],
           "chart_data": [{"text": "TL", "bbox": [20, 240, 60, 280]},    # centre (40,260) = one terminal
                          {"text": "BR", "bbox": [240, 20, 280, 60]}]}    # centre (260,40) = other terminal
    _attach_diagram_graphs([fig], str(pdf))
    g = fig["diagram_graph"]
    assert {n["label"] for n in g["nodes"]} == {"TL", "BR"}
    assert len(g["edges"]) == 1 and g["edges"][0]["direction"] == "ambiguous"   # linked despite the bend


def test_attach_diagram_graphs_skips_low_confidence_diagram(tmp_path):
    # a LOW-confidence diagram call (classifier's own "don't trust me") must NOT be materialized into a
    # graph -- otherwise a misclassified chart's plot lines become fabricated connectors.
    from parse_anything.pipeline.output import _attach_diagram_graphs
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(_make_pdf("2 w\n60 60 m 240 240 l S"))
    fig = _diagram_figure()
    fig["kind_confidence"] = "low"
    _attach_diagram_graphs([fig], str(pdf))
    assert "diagram_graph" not in fig


def test_detect_connectors_out_of_range_page_is_empty_not_crash(tmp_path):
    # an ODL/pdfium page-count mismatch must yield [] (best-effort), never abort the export
    pdf = tmp_path / "one.pdf"
    pdf.write_bytes(_make_pdf("2 w\n50 50 m 250 250 l S"))
    assert detect_connectors(str(pdf), 5, [0, 0, 300, 300]) == []   # page 5 doesn't exist -> []
