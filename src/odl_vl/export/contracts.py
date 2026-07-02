"""Versioned export-contract types (design doc §10).

The dataclasses here are the *authoritative* field list for each surface; the spec doc
(``docs/export-contracts.md``) mirrors them and ``tests/test_export_contracts.py`` asserts the
two stay in sync. Node shapes match what ``pipeline.structure.build_graph`` and
``pipeline.docmeta.DocumentMeta.to_dict`` already emit, so the contract *documents* current
output rather than inventing a new one.

Forward-compat: ``from_dict`` ignores unknown keys, so a newer producer can add fields without
breaking an older consumer. ``to_dict`` omits ``None`` optionals to match the compact output.json.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any

# (name, version) -- version is "MAJOR.MINOR". MAJOR bumps on removal/rename/semantic change;
# MINOR bumps on additive fields. Consumers gate on MAJOR (see check_compatible).
# v1.1: StructureExport gains context/zones; ChunkRecord gains the parent/child small-to-big model
# (level/children/prev/next/is_continuation/page_span via source_refs/display_text/embedding_text/tokenizer).
STRUCTURE_CONTRACT: tuple[str, str] = ("odl-vl.structure", "1.1")
CHUNK_CONTRACT: tuple[str, str] = ("odl-vl.chunks", "1.1")
# Layer 2 clean projection + its geometry sidecar (the two artifacts PR #4's pipeline actually produces).
SEMANTIC_CONTRACT: tuple[str, str] = ("odl-vl.semantic", "1.0")
PROVENANCE_CONTRACT: tuple[str, str] = ("odl-vl.provenance", "1.0")


def contract_tag(contract: tuple[str, str]) -> dict[str, str]:
    """The ``{"name", "version"}`` tag stamped into every payload."""
    return {"name": contract[0], "version": contract[1]}


def check_compatible(tag: dict[str, Any] | None, contract: tuple[str, str]) -> bool:
    """True when ``tag`` is the same contract name and the SAME major version. A consumer built
    for major N accepts any minor of N (additive) and rejects a different name or major."""
    if not tag or tag.get("name") != contract[0]:
        return False
    got = str(tag.get("version", "")).split(".", 1)[0]
    want = contract[1].split(".", 1)[0]
    return got == want


def _from_dict(cls, d: dict[str, Any]):
    """Build a dataclass from a dict, dropping unknown keys (forward-compat)."""
    known = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in d.items() if k in known})


def _compact(d: dict[str, Any]) -> dict[str, Any]:
    """Drop ``None`` values so the serialized form matches build_graph's omit-when-absent style."""
    return {k: v for k, v in d.items() if v is not None}


# --------------------------------------------------------------------------------------------
# Structure export (Layer 0+1) -- grounded structure graph. Mirrors build_graph + docmeta.
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Cell:
    text: str
    bbox: list[float] | None = None
    row_span: int | None = None
    col_span: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return _compact({"text": self.text, "bbox": self.bbox,
                         "row_span": self.row_span, "col_span": self.col_span})

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Cell":
        return _from_dict(cls, d)


@dataclass(frozen=True)
class Region:
    page: int
    bbox: list[float]

    def to_dict(self) -> dict[str, Any]:
        return {"page": self.page, "bbox": self.bbox}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Region":
        return _from_dict(cls, d)


@dataclass(frozen=True)
class Block:
    """A text node (ODL kind in ``type``). ``section``/``refs``/``figure`` are graph edges added
    downstream; ``role`` stays out of here -- it lives in the ``roles`` overlay (non-destructive)."""
    id: str
    type: str
    page: int
    order: int
    bbox: list[float]
    text: str
    font_size: float | None = None
    section: str | None = None
    refs: list[str] | None = None
    figure: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _compact({
            "id": self.id, "type": self.type, "page": self.page, "order": self.order,
            "bbox": self.bbox, "text": self.text, "font_size": self.font_size,
            "section": self.section, "refs": self.refs, "figure": self.figure,
        })

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Block":
        return _from_dict(cls, d)


@dataclass(frozen=True)
class Table:
    id: str
    pages: list[int]
    order: int
    n_rows: int
    n_cols: int
    cells: list[list[Cell]]
    regions: list[Region]
    continued: bool = False
    type: str = "table"
    label: str | None = None
    caption: str | None = None
    caption_id: str | None = None
    arithmetic: Any | None = None
    views: dict[str, str] | None = None
    section: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _compact({
            "id": self.id, "type": self.type, "pages": self.pages, "order": self.order,
            "label": self.label, "caption": self.caption, "caption_id": self.caption_id,
            "n_rows": self.n_rows, "n_cols": self.n_cols,
            "cells": [[c.to_dict() for c in row] for row in self.cells],
            "regions": [r.to_dict() for r in self.regions], "continued": self.continued,
            "arithmetic": self.arithmetic, "views": self.views, "section": self.section,
        })

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Table":
        d = dict(d)
        d["cells"] = [[Cell.from_dict(c) for c in row] for row in d.get("cells", [])]
        d["regions"] = [Region.from_dict(r) for r in d.get("regions", [])]
        return _from_dict(cls, d)


