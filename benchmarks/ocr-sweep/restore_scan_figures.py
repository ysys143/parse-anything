#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict


JsonObject = dict[str, Any]
_PAGE_MARKER_RE = re.compile(r"^<!-- page \d+ -->$", re.MULTILINE)


class RestoreStats(TypedDict):
    model_dirs: int
    scan_docs: int
    restored_figures: int
    restored_documents: int


@dataclass(frozen=True)
class FigureTemplate:
    figure_id: str
    page: int
    order: int
    bbox: tuple[float, float, float, float]
    label: str | None
    caption: str | None

    @property
    def sort_key(self) -> tuple[int, float, int]:
        return (self.page, -self.bbox[3], self.order)


@dataclass(frozen=True)
class RestoredFigure:
    template: FigureTemplate
    figure_id: str
    file: str

    @property
    def image_ref(self) -> str:
        label = self.template.label or "figure"
        return f"![{label}]({self.file})"


def restore_results_tree(results: Path, scan_pdf: Path) -> RestoreStats:
    stats: RestoreStats = {"model_dirs": 0, "scan_docs": 0, "restored_figures": 0, "restored_documents": 0}
    page_sizes = _page_sizes(scan_pdf)
    for model_dir in sorted(path for path in results.iterdir() if path.is_dir()):
        model_stats = restore_model_dir(model_dir, scan_pdf, page_sizes=page_sizes)
        if model_stats["scan_docs"] == 0:
            continue
        stats["model_dirs"] += 1
        stats["scan_docs"] += model_stats["scan_docs"]
        stats["restored_figures"] += model_stats["restored_figures"]
        stats["restored_documents"] += model_stats["restored_documents"]
    return stats


def restore_model_dir(
    model_dir: Path,
    scan_pdf: Path,
    *,
    page_sizes: dict[int, tuple[float, float]] | None = None,
) -> RestoreStats:
    stats: RestoreStats = {"model_dirs": 1, "scan_docs": 0, "restored_figures": 0, "restored_documents": 0}
    page_sizes = page_sizes or _page_sizes(scan_pdf)
    born_dirs = _artifact_dirs(model_dir, "born")
    scan_dirs = _artifact_dirs(model_dir, "scan")
    if not born_dirs or not scan_dirs:
        return stats

    templates = _load_templates(born_dirs[0] / "document.json", page_sizes)
    if not templates:
        return stats

    for scan_dir in scan_dirs:
        restored = restore_scan_document(scan_dir, templates, scan_pdf)
        if restored:
            stats["scan_docs"] += 1
            stats["restored_figures"] += len(restored)
            stats["restored_documents"] += 1
    return stats


def restore_scan_document(
    scan_dir: Path,
    templates: Sequence[FigureTemplate],
    scan_pdf: Path,
) -> list[RestoredFigure]:
    doc_path = scan_dir / "document.json"
    if not doc_path.exists():
        return []
    document = _read_json(doc_path)
    restored = _apply_templates(document, templates)
    if not restored:
        return []

    _write_crops(scan_dir, scan_pdf, restored)
    _write_json(doc_path, document)
    for name in ("document.structure.json",):
        path = scan_dir / name
        if path.exists():
            structure = _read_json(path)
            _apply_templates(structure, templates)
            _write_json(path, structure)
    _patch_semantic(scan_dir / "document.semantic.json", restored)
    _patch_provenance(scan_dir / "document.provenance.json", restored)
    _patch_markdown(scan_dir / "document.md", restored, document_scope=True)
    pages_dir = scan_dir / "pages"
    for figure in restored:
        page_path = pages_dir / f"page-{figure.template.page - 1:03d}.md"
        _patch_markdown(page_path, [figure], document_scope=False)
    return restored


def _artifact_dirs(model_dir: Path, tag: str) -> list[Path]:
    candidates = [model_dir / f"out_{tag}", model_dir / tag]
    dirs: list[Path] = []
    for root in candidates:
        if root.exists():
            dirs.extend(path.parent for path in sorted(root.glob("*/*/document.json")))
    return dirs


def _load_templates(doc_path: Path, page_sizes: dict[int, tuple[float, float]]) -> list[FigureTemplate]:
    document = _read_json(doc_path)
    templates: list[FigureTemplate] = []
    for figure in document.get("figures", []):
        if not isinstance(figure, dict):
            continue
        bbox = _coerce_bbox(figure.get("bbox"))
        page = _coerce_int(figure.get("page"))
        if bbox is None or page is None:
            continue
        label = figure.get("label") if isinstance(figure.get("label"), str) else None
        if not _template_is_content_figure(bbox, page_sizes.get(page), label):
            continue
        templates.append(
            FigureTemplate(
                figure_id=_coerce_id(figure.get("id"), f"p{page}_fig{len(templates) + 1}"),
                page=page,
                order=_coerce_int(figure.get("order")) or 1_000_000,
                bbox=bbox,
                label=label,
                caption=figure.get("caption") if isinstance(figure.get("caption"), str) else None,
            )
        )
    return sorted(templates, key=lambda template: template.sort_key)


