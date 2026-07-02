"""Derived SQLite catalog over the filesystem document.json store.

The filesystem (`<out>/<source_id>/<document_id>/document.json` + assets) stays the source of
truth; this index is a rebuildable projection that enables cross-document lookup at scale
(by external_id, source, flag counts) without scanning every file. Uses stdlib sqlite3 -- no new
dependency. `build_index` is a full rebuild, so the index can always be regenerated from disk.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  document_id     TEXT PRIMARY KEY,
  source_id       TEXT,
  external_id     TEXT,
  original_filename TEXT,
  content_sha256  TEXT,
  n_pages         INTEGER,
  mode            TEXT,
  n_tables        INTEGER,
  n_figures       INTEGER,
  n_flags         INTEGER,
  path            TEXT
);
CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source_id);
CREATE INDEX IF NOT EXISTS idx_documents_external ON documents(external_id);
"""

_COLUMNS = ("document_id", "source_id", "external_id", "original_filename", "content_sha256",
            "n_pages", "mode", "n_tables", "n_figures", "n_flags", "path")


def _row_from_document_json(path: Path) -> tuple:
    doc = json.loads(path.read_text(encoding="utf-8"))
    n_flags = sum(len(p.get("flags", [])) for p in doc.get("pages", []))
    return (
        doc["document_id"], doc.get("source", {}).get("source_id"), doc.get("external_id"),
        doc.get("original_filename"), doc.get("content_sha256"), doc.get("n_pages"),
        doc.get("mode"), len(doc.get("tables", [])), len(doc.get("figures", [])),
        n_flags, str(path.parent),
    )


def build_index(out_root: str | Path, db_path: str | Path) -> int:
    """(Re)build the catalog from every document.json under out_root. Returns the row count."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(_SCHEMA)
        conn.execute("DELETE FROM documents")  # full rebuild -- the index is derived
        placeholders = ",".join("?" for _ in _COLUMNS)
        rows = [_row_from_document_json(p) for p in sorted(Path(out_root).rglob("document.json"))]
        conn.executemany(f"INSERT OR REPLACE INTO documents VALUES ({placeholders})", rows)
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def query(db_path: str | Path, *, source_id: str | None = None, external_id: str | None = None,
          flagged_only: bool = False) -> list[dict[str, Any]]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        sql = "SELECT * FROM documents WHERE 1=1"
        params: list[Any] = []
        if source_id is not None:
            sql += " AND source_id = ?"
            params.append(source_id)
        if external_id is not None:
            sql += " AND external_id = ?"
            params.append(external_id)
        if flagged_only:
            sql += " AND n_flags > 0"
        sql += " ORDER BY source_id, document_id"
        return [dict(row) for row in conn.execute(sql, params)]
    finally:
        conn.close()
