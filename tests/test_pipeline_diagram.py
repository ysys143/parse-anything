from __future__ import annotations

from parse_anything.pipeline.diagram import build_diagram_graph


def _n(text, x0, y0, x1, y1, id=None):
    return {"text": text, "bbox": [x0, y0, x1, y1], "id": id}


def test_nodes_from_tokens_edges_from_connectors():
    nodes = [_n("검토", 0, 0, 20, 10, "a"), _n("승인", 0, 100, 20, 110, "b")]
    conn = [{"src_point": [10, 5], "dst_point": [10, 105]}]     # a -> b
    g = build_diagram_graph(nodes, conn)
    assert {n["id"] for n in g["nodes"]} == {"a", "b"}
    assert g["edges"] == [{"src": "a", "dst": "b"}]


def test_branch_condition_label_on_edge_is_consumed_once():
    # V4: one label near two connectors must tag only ONE edge (1:1 consume), not both
    nodes = [_n("질문", 0, 0, 20, 10, "q"), _n("승인", 0, 100, 20, 110, "p1"), _n("반려", 0, 200, 20, 210, "p2")]
    conns = [{"src_point": [10, 5], "dst_point": [10, 105]}, {"src_point": [10, 5], "dst_point": [10, 205]}]
    labels = [{"text": "아니오", "bbox": [12, 50, 30, 60]}]        # near the first connector's midpoint
    g = build_diagram_graph(nodes, conns, condition_labels=labels)
    tagged = [e for e in g["edges"] if e.get("label")]
    assert len(tagged) == 1 and tagged[0]["label"] == "아니오"


def test_v1_multiline_box_is_one_node_not_two():
    # a single box OCR'd as two stacked lines -> ONE clustered node, so the edge links the box
    nodes = [_n("재고", 0, 0, 20, 8, "box_top"), _n("확인", 0, 9, 20, 17, "box_bot"), _n("종료", 0, 200, 20, 210, "end")]
    g = build_diagram_graph(nodes, [{"src_point": [10, 8], "dst_point": [10, 205]}])
    box = [n for n in g["nodes"] if n["id"] == "box_top"]
    assert len(g["nodes"]) == 2 and box and box[0]["label"] == "재고 확인"    # merged label
    assert g["edges"] == [{"src": "box_top", "dst": "end"}]


def test_v3_boundary_distance_not_center_a_large_box_keeps_its_own_connector():
    # a connector entering the RIGHT EDGE of a large box A must resolve to A, not to a small box B whose
    # centre is nearer the entry point (center-distance bug).
    big = _n("공정 A", 0, 0, 200, 40, "A")          # wide box, centre x=100
    small = _n("B", 230, 0, 250, 20, "B")           # small neighbour, centre x=240
    src = _n("start", 0, 300, 20, 320, "S")
    g = build_diagram_graph([big, small, src], [{"src_point": [10, 310], "dst_point": [195, 20]}])
    assert g["edges"] == [{"src": "S", "dst": "A"}]   # 195,20 is inside A -> A, not B


def test_self_loop_and_missing_direction_are_dropped():
    nodes = [_n("A", 0, 0, 20, 10, "a")]
    assert build_diagram_graph(nodes, [{"src_point": [5, 5], "dst_point": [6, 6]}])["edges"] == []
    assert build_diagram_graph(nodes, [{}])["edges"] == []


def test_default_link_radius_bounds_a_far_endpoint():
    nodes = [_n("A", 0, 0, 20, 10, "a"), _n("B", 0, 100, 20, 110, "b")]
    conn = [{"src_point": [10, 5], "dst_point": [10, 5000]}]     # dst far from any node
    assert build_diagram_graph(nodes, conn)["edges"] == []                    # default radius -> dangling
    assert build_diagram_graph(nodes, conn, max_link_dist=1e9)["edges"] == [{"src": "a", "dst": "b"}]


def test_bbox_connector_is_flagged_ambiguous_direction():
    nodes = [_n("A", 0, 0, 20, 10, "a"), _n("B", 100, 100, 120, 110, "b")]
    g = build_diagram_graph(nodes, [{"bbox": [10, 5, 110, 105]}])
    assert g["edges"] == [{"src": "a", "dst": "b", "direction": "ambiguous"}]  # bbox has no real direction


def test_duplicate_unlabelled_edges_are_deduped():
    nodes = [_n("A", 0, 0, 20, 10, "a"), _n("B", 0, 100, 20, 110, "b")]
    conns = [{"src_point": [10, 5], "dst_point": [10, 105]}] * 2
    assert build_diagram_graph(nodes, conns)["edges"] == [{"src": "a", "dst": "b"}]


def test_empty_and_textless_tokens():
    assert build_diagram_graph([], [])["nodes"] == []
    assert build_diagram_graph([_n("   ", 0, 0, 10, 10)], [])["nodes"] == []
