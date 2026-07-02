from __future__ import annotations

from odl_vl.export import (
    CHUNK_CONTRACT,
    PROVENANCE_CONTRACT,
    SEMANTIC_CONTRACT,
    STRUCTURE_CONTRACT,
    Block,
    ChunkRecord,
    Figure,
    PageEntry,
    Provenance,
    RoleAssignment,
    Section,
    SemanticView,
    StructureExport,
    Table,
    check_compatible,
    contract_tag,
)
from odl_vl.export.contracts import Cell, Region


def _structure() -> StructureExport:
    return StructureExport(
        document={"document_id": "abc123", "mode": "det_vlm"},
        ontology={"profile": "paper", "version": 1},
        pages=[PageEntry(page_index=0, page_number=1, mode="det_vlm", used_vlm=True,
                         flags=[], content=["p1_b0", "p1_t0"], blocks=["p1_b0"], tables=["p1_t0"])],
        sections=[Section(id="sec1", heading="1 Intro", level=1, block_id="p1_b0", content=["p1_b1"])],
        blocks=[Block(id="p1_b0", type="paragraph", page=1, order=0, bbox=[0, 0, 10, 10], text="Intro")],
        tables=[Table(id="p1_t0", pages=[1], order=1, n_rows=1, n_cols=2,
                      cells=[[Cell("a"), Cell("b", bbox=[0, 0, 1, 1])]],
                      regions=[Region(page=1, bbox=[0, 0, 5, 5])])],
        figures=[Figure(id="p1_f0", page=1, order=2, bbox=[0, 0, 3, 3], file="assets/p1_f0.png")],
        roles={"sec1": RoleAssignment(role="body.section", confidence=0.9, by="signal:heading_regex")},
    )


def test_contract_tags_are_stamped():
    payload = _structure().to_dict()
    assert payload["contract"] == contract_tag(STRUCTURE_CONTRACT)
    assert payload["contract"]["name"] == "odl-vl.structure"


def test_structure_round_trip_is_lossless():
    exp = _structure()
    back = StructureExport.from_dict(exp.to_dict())
    assert back.to_dict() == exp.to_dict()


def test_compact_omits_none_optionals():
    d = Block(id="b", type="paragraph", page=1, order=0, bbox=[0, 0, 1, 1], text="x").to_dict()
    assert "font_size" not in d and "section" not in d and "refs" not in d


def test_roles_overlay_is_separate_from_nodes():
    # Layer 1 must not be inlined onto Layer 0 nodes (design §1 non-destructive overlay).
    payload = _structure().to_dict()
    assert "role" not in payload["blocks"][0]
    assert payload["roles"]["sec1"]["role"] == "body.section"


def test_from_dict_ignores_unknown_keys_forward_compat():
    # A newer producer adds a field; an older consumer must not break.
    raw = {"id": "b", "type": "paragraph", "page": 1, "order": 0, "bbox": [0, 0, 1, 1],
           "text": "x", "future_field": {"anything": 1}}
    b = Block.from_dict(raw)
    assert b.id == "b" and not hasattr(b, "future_field")


def test_check_compatible_matches_major_only():
    assert check_compatible({"name": "odl-vl.structure", "version": "1.0"}, STRUCTURE_CONTRACT)
    assert check_compatible({"name": "odl-vl.structure", "version": "1.7"}, STRUCTURE_CONTRACT)  # minor ok
    assert not check_compatible({"name": "odl-vl.structure", "version": "2.0"}, STRUCTURE_CONTRACT)
    assert not check_compatible({"name": "odl-vl.chunks", "version": "1.0"}, STRUCTURE_CONTRACT)
    assert not check_compatible(None, STRUCTURE_CONTRACT)


def test_chunk_record_round_trip_and_compaction():
    c = ChunkRecord(id="c1", doc_id="abc123", structural_type="table", text="| a | b |",
                    token_count=12, atomic=True, parent_id="c0", role="body.result_table",
                    heading_path=["3 Results"], source_refs={"nodes": ["p5_t2"], "pages": [5]},
                    meta={"n_rows": 3})
    d = c.to_dict()
    assert d["atomic"] is True and d["source_refs"]["nodes"] == ["p5_t2"]
    assert ChunkRecord.from_dict(d).to_dict() == d
    bare = ChunkRecord(id="c2", doc_id="abc", structural_type="block", text="x", token_count=1).to_dict()
    assert "refs" not in bare and "meta" not in bare and "heading_path" not in bare  # empties omitted


