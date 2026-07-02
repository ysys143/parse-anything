from __future__ import annotations

from odl_vl.pipeline.ontology import ChunkPolicy
from odl_vl.pipeline.output import _approx_tokens, _chunk_node_text, build_chunks


def _policy(child_tokens: int = 100) -> ChunkPolicy:
    return ChunkPolicy(child_tokens=child_tokens, tokenizer="test", parent="section",
                       keep_atomic=("table", "figure", "equation"))


def _sec(sid, heading, hid, content, parent=None, children=(), zone="body", level=1):
    return {"id": sid, "heading": heading, "level": level, "zone": zone, "heading_ref": hid,
            "parent": parent, "children": list(children), "content": list(content)}


def _chunks(nodes, sections, reading, prov=None, policy=None):
    sem = {"nodes": nodes, "sections": sections, "reading_order": reading}
    ch = build_chunks(sem, prov or {}, "doc", policy or _policy())
    return ch, [c for c in ch if c["level"] == "parent"], [c for c in ch if c["level"] == "child"]


# ---- token estimate & node text --------------------------------------------------------------------
def test_approx_tokens():
    assert _approx_tokens("한국어 문서") == 5                    # 5 CJK chars, no latin words
    assert _approx_tokens("hello world foo") == 4              # 3 words * 1.3 -> 4
    assert _approx_tokens("") == 0


def test_chunk_node_text_per_type():
    assert _chunk_node_text({"type": "paragraph", "text": "hi"}) == "hi"
    assert _chunk_node_text({"type": "equation", "latex": "x=1"}) == "x=1"
    assert _chunk_node_text({"type": "table", "label": "Table 1"}) == "[Table 1]"
    assert _chunk_node_text({"type": "figure", "label": "Fig 1", "caption": "a chart"}) == "[Fig 1] a chart"
    assert _chunk_node_text({"type": "figure"}) == "[Figure]"


# ---- parent/child structure ------------------------------------------------------------------------
def test_parent_per_section_with_breadcrumb_and_page_span():
    nodes = [{"id": "h", "type": "heading", "zone": "body", "text": "Intro"},
             {"id": "p1", "type": "paragraph", "zone": "body", "text": "first"},
             {"id": "p2", "type": "paragraph", "zone": "body", "text": "second"}]
    secs = [_sec("s1", "Intro", "h", ["p1", "p2"])]
    ch, parents, children = _chunks(nodes, secs, ["h", "p1", "p2"], {"h": {"page": 2}, "p1": {"page": 2}, "p2": {"page": 3}})
    assert len(parents) == 1 and parents[0]["structural_type"] == "section" and parents[0]["heading_path"] == ["Intro"]
    assert parents[0]["source_refs"]["pages"] == [2, 3] and parents[0]["source_refs"]["nodes"] == ["h", "p1", "p2"]
    assert len(children) == 1 and children[0]["parent_id"] == parents[0]["id"]
    assert children[0]["embedding_text"].startswith("Intro\n")     # breadcrumb prepended for embedding


def test_atomics_are_kept_whole_as_their_own_children():
    nodes = [{"id": "h", "type": "heading", "zone": "body", "text": "S"},
             {"id": "p", "type": "paragraph", "zone": "body", "text": "text"},
             {"id": "t", "type": "table", "zone": "body", "label": "T1"},
             {"id": "e", "type": "equation", "zone": "body", "latex": "x=1"},
             {"id": "f", "type": "figure", "zone": "body", "label": "F1"}]
    secs = [_sec("s1", "S", "h", ["p", "t", "e", "f"])]
    ch, parents, children = _chunks(nodes, secs, ["h", "p", "t", "e", "f"])
    by_type = {c["structural_type"]: c for c in children}
    assert by_type["table"]["source_refs"]["nodes"] == ["t"] and by_type["table"]["atomic"] is True
    assert by_type["equation"]["source_refs"]["nodes"] == ["e"] and by_type["equation"]["atomic"] is True
    assert by_type["figure"]["source_refs"]["nodes"] == ["f"] and by_type["figure"]["atomic"] is True
    atomics = ("table", "figure", "equation")
    assert all(len(c["source_refs"]["nodes"]) == 1 for c in children if c["structural_type"] in atomics)


def test_token_budget_splits_text_and_marks_continuation():
    nodes = [{"id": "h", "type": "heading", "zone": "body", "text": "S"},
             {"id": "p1", "type": "paragraph", "zone": "body", "text": "alpha beta gamma"},
             {"id": "p2", "type": "paragraph", "zone": "body", "text": "delta epsilon zeta"}]
    secs = [_sec("s1", "S", "h", ["p1", "p2"])]
    ch, parents, children = _chunks(nodes, secs, ["h", "p1", "p2"], policy=_policy(child_tokens=4))
    text_children = [c for c in children if c["structural_type"] == "text"]
    assert len(text_children) >= 2
    assert text_children[0]["is_continuation"] is False and text_children[-1]["is_continuation"] is True


