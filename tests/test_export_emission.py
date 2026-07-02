"""Schema-regression: the pipeline's emitted artifacts ARE the export contracts (integration-plan §5/§8).

``write_outputs`` serializes document.semantic.json / document.provenance.json / document.chunks.jsonl
THROUGH SemanticView/Provenance/ChunkRecord, so reading a file back and re-serializing must be a no-op
(``Contract.from_dict(read).to_dict() == read``). document.json (Layer 0) must stay byte-compatible: no
role/zone/heading_level/odl_role inlined on nodes, with the role overlay + zones lifted to the top level.
"""
from __future__ import annotations

import json

from odl_vl.export import (
    PROVENANCE_CONTRACT,
    SEMANTIC_CONTRACT,
    STRUCTURE_CONTRACT,
    ChunkRecord,
    Provenance,
    SemanticView,
    StructureExport,
    contract_tag,
)
from odl_vl.pipeline.docmeta import DocumentMeta
from odl_vl.pipeline.odl_extract import OdlDocument, OdlImage, OdlPage, OdlParagraph, OdlTable
from odl_vl.pipeline.output import document_dir, write_outputs
from odl_vl.pipeline.run import DocumentResult, PageOutcome


def _emit(tmp_path):
    """A one-page doc with a numbered heading, body prose, a captioned table, and a figure -> exercises a
    section/page parent + a text child + atomic children through the real emission path."""
    heading = OdlParagraph(0, "heading", (50, 40, 400, 60), "1 Introduction", element_id=1, order=0)
    body = OdlParagraph(0, "paragraph", (50, 70, 400, 120), "Body prose for the section.", element_id=2, order=1)
    table = OdlTable(0, 2, 2, (50, 500, 400, 600), (("H", "V"), ("a", "1")), label="Table 1", caption="cap",
                     cell_boxes=(((10, 10, 20, 20), (30, 10, 40, 20)), ((10, 30, 20, 40), (30, 30, 40, 40))))
    figure = OdlImage(0, (50, 130, 400, 300), element_id="i1", label="Figure 1", caption="figcap", kind="figure")
    structure = OdlDocument(1, (OdlPage(0, "text", (table,), (figure,), (heading, body)),))
    meta = DocumentMeta(document_id="emit012345678900", content_sha256="emit012345678900ff",
                        original_filename="d.pdf", source_id="csnl", n_pages=1, mode="deterministic")
    result = DocumentResult((PageOutcome(0, "deterministic", False, "# md", 0.0, ()),), structure=structure, meta=meta)
    out = document_dir(tmp_path, result)
    write_outputs(result, out)
    return out


# ---- Layer 0: byte-compat + non-destructive overlay -------------------------------------------------
def test_document_json_layer0_is_byte_compat_with_overlay(tmp_path):
    out = _emit(tmp_path)
    doc = json.loads((out / "document.json").read_text(encoding="utf-8"))
    banned = ("role", "zone", "heading_level", "odl_role")
    for name in ("blocks", "tables", "figures", "sections"):
        for n in doc.get(name, []):
            assert not any(k in n for k in banned), f"{name} node inlines {set(n) & set(banned)}"
    assert doc["roles"] and all({"role", "confidence", "by"} <= set(v) for v in doc["roles"].values())
    assert "zones" in doc and "@context" in doc and "ontology" in doc


def test_document_structure_json_is_a_typed_structure_view(tmp_path):
    out = _emit(tmp_path)
    doc = json.loads((out / "document.json").read_text(encoding="utf-8"))
    struct = json.loads((out / "document.structure.json").read_text(encoding="utf-8"))
    assert struct["contract"] == contract_tag(STRUCTURE_CONTRACT)
    assert StructureExport.from_dict(struct).to_dict() == struct    # the file IS the contract's serialization
    assert struct["document_id"] == doc["document_id"]              # identity spread flat, mirrors document.json
    # typed view stays faithful to the loss-aware source of truth: same node ids, role still NOT inlined
    assert [b["id"] for b in struct["blocks"]] == [b["id"] for b in doc["blocks"]]
    assert all("role" not in b for b in struct["blocks"])
    assert struct["roles"] == doc["roles"] and struct["zones"] == doc["zones"]


# ---- Layer 2: emission == contract.to_dict() (idempotent round-trip) --------------------------------
def test_semantic_json_is_a_semantic_view_payload(tmp_path):
    out = _emit(tmp_path)
    read = json.loads((out / "document.semantic.json").read_text(encoding="utf-8"))
    assert read["contract"] == contract_tag(SEMANTIC_CONTRACT)
    assert SemanticView.from_dict(read).to_dict() == read          # the file IS the contract's serialization
    assert read["document_id"] == "emit012345678900"               # identity spread flat (Layer-0 aligned)
    assert all("bbox" not in n and "font_size" not in n for n in read["nodes"])   # geometry-free


def test_provenance_json_is_a_provenance_payload_joined_by_node_id(tmp_path):
    out = _emit(tmp_path)
    sem = json.loads((out / "document.semantic.json").read_text(encoding="utf-8"))
    prov = json.loads((out / "document.provenance.json").read_text(encoding="utf-8"))
    assert prov["contract"] == contract_tag(PROVENANCE_CONTRACT)
    assert Provenance.from_dict(prov).to_dict() == prov
    node_ids = {n["id"] for n in sem["nodes"]}
    assert set(prov["prov"]).issubset(node_ids)                    # every provenance key is a semantic node


def test_chunks_jsonl_lines_are_chunk_records(tmp_path):
    out = _emit(tmp_path)
    lines = [json.loads(x) for x in (out / "document.chunks.jsonl").read_text(encoding="utf-8").splitlines()]
    assert lines, "expected at least one chunk"
    for c in lines:
        assert ChunkRecord.from_dict(c).to_dict() == c             # each line IS ChunkRecord.to_dict()
        assert {"id", "doc_id", "structural_type", "level", "source_refs"} <= set(c)
        assert set(c["source_refs"]) == {"nodes", "pages"}
        assert isinstance(c["tokenizer"], str) and c["tokenizer"]  # tokenizer name recorded (counts are tokenizer-specific)
    parents = [c for c in lines if c["level"] == "parent"]
    children = [c for c in lines if c["level"] == "child"]
    assert parents and children
    assert all(c["parent_id"] in {p["id"] for p in parents} for c in children)   # every child under a parent
    # atomic children keep their single source node whole (table/figure)
    atomic = [c for c in children if c.get("atomic")]
    assert atomic and all(len(c["source_refs"]["nodes"]) == 1 for c in atomic)
