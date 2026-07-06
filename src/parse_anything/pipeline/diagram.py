"""Deterministic diagram / flowchart relation graph (FR-5.3 / FR-5.4).

Builds ``{nodes, edges}`` from a diagram's parts. NODES are its text boxes -- tokens are first CLUSTERED
by bbox proximity so a multi-line box label is ONE node, not one per line (adversarial review V1). EDGES
come from CONNECTOR geometry: each connector links the node nearest its start point to the node nearest
its end point, using point-to-box-BOUNDARY distance (V3) and a finite link radius so a far endpoint stays
dangling rather than snapping to a random node. A short label near a connector's midpoint becomes the
edge's branch condition (예/아니오/…, FR-5.4), consumed 1:1 so one label can't tag every edge (V4).
Values are quoted, never generated (§5-C).

SCOPE (honest): this consumes connector geometry; it does NOT detect arrows from raster pixels, and it
cannot verify arrowhead direction. Supply connectors as ``{"src_point":[x,y], "dst_point":[x,y]}``
(direction = src->dst, trusted from the caller). A ``{"bbox":[…]}`` connector has NO reliable direction,
so its edge is flagged ``direction:"ambiguous"`` (V2). Extracting connectors + arrowheads from vector
paths is the caller's job and is not yet wired (backlog B4b) -- until then this is an assembly primitive.
"""
from __future__ import annotations

import math
from collections import defaultdict


def _text(tok: dict) -> str:
    return (tok.get("label") or tok.get("text") or "").strip()


def _dist(point: list[float], bbox: list[float]) -> float:
    """Point to the NEAREST POINT of bbox (0 when inside) -- not to its centre, so a connector entering a
    large box is not stolen by a small neighbour whose centre happens to be closer (V3)."""
    dx = max(bbox[0] - point[0], 0.0, point[0] - bbox[2])
    dy = max(bbox[1] - point[1], 0.0, point[1] - bbox[3])
    return math.hypot(dx, dy)


def _nearest(point: list[float], items: list[dict], max_dist: float) -> "dict | None":
    best, best_d = None, math.inf
    for it in items:
        d = _dist(point, it["bbox"])
        if d < best_d:
            best, best_d = it, d
    return best if best is not None and best_d <= max_dist else None


def _cluster_nodes(tokens: list[dict], gap: "float | None") -> list[dict]:
    """Union tokens whose bboxes overlap or sit within ``gap`` (default: 0.6x median token height, so
    stacked lines in ONE box merge but separate boxes stay apart) into a single node."""
    toks = [t for t in tokens if _text(t)]
    if not toks:
        return []
    heights = sorted(t["bbox"][3] - t["bbox"][1] for t in toks)
    span: float = gap if gap is not None else 0.6 * heights[len(heights) // 2]
    parent = list(range(len(toks)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def near(a: list[float], b: list[float]) -> bool:
        return (a[0] <= b[2] + span and b[0] <= a[2] + span) and (a[1] <= b[3] + span and b[1] <= a[3] + span)

    for i in range(len(toks)):
        for j in range(i + 1, len(toks)):
            if near(toks[i]["bbox"], toks[j]["bbox"]):
                parent[find(i)] = find(j)

    groups: dict[int, list[dict]] = defaultdict(list)
    for i, t in enumerate(toks):
        groups[find(i)].append(t)
    nodes: list[dict] = []
    for g, members in groups.items():
        members.sort(key=lambda t: (t["bbox"][1], t["bbox"][0]))  # reading order within the box
        bb = [min(m["bbox"][0] for m in members), min(m["bbox"][1] for m in members),
              max(m["bbox"][2] for m in members), max(m["bbox"][3] for m in members)]
        nid = next((m["id"] for m in members if m.get("id")), None) or f"n{g}"
        nodes.append({"id": nid, "label": " ".join(_text(m) for m in members), "bbox": bb})
    return nodes


def _default_radius(nodes: list[dict]) -> float:
    diags = sorted(math.hypot(n["bbox"][2] - n["bbox"][0], n["bbox"][3] - n["bbox"][1]) for n in nodes)
    return 3.0 * diags[len(diags) // 2] if diags else math.inf


def build_diagram_graph(tokens: list[dict], connectors: "list[dict] | None" = None, *,
                        condition_labels: "list[dict] | None" = None,
                        max_link_dist: "float | None" = None, cluster_gap: "float | None" = None) -> dict:
    """``tokens``: node text ``[{text|label, bbox, id?}]`` (clustered into boxes). ``connectors``:
    ``[{src_point,dst_point}|{bbox}]``. ``condition_labels``: ``[{text, bbox}]``. ``max_link_dist``: link
    radius (default derived from node size) beyond which a connector end is dangling. Returns
    ``{"nodes":[…], "edges":[{src,dst,label?,direction?}]}``."""
    nodes = _cluster_nodes(tokens, cluster_gap)
    radius = max_link_dist if max_link_dist is not None else _default_radius(nodes)
    labels = list(condition_labels or [])
    used_labels: set[int] = set()
    edges: list[dict] = []
    seen: set[tuple] = set()
    for c in connectors or []:
        sp, dp = c.get("src_point"), c.get("dst_point")
        if sp is not None and dp is not None:
            ambiguous = False                          # explicit endpoints = caller-trusted direction
        elif c.get("points"):                          # real polyline terminals, but NO reliable direction
            pts = c["points"]                          # (used by vecpaths: link by true endpoints, not bbox
            sp, dp = pts[0], pts[-1]                    #  corners -- an L-connector's terminals are off-diagonal)
            ambiguous = True
        else:
            bx = c.get("bbox")
            if not bx:
                continue
            sp, dp = [bx[0], bx[1]], [bx[2], bx[3]]     # no reliable direction (fallback: bbox diagonal)
            ambiguous = True
        s = _nearest(sp, nodes, radius)
        d = _nearest(dp, nodes, radius)
        if s is None or d is None or s is d:            # dangling end or self-loop -> not an edge
            continue
        edge = {"src": s["id"], "dst": d["id"]}
        if ambiguous:
            edge["direction"] = "ambiguous"
        if labels:                                      # nearest UNUSED condition label within radius (1:1)
            mid = [(sp[0] + dp[0]) / 2, (sp[1] + dp[1]) / 2]
            free = [cl for k, cl in enumerate(labels) if k not in used_labels]
            lab = _nearest(mid, free, radius)
            if lab is not None and (lab.get("text") or "").strip():
                edge["label"] = lab["text"].strip()
                used_labels.add(labels.index(lab))
        key = (edge["src"], edge["dst"], edge.get("label"))
        if key in seen:                                 # drop a fully-duplicate unlabelled/labelled edge (V5)
            continue
        seen.add(key)
        edges.append(edge)
    return {"nodes": nodes, "edges": edges}