@dataclass(frozen=True)
class Figure:
    id: str
    page: int
    order: int
    type: str = "figure"
    kind: str = "figure"
    label: str | None = None
    caption: str | None = None
    caption_id: str | None = None
    bbox: list[float] | None = None
    file: str | None = None
    source: str | None = None
    description: str | None = None
    section: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _compact({
            "id": self.id, "type": self.type, "page": self.page, "order": self.order,
            "label": self.label, "caption": self.caption, "caption_id": self.caption_id,
            "bbox": self.bbox, "file": self.file, "kind": self.kind,
            "source": self.source, "description": self.description, "section": self.section,
        })

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Figure":
        return _from_dict(cls, d)


@dataclass(frozen=True)
class Section:
    id: str
    heading: str
    level: int
    block_id: str
    children: list[str] = field(default_factory=list)
    content: list[str] = field(default_factory=list)
    page: int | None = None
    parent: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _compact({
            "id": self.id, "heading": self.heading, "level": self.level,
            "block_id": self.block_id, "page": self.page, "parent": self.parent,
            "children": self.children, "content": self.content,
        })

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Section":
        return _from_dict(cls, d)


@dataclass(frozen=True)
class PageEntry:
    page_index: int
    page_number: int
    mode: str
    used_vlm: bool
    flags: list[str] = field(default_factory=list)
    page_label: str | None = None
    markdown_file: str | None = None
    content: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    figures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _compact({
            "page_index": self.page_index, "page_number": self.page_number,
            "page_label": self.page_label, "mode": self.mode, "used_vlm": self.used_vlm,
            "flags": self.flags, "markdown_file": self.markdown_file,
            "content": self.content, "blocks": self.blocks,
            "tables": self.tables, "figures": self.figures,
        })

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PageEntry":
        return _from_dict(cls, d)


@dataclass(frozen=True)
class RoleAssignment:
    """Layer 1 overlay entry: a semantic role for a node (block/section/table/figure id), its
    confidence, and how it was decided (``signal:...`` / ``vlm`` / ``default``)."""
    role: str
    confidence: float
    by: str

    def to_dict(self) -> dict[str, Any]:
        return {"role": self.role, "confidence": self.confidence, "by": self.by}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RoleAssignment":
        return _from_dict(cls, d)


@dataclass(frozen=True)
class StructureExport:
    """Layer 0+1 surface. ``document`` is ``DocumentMeta.to_dict()``; ``roles`` is the Layer 1
    overlay keyed by node id (empty until role classification runs); ``ontology`` records the
    injected profile+version (or None)."""
    document: dict[str, Any]
    pages: list[PageEntry] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    figures: list[Figure] = field(default_factory=list)
    roles: dict[str, RoleAssignment] = field(default_factory=dict)
    zones: list[dict[str, Any]] = field(default_factory=list)   # v1.1: zone -> pages summary (top-level axis)
    context: dict[str, Any] | None = None                        # v1.1: JSON-LD @context (portable IR)
    ontology: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return _compact({
            "contract": contract_tag(STRUCTURE_CONTRACT),
            "@context": self.context,
            "document": self.document,
            "ontology": self.ontology,
            "pages": [p.to_dict() for p in self.pages],
            "sections": [s.to_dict() for s in self.sections],
            "blocks": [b.to_dict() for b in self.blocks],
            "tables": [t.to_dict() for t in self.tables],
            "figures": [f.to_dict() for f in self.figures],
            "roles": {k: v.to_dict() for k, v in self.roles.items()},
            "zones": self.zones or None,
        })

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "StructureExport":
        return cls(
            document=d.get("document", {}),
            context=d.get("@context"),
            ontology=d.get("ontology"),
            pages=[PageEntry.from_dict(x) for x in d.get("pages", [])],
            sections=[Section.from_dict(x) for x in d.get("sections", [])],
            blocks=[Block.from_dict(x) for x in d.get("blocks", [])],
            tables=[Table.from_dict(x) for x in d.get("tables", [])],
            figures=[Figure.from_dict(x) for x in d.get("figures", [])],
            roles={k: RoleAssignment.from_dict(v) for k, v in d.get("roles", {}).items()},
            zones=d.get("zones", []),
        )


