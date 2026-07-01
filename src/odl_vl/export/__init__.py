"""Versioned public export contracts (design doc §10).

Two stable, independently-versioned surfaces sit between the parsing/chunking core and any
downstream consumer, so a future repo split (`odl-vl` core vs `odl-vl[kg]`) is a packaging
move, not a rewrite:

- **Structure export** (Layer 0+1) -- the grounded structure graph (identity/provenance +
  reading-order pages + sections + blocks/tables/figures + role overlay). Consumed by Mode 2
  (our KG builder) and any graph tool. This is a superset of the existing ``document.json``
  plus the Layer 1 ``roles`` overlay.
- **Chunk export** (Layer 2) -- the agent/RAG-ready chunk records (clean text, role, heading
  path, provenance refs). Consumed by Mode 1 (text/chunks) RAG ingestion.

Stability policy: additive within a major version; consumers MUST ignore unknown fields
(forward-compat, enforced by ``from_dict``). Field removal/rename or a semantic change bumps
the major. Every payload carries its ``contract`` tag; use ``check_compatible`` to gate.
"""
from __future__ import annotations

from .contracts import (
    CHUNK_CONTRACT,
    STRUCTURE_CONTRACT,
    Block,
    Cell,
    ChunkRecord,
    Figure,
    PageEntry,
    Region,
    RoleAssignment,
    Section,
    StructureExport,
    Table,
    check_compatible,
    contract_tag,
)

__all__ = [
    "STRUCTURE_CONTRACT",
    "CHUNK_CONTRACT",
    "StructureExport",
    "ChunkRecord",
    "Block",
    "Cell",
    "Table",
    "Region",
    "Figure",
    "Section",
    "PageEntry",
    "RoleAssignment",
    "contract_tag",
    "check_compatible",
]