def test_prev_next_links_children_in_reading_order():
    nodes = [{"id": "h", "type": "heading", "zone": "body", "text": "S"},
             {"id": "t", "type": "table", "zone": "body", "label": "T"},
             {"id": "e", "type": "equation", "zone": "body", "latex": "y"}]
    secs = [_sec("s1", "S", "h", ["t", "e"])]
    ch, parents, children = _chunks(nodes, secs, ["h", "t", "e"])
    # heading text child, then table, then equation -> a prev/next chain over the leaves
    ids = [c["id"] for c in children]
    assert children[0]["prev"] is None
    for a, b in zip(children, children[1:]):
        assert a["next"] == b["id"] and b["prev"] == a["id"]
    assert children[-1]["next"] is None and len(ids) == len(set(ids))


def test_nested_section_breadcrumb():
    nodes = [{"id": "h1", "type": "heading", "zone": "body", "text": "Chapter"},
             {"id": "h2", "type": "heading", "zone": "body", "text": "Section"},
             {"id": "p", "type": "paragraph", "zone": "body", "text": "body"}]
    secs = [_sec("s1", "Chapter", "h1", [], children=["s2"]),
            _sec("s2", "Section", "h2", ["p"], parent="s1", level=2)]
    ch, parents, children = _chunks(nodes, secs, ["h1", "h2", "p"])
    assert any(p["heading_path"] == ["Chapter", "Section"] for p in parents)   # full ancestry breadcrumb


# ---- fallbacks -------------------------------------------------------------------------------------
def test_orphan_nodes_group_into_page_parents():
    nodes = [{"id": "a", "type": "paragraph", "zone": "cover", "text": "cover"},
             {"id": "b", "type": "paragraph", "zone": "body", "text": "p2"}]
    ch, parents, children = _chunks(nodes, [], ["a", "b"], {"a": {"page": 1}, "b": {"page": 2}})
    assert len(parents) == 2 and all(p["structural_type"] == "page" for p in parents)  # no sections -> page parents
    assert [p["source_refs"]["pages"] for p in parents] == [[1, 1], [2, 2]]


def test_oversized_paragraph_splits_on_sentence_boundaries():
    long = "First sentence here. Second sentence follows on. Third one arrives now. Fourth is the last one."
    nodes = [{"id": "p", "type": "paragraph", "zone": "body", "text": long}]
    ch, parents, children = _chunks(nodes, [], ["p"], {"p": {"page": 1}}, _policy(child_tokens=4))
    assert len(children) >= 2 and all(c["source_refs"]["nodes"] == ["p"] for c in children)  # same node, sentence windows
    assert children[-1]["is_continuation"] is True


def test_empty_document_yields_no_chunks():
    assert build_chunks({"nodes": [], "sections": [], "reading_order": []}, {}, "d", _policy()) == []


def test_references_section_chunks_carry_reference_nodes():
    nodes = [{"id": "h", "type": "heading", "zone": "references", "text": "References"},
             {"id": "r1", "type": "reference", "zone": "references", "text": "[1] A. 2020", "marker": "1"},
             {"id": "r2", "type": "reference", "zone": "references", "text": "[2] B. 2019", "marker": "2"}]
    secs = [_sec("s1", "References", "h", ["r1", "r2"], zone="references")]
    ch, parents, children = _chunks(nodes, secs, ["h", "r1", "r2"])
    assert parents[0]["zone"] == "references"
    assert any("reference" in c["node_types"] for c in children)


def test_table_page_span_from_provenance_regions():
    nodes = [{"id": "t", "type": "table", "zone": "body", "label": "T"}]
    ch, parents, children = _chunks(nodes, [], ["t"], {"t": {"regions": [{"page": 4, "bbox": [0, 0, 1, 1]}]}})
    assert parents[0]["source_refs"]["pages"] == [4, 4]


def test_equation_node_page_is_derived_from_its_id():
    # a synthesised equation node (eq_pN_k) is not in provenance -> its page comes from the id
    nodes = [{"id": "eq_p5_0", "type": "equation", "zone": "body", "latex": "x=1", "display": True}]
    ch, parents, children = _chunks(nodes, [], ["eq_p5_0"], {})
    assert parents[0]["source_refs"]["pages"] == [5, 5]


def test_reading_order_ids_missing_from_nodes_are_skipped():
    nodes = [{"id": "p", "type": "paragraph", "zone": "body", "text": "hi"}]
    ch, parents, children = _chunks(nodes, [], ["ghost", "p", "also_gone"], {"p": {"page": 1}})
    assert len(parents) == 1 and parents[0]["source_refs"]["nodes"] == ["p"]   # stray reading-order ids ignored


def test_oversized_paragraph_leaves_a_trailing_window():
    # two long sentences then a short tail -> the tail flushes as a final (non-continuation-free) window
    text = "This first sentence is deliberately quite long indeed. Short tail."
    nodes = [{"id": "p", "type": "paragraph", "zone": "body", "text": text}]
    ch, parents, children = _chunks(nodes, [], ["p"], {"p": {"page": 1}}, _policy(child_tokens=6))
    assert len(children) >= 2 and children[-1]["display_text"].strip().endswith("Short tail.")


def test_breadcrumb_stops_at_a_broken_parent_chain():
    nodes = [{"id": "h", "type": "heading", "zone": "body", "text": "Orphaned"},
             {"id": "p", "type": "paragraph", "zone": "body", "text": "body"}]
    secs = [_sec("s2", "Orphaned", "h", ["p"], parent="missing")]   # parent id not in the section set
    ch, parents, children = _chunks(nodes, secs, ["h", "p"])
    assert parents[0]["heading_path"] == ["Orphaned"]             # chain stops at the missing parent
