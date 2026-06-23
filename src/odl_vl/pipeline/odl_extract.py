"""ODL (opendataloader-pdf) structure + clean-text extraction layer.

ODL is the deterministic **structure / clean-text** source (measurement-findings F17): table
grids, reading-ordered text (header/footer filtered), and image assets. VALUES stay with
pypdfium2 (`deterministic.py`) -- ODL can drop a real number for cleanliness (F17 'A100 40GB'),
so it must not be the value authority. Requires Java 17 at runtime (processing-tiers §2.6).

The ODL JSON tree (`kids`) carries typed elements: paragraph/heading/list item/caption/text
block (text `content`), table (rows -> cells), image (bbox). Page numbers are 1-based in ODL;
this module exposes 0-based ``page_index`` to match the rest of the pipeline.

The ODL subprocess invocation is injectable (``runner``) so parsing is unit-testable without
Java; the real runner calls ``opendataloader_pdf.convert``.
"""
from __future__ import annotations

import json
import re
import tempfile
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

BBox = tuple[float, float, float, float]

_TEXT_TYPES = frozenset({"paragraph", "heading", "list item", "text block"})
_IMAGE_TYPES = frozenset({"image", "figure", "picture"})

# Original printed table/figure numbers ("Table 5-2", "표 5-2", "Figure 12", "그림 3").
_TABLE_LABEL_RE = re.compile(r"(?i)\b(?:table|표|tab\.?)\s*(\d+(?:[-.]\d+)*)")
_FIGURE_LABEL_RE = re.compile(r"(?i)\b(?:figure|fig\.?|그림|figs?\.?)\s*(\d+(?:[-.]\d+)*)")


class OdlError(RuntimeError):
    """ODL extraction failure (e.g. java_not_found, odl_convert_failed)."""


@dataclass(frozen=True, slots=True)
class _Caption:
    page_index: int
    bbox: BBox
    text: str


@dataclass(frozen=True, slots=True)
class OdlImage:
    page_index: int
    bbox: BBox
    element_id: str | None = None
    label: str | None = None     # original printed number, e.g. "Figure 12"
    caption: str | None = None
    kind: str = "image"


@dataclass(frozen=True, slots=True)
class OdlTable:
    page_index: int
    n_rows: int
    n_cols: int
    bbox: BBox
    cells: tuple[tuple[str, ...], ...]  # row-major text grid
    label: str | None = None     # original printed number, e.g. "표 5-2"
    caption: str | None = None

    @property
    def width(self) -> float:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> float:
        return self.bbox[3] - self.bbox[1]

    @property
    def has_content(self) -> bool:
        return any(c.strip() for row in self.cells for c in row)


@dataclass(frozen=True, slots=True)
class OdlPage:
    page_index: int
    text: str  # reading-ordered, header/footer-filtered
    tables: tuple[OdlTable, ...]
    images: tuple[OdlImage, ...]


@dataclass(frozen=True, slots=True)
class OdlDocument:
    n_pages: int
    pages: tuple[OdlPage, ...]


def substantial_tables(page: OdlPage, *, min_width: float = 20.0, min_height: float = 10.0) -> list[OdlTable]:
    """Real tables, dropping degenerate sliver false-positives (F16: plot axis lines yield
    near-0pt empty 'tables'). The primary signal is **cell content** (slivers have none); a
    small geometric floor drops near-zero boxes. Thresholds are tunable (calibrated per
    source by diagnosis -- R-A7); the defaults keep small real tables (e.g. a 75pt grid)."""
    return [t for t in page.tables if t.has_content and t.width > min_width and t.height > min_height]


def _collect_text(node: object) -> str:
    parts: list[str] = []

    def walk(n: object) -> None:
        if isinstance(n, dict):
            content = n.get("content")
            if isinstance(content, str):
                parts.append(content)
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(node)
    return " ".join(p for p in parts if p).strip()


def _parse_table(node: dict) -> OdlTable | None:
    page = node.get("page number")
    if not page:
        return None
    bbox = node.get("bounding box") or [0.0, 0.0, 0.0, 0.0]
    grid: list[tuple[str, ...]] = []
    for row in node.get("rows", []) or []:
        grid.append(tuple(_collect_text(cell) for cell in (row.get("cells") or [])))
    return OdlTable(
        page_index=int(page) - 1,
        n_rows=int(node.get("number of rows", len(grid))),
        n_cols=int(node.get("number of columns", max((len(r) for r in grid), default=0))),
        bbox=tuple(float(x) for x in bbox[:4]),  # type: ignore[arg-type]
        cells=tuple(grid),
    )