def test_chunk_contract_distinct_from_structure():
    assert CHUNK_CONTRACT[0] == "odl-vl.chunks" and STRUCTURE_CONTRACT[0] == "odl-vl.structure"


# ---- v1.1 additions: parent/child chunk model, SemanticView, Provenance -----------------------------


def test_chunk_record_parent_child_small_to_big_round_trip():
    parent = ChunkRecord(id="c0001p", doc_id="d", structural_type="section", level="parent",
                         zone="body", heading_path=["1 Intro"], display_text="Intro\nbody",
                         children=["c0001_1", "c0001_2"], token_count=3, tokenizer="test",
                         source_refs={"nodes": ["h", "p", "t"], "pages": [1, 2]}).to_dict()
    child = ChunkRecord(id="c0001_2", doc_id="d", structural_type="table", level="child", atomic=True,
                        parent_id="c0001p", zone="body", heading_path=["1 Intro"], display_text="[T1]",
                        embedding_text="1 Intro\n[T1]", prev="c0001_1", next=None, token_count=1,
                        tokenizer="test", node_types=["table"],
                        source_refs={"nodes": ["t"], "pages": [2, 2]}).to_dict()
    assert parent["level"] == "parent" and parent["children"] == ["c0001_1", "c0001_2"]
    assert parent["source_refs"]["pages"] == [1, 2]
    assert child["level"] == "child" and child["atomic"] is True and child["parent_id"] == "c0001p"
    assert child["embedding_text"].startswith("1 Intro\n")
    assert ChunkRecord.from_dict(parent).to_dict() == parent      # round-trip is lossless + idempotent
    assert ChunkRecord.from_dict(child).to_dict() == child


def test_chunk_contract_is_minor_bumped_and_still_major_1():
    assert CHUNK_CONTRACT[1] == "1.1"
    assert check_compatible({"name": "odl-vl.chunks", "version": "1.0"}, CHUNK_CONTRACT)   # old consumer ok


def _semantic() -> SemanticView:
    return SemanticView(
        document={"document_id": "abc123", "content_sha256": "abc123ff", "n_pages": 2, "mode": "det_vlm"},
        context={"doco": "http://purl.org/spar/doco/"},
        profile={"id": "odl:ontology/paper", "version": "1.0.0"},
        metadata={"title": "A Paper"},
        zones=[{"zone": "body", "pages": [1, 2]}],
        sections=[{"id": "s1", "heading": "1 Intro", "level": 1, "heading_ref": "h", "children": [], "content": ["p"]}],
        nodes=[{"id": "h", "type": "heading", "zone": "body", "text": "1 Intro", "level": 1},
               {"id": "p", "type": "paragraph", "zone": "body", "text": "body"}],
        reading_order=["h", "p"],
    )


def test_semantic_view_stamps_contract_and_spreads_identity():
    d = _semantic().to_dict()
    assert d["contract"] == contract_tag(SEMANTIC_CONTRACT)
    assert d["document_id"] == "abc123" and d["n_pages"] == 2      # identity spread to top level (flat, like Layer 0)
    assert d["@context"]["doco"].endswith("/doco/")
    assert d["nodes"][0]["id"] == "h" and "bbox" not in d["nodes"][0]   # geometry-free projection


def test_semantic_view_round_trip_is_lossless():
    exp = _semantic()
    assert SemanticView.from_dict(exp.to_dict()).to_dict() == exp.to_dict()


def test_provenance_stamps_contract_and_joins_by_node_id():
    prov = Provenance(prov={"h": {"page": 1, "bbox": [0, 0, 10, 10], "order": 0},
                            "p": {"page": 1, "bbox": [0, 20, 10, 30], "font_size": 11.0}},
                      profile={"id": "odl:ontology/paper"})
    d = prov.to_dict()
    assert d["contract"] == contract_tag(PROVENANCE_CONTRACT)
    assert set(d["prov"]) == {"h", "p"} and d["prov"]["h"]["bbox"] == [0, 0, 10, 10]
    assert Provenance.from_dict(d).to_dict() == d                  # round-trip (contract tag ignored on read)


def test_structure_export_v1_1_carries_context_and_zones():
    exp = StructureExport(document={"document_id": "x"},
                          context={"doco": "http://purl.org/spar/doco/"},
                          zones=[{"zone": "references", "pages": [9, 10]}])
    d = exp.to_dict()
    assert d["contract"]["version"] == "1.1"
    assert d["@context"]["doco"].endswith("/doco/") and d["zones"][0]["zone"] == "references"
    assert StructureExport.from_dict(d).to_dict() == d
