from __future__ import annotations

from parse_anything.pipeline.output import _extract_document_fields


def _b(text, x0, y0, x1, y1, page=1):
    return {"text": text, "bbox": [x0, y0, x1, y1], "page": page}


def test_prose_yields_no_extractions():
    # a normal report page: no colon KV density, no Ø/R/± dims, no title-block keys -> nothing fires
    blocks = [_b("본 연구는 다음을 분석한다.", 0, 0, 300, 12),
              _b("결과는 유의미했다.", 0, 20, 200, 32),
              _b("표 1은 요약을 보여준다.", 0, 40, 220, 52)]
    assert _extract_document_fields(blocks) == {}


def test_form_page_surfaces_form_fields():
    blocks = [
        _b("성명:", 0, 0, 30, 10), _b("육도연", 35, 0, 80, 10),
        _b("전화:", 0, 15, 30, 25), _b("010-1234", 35, 15, 90, 25),
        _b("주소:", 0, 30, 30, 40), _b("대전", 35, 30, 70, 40),
    ]
    ex = _extract_document_fields(blocks)
    assert "form_fields" in ex and ex["form_fields"][0]["page"] == 1
    labels = {f["label"] for f in ex["form_fields"][0]["fields"]}
    assert {"성명", "전화", "주소"} <= labels


def test_drawing_page_surfaces_dimensions_and_title_block():
    blocks = [
        _b("Ø17", 100, 100, 130, 110), _b("R50", 140, 100, 165, 110), _b("114.5", 100, 120, 140, 130),
        _b("Maßstab", 600, 700, 640, 712), _b("2:1", 645, 700, 680, 712),
        _b("Werkstoff", 600, 714, 650, 726), _b("16MnCr5", 655, 714, 720, 726),
        _b("frame", 0, 0, 1000, 1000),
    ]
    ex = _extract_document_fields(blocks)
    assert "dimensions" in ex
    dim_vals = {d["value"] for d in ex["dimensions"][0]["dimensions"]}
    assert "Ø17" in dim_vals and "R50" in dim_vals
    assert "title_block" in ex and ex["title_block"][0]["fields"]["scale"]["value"] == "2:1"


def test_pages_are_kept_separate():
    blocks = [_b("성명:", 0, 0, 30, 10, page=2), _b("육도연", 35, 0, 80, 10, page=2),
              _b("전화:", 0, 15, 30, 25, page=2), _b("010", 35, 15, 60, 25, page=2),
              _b("주소:", 0, 30, 30, 40, page=2), _b("대전", 35, 30, 70, 40, page=2)]
    ex = _extract_document_fields(blocks)
    assert ex["form_fields"][0]["page"] == 2


def test_statistics_prose_page_surfaces_no_dimensions():
    # wiring must not emit phantom dimensions on a science page (R-squared, ±, bare numbers)
    blocks = [_b("model fit R2 was high", 0, 0, 200, 10),
              _b("mean 0.89 ± 0.03 across", 0, 20, 200, 30),
              _b("500 samples over 12 runs", 0, 40, 200, 50)]
    ex = _extract_document_fields(blocks)
    assert "dimensions" not in ex


def test_title_block_only_on_a_page_that_has_dimensions():
    # a Korean recipe-like bottom-right (재료/날짜) WITHOUT any drawing dimensions -> no title_block
    recipe = [_b("재료", 600, 700, 640, 712), _b("밀가루", 645, 700, 700, 712),
              _b("날짜", 600, 714, 640, 726), _b("2026-07-06", 645, 714, 720, 726),
              _b("frame", 0, 0, 1000, 1000)]
    assert "title_block" not in _extract_document_fields(recipe)