def _center(b: BBox) -> tuple[float, float]:
    return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


def _dist(a: BBox, b: BBox) -> float:
    (ax, ay), (bx, by) = _center(a), _center(b)
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def _label_tables_figures(
    tables: list[OdlTable], images: list[OdlImage], captions: list[_Caption]
) -> tuple[tuple[OdlTable, ...], tuple[OdlImage, ...]]:
    """Attach the original printed number ("Table 5-2", "Figure 12") by matching each ODL caption
    to the nearest table/figure on its page (bbox proximity) and parsing its leading label."""
    for cap in captions:
        tmatch = _TABLE_LABEL_RE.search(cap.text)
        fmatch = _FIGURE_LABEL_RE.search(cap.text)
        if tmatch and tables:
            i = min(range(len(tables)), key=lambda k: _dist(cap.bbox, tables[k].bbox))
            if tables[i].label is None:
                tables[i] = replace(tables[i], label=tmatch.group(0).strip(), caption=cap.text)
        elif fmatch and images:
            i = min(range(len(images)), key=lambda k: _dist(cap.bbox, images[k].bbox))
            if images[i].label is None:
                images[i] = replace(images[i], label=fmatch.group(0).strip(), caption=cap.text, kind="figure")
    return tuple(tables), tuple(images)


def parse_document(data: dict) -> OdlDocument:
    """Parse an ODL JSON document dict into an OdlDocument. Pure (no I/O)."""
    n_pages = int(data.get("number of pages", 0))
    text_by_page: dict[int, list[str]] = defaultdict(list)
    tables_by_page: dict[int, list[OdlTable]] = defaultdict(list)
    images_by_page: dict[int, list[OdlImage]] = defaultdict(list)
    captions_by_page: dict[int, list[_Caption]] = defaultdict(list)

    def walk(node: object) -> None:
        if isinstance(node, dict):
            ntype = str(node.get("type", "")).lower()
            page = node.get("page number")
            if ntype == "table":
                table = _parse_table(node)
                if table is not None:
                    tables_by_page[table.page_index].append(table)
                return  # cells handled inside; don't descend (avoid double-counting as page text)
            bbox = node.get("bounding box") or [0.0, 0.0, 0.0, 0.0]
            box = tuple(float(x) for x in bbox[:4])
            if ntype == "caption" and page:
                content = node.get("content")
                if isinstance(content, str) and content.strip():
                    captions_by_page[int(page) - 1].append(_Caption(int(page) - 1, box, content))  # type: ignore[arg-type]
            elif ntype in _TEXT_TYPES:
                content = node.get("content")
                if isinstance(content, str) and content.strip() and page:
                    text_by_page[int(page) - 1].append(content)
            elif ntype in _IMAGE_TYPES and page:
                images_by_page[int(page) - 1].append(OdlImage(int(page) - 1, box, node.get("id")))  # type: ignore[arg-type]
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    if n_pages <= 0:
        n_pages = 1 + max([*text_by_page, *tables_by_page, *images_by_page, *captions_by_page, -1])
    pages = []
    for i in range(n_pages):
        tables, images = _label_tables_figures(
            list(tables_by_page.get(i, [])), list(images_by_page.get(i, [])), captions_by_page.get(i, [])
        )
        pages.append(OdlPage(page_index=i, text="\n".join(text_by_page.get(i, [])), tables=tables, images=images))
    return OdlDocument(n_pages=n_pages, pages=tuple(pages))


def _run_odl(pdf_path: str) -> dict:
    import opendataloader_pdf as odl

    with tempfile.TemporaryDirectory() as tmp:
        try:
            odl.convert(input_path=str(pdf_path), output_dir=tmp, format=["json"], quiet=True)
        except FileNotFoundError as exc:  # 'java' not on PATH
            raise OdlError("java_not_found: ODL requires Java 17") from exc
        except Exception as exc:  # noqa: BLE001 -- surface as opaque ODL error
            raise OdlError(f"odl_convert_failed:{type(exc).__name__}") from exc
        out = Path(tmp) / f"{Path(pdf_path).stem}.json"
        if not out.exists():
            raise OdlError("odl_no_json_output")
        return json.loads(out.read_text(encoding="utf-8"))


def extract(pdf_path: str, *, runner: Callable[[str], dict] | None = None) -> OdlDocument:
    """Extract ODL structure/text from a PDF. ``runner`` (returning the ODL JSON dict) is
    injectable for tests; the default invokes ODL (Java 17 required)."""
    return parse_document((runner or _run_odl)(pdf_path))