def _template_is_content_figure(
    bbox: tuple[float, float, float, float],
    page_size: tuple[float, float] | None,
    label: str | None,
) -> bool:
    if label:
        return True
    if page_size is None:
        return False
    page_area = page_size[0] * page_size[1]
    bbox_area = max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])
    return page_area > 0 and bbox_area / page_area >= 0.12


def _apply_templates(document: JsonObject, templates: Sequence[FigureTemplate]) -> list[RestoredFigure]:
    figures = document.setdefault("figures", [])
    if not isinstance(figures, list):
        return []
    pages = document.get("pages", [])
    if not isinstance(pages, list):
        pages = []
    roles = document.setdefault("roles", {})
    if not isinstance(roles, dict):
        roles = {}
        document["roles"] = roles
    zones = document.setdefault("zones", [])
    if not isinstance(zones, list):
        zones = []
        document["zones"] = zones

    restored: list[RestoredFigure] = []
    used_ids = {str(figure.get("id")) for figure in figures if isinstance(figure, dict) and figure.get("id")}
    for template in templates:
        figure = _find_target_figure(figures, template)
        if figure is None:
            figure_id = _unique_id(template.figure_id, used_ids)
            figure = {
                "id": figure_id,
                "type": "figure",
                "page": template.page,
                "order": template.order,
                "caption_id": None,
            }
            figures.append(figure)
            used_ids.add(figure_id)
        else:
            figure_id = _coerce_id(figure.get("id"), template.figure_id)
            used_ids.add(figure_id)
        file_ref = f"assets/{figure_id}.png"
        figure.update(
            {
                "id": figure_id,
                "type": "figure",
                "page": template.page,
                "order": _coerce_int(figure.get("order")) or template.order,
                "bbox": list(template.bbox),
                "file": file_ref,
                "source": "scan_template",
                "template_source": "born",
            }
        )
        if template.label and not figure.get("label"):
            figure["label"] = template.label
        if template.caption and not figure.get("caption"):
            figure["caption"] = template.caption
        _attach_to_page(pages, template.page, figure_id)
        roles.setdefault(figure_id, {"role": "figure", "confidence": 1.0, "by": "scan_template"})
        _attach_zone(zones, template.page)
        restored.append(RestoredFigure(template=template, figure_id=figure_id, file=file_ref))
    return restored


def _find_target_figure(figures: list[Any], template: FigureTemplate) -> JsonObject | None:
    if template.label:
        label = _norm_label(template.label)
        candidates = [
            figure
            for figure in figures
            if isinstance(figure, dict) and _norm_label(figure.get("label")) == label
        ]
        if candidates:
            return max(candidates, key=lambda figure: len(str(figure.get("caption") or "")))
    for figure in figures:
        if isinstance(figure, dict) and figure.get("id") == template.figure_id:
            return figure
    return None


def _attach_to_page(pages: list[Any], page_number: int, figure_id: str) -> None:
    page_index = page_number - 1
    if page_index < 0 or page_index >= len(pages):
        return
    page = pages[page_index]
    if not isinstance(page, dict):
        return
    for key in ("figures", "content"):
        values = page.setdefault(key, [])
        if isinstance(values, list) and figure_id not in values:
            values.append(figure_id)


def _attach_zone(zones: list[Any], page_number: int) -> None:
    body = next((zone for zone in zones if isinstance(zone, dict) and zone.get("zone") == "body"), None)
    if body is None:
        body = {"zone": "body", "pages": []}
        zones.append(body)
    pages = body.setdefault("pages", [])
    if isinstance(pages, list) and page_number not in pages:
        pages.append(page_number)
        pages.sort()


def _write_crops(scan_dir: Path, scan_pdf: Path, figures: Iterable[RestoredFigure], *, scale: float = 2.0) -> None:
    import pypdfium2 as pdfium
    from PIL import Image

    from parse_anything.pipeline.render import render_page_png

    assets = scan_dir / "assets"
    assets.mkdir(exist_ok=True)
    rendered: dict[int, Image.Image] = {}
    heights: dict[int, float] = {}
    doc = pdfium.PdfDocument(scan_pdf)
    try:
        for figure in figures:
            page_index = figure.template.page - 1
            if page_index < 0 or page_index >= len(doc):
                continue
            if page_index not in rendered:
                rendered[page_index] = Image.open(
                    io.BytesIO(render_page_png(str(scan_pdf), page_index, scale=scale))
                ).convert("RGB")
                heights[page_index] = float(doc[page_index].get_size()[1])
            image = rendered[page_index]
            height = heights[page_index]
            x0, y0, x1, y1 = figure.template.bbox
            box = (
                int(x0 * scale),
                int((height - y1) * scale),
                int(x1 * scale),
                int((height - y0) * scale),
            )
            box = (max(0, box[0]), max(0, box[1]), min(image.width, box[2]), min(image.height, box[3]))
            if box[2] <= box[0] or box[3] <= box[1]:
                continue
            image.crop(box).save(scan_dir / figure.file)
    finally:
        doc.close()


