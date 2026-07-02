from __future__ import annotations

import json

from parse_anything.pipeline.catalog import build_index, query


def _write_doc(root, source, docid, *, external=None, n_flags=0, n_tables=1):
    d = root / source / docid
    d.mkdir(parents=True)
    doc = {
        "document_id": docid, "content_sha256": docid + "ff", "external_id": external,
        "original_filename": f"{docid}.pdf", "source": {"source_id": source},
        "n_pages": 3, "mode": "deterministic",
        "pages": [{"flags": ["f"] * n_flags}], "tables": [{}] * n_tables, "figures": [],
    }
    (d / "document.json").write_text(json.dumps(doc), encoding="utf-8")


def test_build_and_query_catalog(tmp_path):
    root = tmp_path / "out"
    _write_doc(root, "csnl", "aaa", external="ext-1", n_flags=2)
    _write_doc(root, "csnl", "bbb")
    _write_doc(root, "hwp", "ccc", external="ext-9")
    db = tmp_path / "catalog.db"

    assert build_index(root, db) == 3
    assert len(query(db)) == 3
    assert [r["document_id"] for r in query(db, source_id="csnl")] == ["aaa", "bbb"]
    assert query(db, external_id="ext-9")[0]["document_id"] == "ccc"
    flagged = query(db, flagged_only=True)
    assert len(flagged) == 1 and flagged[0]["document_id"] == "aaa" and flagged[0]["n_flags"] == 2

    # derived + rebuildable: a second build is idempotent (no duplicates)
    assert build_index(root, db) == 3 and len(query(db)) == 3
