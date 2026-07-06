"""Document identity + provenance metadata (R2).

The canonical document id is a content hash (sha256[:16] of the PDF bytes): deterministic,
dedup-friendly, idempotent (re-processing the same file -> same id/folder), and free of messy
filenames. A caller-provided ``external_id`` is preserved alongside for lookup. The original
filename, ingestion origin, and PDF producer metadata are kept as provenance.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium

_PRODUCER_KEYS = ("Producer", "Creator", "Title", "Author", "CreationDate", "ModificationDate")


def document_id(pdf_path: str) -> tuple[str, str]:
    """Return (short_id, full_sha256) for a PDF's bytes. short_id = sha256[:16]."""
    full = hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest()
    return full[:16], full


def _producer_meta(pdf_path: str) -> dict[str, str]:
    doc = pdfium.PdfDocument(pdf_path)
    try:
        meta = {}
        for key in _PRODUCER_KEYS:
            value = doc.get_metadata_value(key)
            if value:
                meta[key.lower()] = value
        return meta
    finally:
        doc.close()


@dataclass(frozen=True, slots=True)
class DocumentMeta:
    document_id: str
    content_sha256: str
    original_filename: str
    source_id: str = "default"
    ingested_from: str | None = None
    external_id: str | None = None
    n_pages: int = 0
    mode: str = ""
    producer: dict[str, str] = field(default_factory=dict)
    diagnostic: dict[str, Any] = field(default_factory=lambda: {"tier": "cli", "at": None, "profile_id": None})

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "content_sha256": self.content_sha256,
            "external_id": self.external_id,
            "original_filename": self.original_filename,
            "source": {"source_id": self.source_id, "ingested_from": self.ingested_from},
            "producer": self.producer,
            "n_pages": self.n_pages,
            "mode": self.mode,
            "diagnostic": self.diagnostic,
        }


def build_meta(
    pdf_path: str,
    *,
    source_id: str = "default",
    external_id: str | None = None,
    ingested_from: str | None = None,
    original_filename: str | None = None,
    mode: str = "",
    n_pages: int = 0,
) -> DocumentMeta:
    short, full = document_id(pdf_path)
    return DocumentMeta(
        document_id=short,
        content_sha256=full,
        # override lets an image-wrapped run record the real image name, not the throwaway temp .pdf
        original_filename=original_filename or Path(pdf_path).name,
        source_id=source_id,
        external_id=external_id,
        ingested_from=ingested_from or str(pdf_path),
        n_pages=n_pages,
        mode=mode,
        producer=_producer_meta(pdf_path),
    )
