from __future__ import annotations

from odl_vl.export import (
    CHUNK_CONTRACT,
    STRUCTURE_CONTRACT,
    Block,
    ChunkRecord,
    Figure,
    PageEntry,
    RoleAssignment,
    Section,
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
