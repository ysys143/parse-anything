#!/usr/bin/env python3
"""TEDS (Tree-Edit-Distance-based Similarity) for HTML tables -- canonical PubTabNet formulation.

TEDS(a,b) = 1 - EditDistance(T_a, T_b) / max(|T_a|, |T_b|), where T is the table's DOM tree and
node rename cost for two <td>/<th> cells is the normalized edit distance of their text content.
Score in [0,1]; 1 = identical structure AND content. Unlike flat char_sim, TEDS SEES rows/columns/
spans/cell alignment -- exactly the born-digital table-structure fidelity a text metric is blind to.

Requires apted + lxml (uv pip install apted lxml). This is the standard metric used by PubTabNet /
OmniDocBench, vendored here so the three-way table comparison uses the same yardstick as the field.
"""
from __future__ import annotations

from collections import deque

from apted import APTED, Config
from apted.helpers import Tree
from lxml import html


class TableTree(Tree):
    def __init__(self, tag, colspan=None, rowspan=None, content=None, *children):
        self.tag = tag
        self.colspan = colspan
        self.rowspan = rowspan
        self.content = content
        self.children = list(children)

    def bracket(self) -> str:
        if self.tag in ("td", "th"):
            r = f'"tag": {self.tag}, "colspan": {self.colspan}, "rowspan": {self.rowspan}, "text": {self.content}'
        else:
            r = f'"tag": {self.tag}'
        for c in self.children:
            r += c.bracket()
        return "{{{}}}".format(r)


def _edit_ratio(a, b) -> float:
    """Normalized Levenshtein distance in [0,1] between two token lists (cell text as chars)."""
    import difflib
    a = a or []
    b = b or []
    if not a and not b:
        return 0.0
    sa, sb = "".join(a), "".join(b)
    if not sa and not sb:
        return 0.0
    return 1.0 - difflib.SequenceMatcher(None, sa, sb).ratio()


class TableConfig(Config):
    def rename(self, node1, node2):
        if (node1.tag != node2.tag or node1.colspan != node2.colspan
                or node1.rowspan != node2.rowspan):
            return 1.0
        if node1.tag in ("td", "th"):
            return _edit_ratio(node1.content, node2.content)
        return 0.0

    def children(self, node):
        return getattr(node, "children", [])


def _build_tree(node) -> TableTree:
    """lxml element -> TableTree. Keeps only structural tags (table/thead/tbody/tr/td/th)."""
    if node.tag in ("td", "th"):
        cell = TableTree(node.tag,
                         int(node.get("colspan", "1")),
                         int(node.get("rowspan", "1")),
                         list("".join(node.itertext()).strip()))
        return cell
    t = TableTree(node.tag, None, None, None)
    for c in node:
        if c.tag in ("table", "thead", "tbody", "tr", "td", "th"):
            t.children.append(_build_tree(c))
    return t


def _first_table(html_str: str):
    try:
        doc = html.fromstring(html_str)
    except Exception:
        return None
    tables = doc.xpath("//table")
    if not tables:
        return doc if doc.tag == "table" else None
    return tables[0]


def teds(pred_html: str, true_html: str) -> float:
    """TEDS between two HTML fragments (uses their first <table>). 0 if pred has no table."""
    tt = _first_table(true_html)
    if tt is None:
        return 0.0
    pt = _first_table(pred_html)
    true_tree = _build_tree(tt)
    n_true = _count(true_tree)
    if pt is None:
        return 0.0                      # predicted nothing table-shaped -> full miss
    pred_tree = _build_tree(pt)
    n_pred = _count(pred_tree)
    dist = APTED(pred_tree, true_tree, TableConfig()).compute_edit_distance()
    denom = max(n_pred, n_true)
    return 1.0 - dist / denom if denom else 1.0


def _count(tree: TableTree) -> int:
    n, q = 0, deque([tree])
    while q:
        node = q.popleft()
        n += 1
        q.extend(node.children)
    return n


if __name__ == "__main__":  # self-test
    a = "<table><tr><td>1</td><td>2</td></tr><tr><td>3</td><td>4</td></tr></table>"
    b = "<table><tr><td>1</td><td>2</td></tr><tr><td>3</td><td>5</td></tr></table>"  # one cell differs
    c = "<table><tr><td>1 2</td></tr></table>"                                      # structure collapsed
    print(f"identical : {teds(a, a):.3f}  (expect 1.000)")
    print(f"1 cell diff: {teds(b, a):.3f}  (expect ~0.9)")
    print(f"collapsed  : {teds(c, a):.3f}  (expect low)")
    print(f"no table   : {teds('plain text', a):.3f}  (expect 0.000)")
