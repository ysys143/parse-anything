from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def _load_restore_module():
    path = Path(__file__).resolve().parents[1] / "benchmarks" / "ocr-sweep" / "restore_scan_figures.py"
    spec = importlib.util.spec_from_file_location("ocr_sweep_restore_scan_figures", path)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load restore_scan_figures.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _make_scan_pdf(path: Path) -> Path:
    pdf = canvas.Canvas(str(path), pagesize=letter)
    pdf.setFillColorRGB(0.2, 0.45, 0.8)
    pdf.rect(72, 520, 260, 130, stroke=0, fill=1)
    pdf.showPage()
    pdf.save()
    return path


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_restore_scan_document_crops_template_figure_and_patches_artifacts(tmp_path):
    module = _load_restore_module()
    scan_pdf = _make_scan_pdf(tmp_path / "scan.pdf")
    scan_dir = tmp_path / "results" / "model" / "out_scan" / "model" / "scan-doc"
    (scan_dir / "pages").mkdir(parents=True)
    doc = {
        "pages": [
            {
                "page_index": 0,
                "content": ["p1_vlm1"],
                "figures": ["p1_vlm1"],
                "blocks": [],
                "tables": [],
            }
        ],
        "figures": [
            {
                "id": "p1_vlm1",
                "type": "figure",
                "page": 1,
                "order": 1000000000,
                "bbox": None,
                "file": None,
                "label": "Fig 3",
                "caption": "Fig 3. Template-backed caption.",
            }
        ],
        "roles": {"p1_vlm1": {"role": "figure", "confidence": 1.0, "by": "ontology"}},
        "zones": [{"zone": "body", "pages": [1]}],
    }
    for name in ("document.json", "document.structure.json"):
        _write_json(scan_dir / name, doc)
    _write_json(
        scan_dir / "document.semantic.json",
        {
            "nodes": [
                {
                    "id": "p1_vlm1",
                    "type": "figure",
                    "zone": "body",
                    "label": "Fig 3",
                    "file": None,
                }
            ],
            "reading_order": ["p1_vlm1"],
        },
    )
    _write_json(scan_dir / "document.provenance.json", {"prov": {"p1_vlm1": {"page": 1, "order": 1000000000}}})
    caption = "**Fig 3. Template-backed caption.** body"
    (scan_dir / "document.md").write_text(f"<!-- page 1 -->\n\n{caption}\n", encoding="utf-8")
    (scan_dir / "pages" / "page-000.md").write_text(caption + "\n", encoding="utf-8")
    templates = [
        module.FigureTemplate(
            figure_id="p1_1",
            page=1,
            order=3,
            bbox=(72.0, 520.0, 332.0, 650.0),
            label="Fig 3",
            caption="Fig 3",
        )
    ]

    restored = module.restore_scan_document(scan_dir, templates, scan_pdf)

    assert [figure.figure_id for figure in restored] == ["p1_vlm1"]
    asset = scan_dir / "assets" / "p1_vlm1.png"
    assert asset.exists()
    assert Image.open(asset).size == (520, 260)
    patched_md = (scan_dir / "document.md").read_text(encoding="utf-8")
    assert patched_md.index("![Fig 3](assets/p1_vlm1.png)") < patched_md.index("**Fig 3.")
    patched_page = (scan_dir / "pages" / "page-000.md").read_text(encoding="utf-8")
    assert patched_page.startswith("![Fig 3](assets/p1_vlm1.png)")
    patched_doc = json.loads((scan_dir / "document.json").read_text(encoding="utf-8"))
    assert patched_doc["figures"][0]["bbox"] == [72.0, 520.0, 332.0, 650.0]
    assert patched_doc["figures"][0]["file"] == "assets/p1_vlm1.png"
    patched_semantic = json.loads((scan_dir / "document.semantic.json").read_text(encoding="utf-8"))
    assert patched_semantic["nodes"][0]["file"] == "assets/p1_vlm1.png"
    patched_provenance = json.loads((scan_dir / "document.provenance.json").read_text(encoding="utf-8"))
    assert patched_provenance["prov"]["p1_vlm1"]["bbox"] == [72.0, 520.0, 332.0, 650.0]


def test_restore_scan_document_adds_missing_registry_figure_from_markdown_caption(tmp_path):
    module = _load_restore_module()
    scan_pdf = _make_scan_pdf(tmp_path / "scan.pdf")
    scan_dir = tmp_path / "results" / "model" / "out_scan" / "model" / "scan-doc"
    (scan_dir / "pages").mkdir(parents=True)
    _write_json(
        scan_dir / "document.json",
        {
            "pages": [{"page_index": 0, "content": [], "figures": [], "blocks": [], "tables": []}],
            "figures": [],
            "roles": {},
            "zones": [],
        },
    )
    caption = "**Fig 7. Caption that OCR kept but JSON missed.** body"
    (scan_dir / "document.md").write_text(f"<!-- page 1 -->\n\n{caption}\n", encoding="utf-8")
    (scan_dir / "pages" / "page-000.md").write_text(caption + "\n", encoding="utf-8")
    templates = [
        module.FigureTemplate(
            figure_id="p1_1",
            page=1,
            order=4,
            bbox=(72.0, 520.0, 332.0, 650.0),
            label="Fig 7",
            caption="Fig 7",
        )
    ]

    restored = module.restore_scan_document(scan_dir, templates, scan_pdf)

    assert [figure.figure_id for figure in restored] == ["p1_1"]
    patched_md = (scan_dir / "document.md").read_text(encoding="utf-8")
    assert patched_md.index("![Fig 7](assets/p1_1.png)") < patched_md.index("**Fig 7.")
    patched_doc = json.loads((scan_dir / "document.json").read_text(encoding="utf-8"))
    assert patched_doc["figures"][0]["id"] == "p1_1"
    assert patched_doc["pages"][0]["figures"] == ["p1_1"]
    assert patched_doc["roles"]["p1_1"]["by"] == "scan_template"