# --------------------------------------------------------------------------------------------
# Chunk export (Layer 2) -- agent/RAG-ready records. One ChunkRecord per chunks.jsonl line.
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ChunkRecord:
    """A retrieval unit in the small-to-big model (design §4). A PARENT chunk (``level="parent"``)
    is a whole section (or a page group) listed by ``children``; a CHILD chunk (``level="child"``)
    is a token-packed leaf under ``parent_id``, kept whole for atomics (``atomic=True`` on
    table/figure/equation). ``source_refs`` (node ids + ``pages`` span) is the round-trip to Layer 0
    for citation/bbox grounding. ``display_text`` is what to show; ``embedding_text`` prepends the
    heading breadcrumb so a focused child still embeds with its structural context (§9.3). ``role``/
    ``heading_path`` drive structure/semantic-aware retrieval; a ``drop``-policy role never produces
    a record. ``text`` is a legacy v1.0 alias kept optional for back-compat (prefer ``display_text``)."""
    id: str
    doc_id: str
    structural_type: str
    level: str | None = None                                    # "parent" | "child"
    token_count: int = 0
    tokenizer: str | None = None
    atomic: bool = False
    is_continuation: bool = False
    parent_id: str | None = None
    children: list[str] = field(default_factory=list)           # parent -> its child chunk ids
    prev: str | None = None                                     # leaf reading-order links
    next: str | None = None
    zone: str | None = None
    role: str | None = None
    heading_path: list[str] = field(default_factory=list)       # was section_path (PR #4)
    display_text: str | None = None
    embedding_text: str | None = None
    text: str | None = None                                     # legacy v1.0 alias (optional)
    source_refs: dict[str, list] = field(default_factory=lambda: {"nodes": [], "pages": []})
    node_types: list[str] = field(default_factory=list)         # semantic node types packed into this chunk
    refs: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _compact({
            "id": self.id, "level": self.level, "parent_id": self.parent_id, "doc_id": self.doc_id,
            "structural_type": self.structural_type, "zone": self.zone, "role": self.role,
            "heading_path": self.heading_path or None, "children": self.children or None,
            "display_text": self.display_text, "embedding_text": self.embedding_text,
            "text": self.text, "token_count": self.token_count, "tokenizer": self.tokenizer,
            "atomic": self.atomic, "is_continuation": self.is_continuation,
            "prev": self.prev, "next": self.next,
            "source_refs": self.source_refs, "node_types": self.node_types or None,
            "refs": self.refs or None, "meta": self.meta or None,
        })

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ChunkRecord":
        return _from_dict(cls, d)


# --------------------------------------------------------------------------------------------
# Semantic view (Layer 2) -- the agent-clean projection: role inlined, geometry removed. Plus its
# geometry sidecar, keyed by the same node id. These are the two artifacts the pipeline emits as
# document.semantic.json / document.provenance.json (design §4/§5).
# --------------------------------------------------------------------------------------------

# Envelope keys are contract-controlled; everything else in a semantic payload is flat identity meta
# (document_id/content_sha256/n_pages/mode/...) collected into ``document`` on from_dict.
_SEMANTIC_ENVELOPE = frozenset(
    {"contract", "@context", "profile", "metadata", "zones", "sections", "nodes", "reading_order"}
)


@dataclass(frozen=True)
class SemanticView:
    """Layer 2 clean projection (``document.semantic.json``). ``document`` holds the flat identity meta
    (spread back to the top level on serialization, matching the flat Layer 0 ``document.json``);
    ``nodes`` carry role inlined and NO geometry (id/type(role)/zone/text|latex|label/caption_ref?/...);
    ``sections`` is the heading tree; ``reading_order`` is the flat node-id stream. Node/section dicts
    stay open (heterogeneous per type) -- the contract governs the envelope + the node-id join to
    ``Provenance``, not each node's inner shape."""
    document: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] | None = None
    profile: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    zones: list[dict[str, Any]] = field(default_factory=list)
    sections: list[dict[str, Any]] = field(default_factory=list)
    nodes: list[dict[str, Any]] = field(default_factory=list)
    reading_order: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _compact({
            "contract": contract_tag(SEMANTIC_CONTRACT),
            **self.document,
            "@context": self.context,
            "profile": self.profile,
            "metadata": self.metadata or None,
            "zones": self.zones,
            "sections": self.sections,
            "nodes": self.nodes,
            "reading_order": self.reading_order,
        })

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SemanticView":
        return cls(
            document={k: v for k, v in d.items() if k not in _SEMANTIC_ENVELOPE},
            context=d.get("@context"),
            profile=d.get("profile"),
            metadata=d.get("metadata", {}) or {},
            zones=d.get("zones", []),
            sections=d.get("sections", []),
            nodes=d.get("nodes", []),
            reading_order=d.get("reading_order", []),
        )


@dataclass(frozen=True)
class Provenance:
    """Geometry sidecar (``document.provenance.json``): ``prov`` maps node id ->
    ``{page?, order?, bbox?, font_size?, regions?, cell_boxes?}``. Loss-aware grounding for the
    geometry stripped out of ``SemanticView``; join by node id."""
    prov: dict[str, Any] = field(default_factory=dict)
    profile: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return _compact({
            "contract": contract_tag(PROVENANCE_CONTRACT),
            "profile": self.profile,
            "prov": self.prov,
        })

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Provenance":
        return cls(prov=d.get("prov", {}), profile=d.get("profile"))