def _patch_semantic(path: Path, figures: Sequence[RestoredFigure]) -> None:
    if not path.exists():
        return
    semantic = _read_json(path)
    nodes = semantic.setdefault("nodes", [])
    if not isinstance(nodes, list):
        return
    by_id: dict[Any, JsonObject] = {node.get("id"): node for node in nodes if isinstance(node, dict)}
    for figure in figures:
        node = by_id.get(figure.figure_id)
        if node is None:
            node = {"id": figure.figure_id, "type": "figure", "zone": "body"}
            nodes.append(node)
            by_id[figure.figure_id] = node
        node["type"] = "figure"
        node["zone"] = node.get("zone") or "body"
        if figure.template.label is not None:
            node["label"] = figure.template.label
        else:
            node.pop("label", None)
        node["kind"] = node.get("kind") or "figure"
        node["source"] = "scan_template"
        node["file"] = figure.file
    reading_order = semantic.setdefault("reading_order", [])
    if isinstance(reading_order, list):
        for figure in figures:
            if figure.figure_id not in reading_order:
                reading_order.append(figure.figure_id)
    _write_json(path, semantic)


def _patch_provenance(path: Path, figures: Sequence[RestoredFigure]) -> None:
    if not path.exists():
        return
    provenance = _read_json(path)
    prov = provenance.setdefault("prov", {})
    if not isinstance(prov, dict):
        return
    for figure in figures:
        prov[figure.figure_id] = {
            "page": figure.template.page,
            "order": figure.template.order,
            "bbox": list(figure.template.bbox),
            "file": figure.file,
        }
    _write_json(path, provenance)


def _patch_markdown(path: Path, figures: Sequence[RestoredFigure], *, document_scope: bool) -> None:
    if not path.exists():
        return
    markdown = path.read_text(encoding="utf-8")
    original = markdown
    for figure in sorted(figures, key=lambda item: item.template.sort_key):
        markdown = _insert_figure_ref(markdown, figure, document_scope=document_scope)
    if markdown != original:
        path.write_text(markdown, encoding="utf-8")


def _insert_figure_ref(markdown: str, figure: RestoredFigure, *, document_scope: bool) -> str:
    if figure.image_ref in markdown or f"]({figure.file})" in markdown:
        return markdown
    if not document_scope:
        return _insert_figure_ref_in_segment(markdown, figure, marker=None)

    marker = f"<!-- page {figure.template.page} -->"
    start = markdown.find(marker)
    if start == -1:
        return markdown.rstrip() + "\n\n" + figure.image_ref + "\n"
    next_marker = _next_page_marker(markdown, start + len(marker))
    segment = markdown[start:next_marker]
    patched = _insert_figure_ref_in_segment(segment, figure, marker=marker)
    return markdown[:start] + patched + markdown[next_marker:]


def _insert_figure_ref_in_segment(markdown: str, figure: RestoredFigure, *, marker: str | None) -> str:
    label = figure.template.label
    if label:
        match = _caption_match(markdown, label)
        if match is not None:
            return markdown[: match.start()] + figure.image_ref + "\n\n" + markdown[match.start():]
    if marker is not None:
        insert_at = markdown.find(marker) + len(marker)
        return markdown[:insert_at].rstrip() + "\n\n" + figure.image_ref + markdown[insert_at:]
    return figure.image_ref + "\n\n" + markdown.lstrip()


def _caption_match(markdown: str, label: str) -> re.Match[str] | None:
    pattern = re.compile(rf"(?m)^(?=\s*(?:\*\*)?\s*{re.escape(label)}(?:[.:]|\s))")
    return pattern.search(markdown)


def _next_page_marker(markdown: str, start: int) -> int:
    match = _PAGE_MARKER_RE.search(markdown, start)
    return match.start() if match else len(markdown)


def _page_sizes(pdf_path: Path) -> dict[int, tuple[float, float]]:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(pdf_path)
    try:
        return {
            index + 1: (float(doc[index].get_size()[0]), float(doc[index].get_size()[1]))
            for index in range(len(doc))
        }
    finally:
        doc.close()


def _coerce_bbox(value: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(value, list | tuple) or len(value) != 4:
        return None
    try:
        x0, y0, x1, y1 = (float(item) for item in value)
    except (TypeError, ValueError):
        return None
    if x1 <= x0 or y1 <= y0:
        return None
    return x0, y0, x1, y1


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_id(value: Any, fallback: str) -> str:
    return value if isinstance(value, str) and value else fallback


def _norm_label(value: Any) -> str:
    return " ".join(str(value or "").lower().replace(".", " ").split())


def _unique_id(preferred: str, used_ids: set[str]) -> str:
    if preferred not in used_ids:
        return preferred
    index = 1
    while f"{preferred}_scan{index}" in used_ids:
        index += 1
    return f"{preferred}_scan{index}"


def _read_json(path: Path) -> JsonObject:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _write_json(path: Path, payload: JsonObject) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Restore scan figure crops from paired born OCR artifacts")
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--scan-pdf", required=True, type=Path)
    args = parser.parse_args(argv)
    stats = restore_results_tree(args.results, args.scan_pdf)
    print(json.dumps(stats, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
