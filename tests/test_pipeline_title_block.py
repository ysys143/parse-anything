from __future__ import annotations

from parse_anything.pipeline.title_block import detect_title_block, detect_title_block_gated


def _b(text, x0, y0, x1, y1):
    return {"text": text, "bbox": [x0, y0, x1, y1]}


def test_extracts_schneckenwelle_title_block_fields():
    # grid cells: label cell next to value cell, no colons (German drawing)
    blocks = [
        _b("Maßstab", 100, 100, 130, 110), _b("2:1", 132, 100, 150, 110),
        _b("Werkstoff", 100, 112, 135, 122), _b("16MnCr5", 137, 112, 175, 122),
        _b("Benennung", 100, 124, 135, 134), _b("Schneckenwelle", 137, 124, 200, 134),
    ]
    tb = detect_title_block(blocks)
    assert tb["scale"]["value"] == "2:1"
    assert tb["material"]["value"] == "16MnCr5"
    assert tb["title"]["value"] == "Schneckenwelle"


def test_value_paired_from_cell_below_when_none_to_the_right():
    blocks = [_b("축척", 0, 0, 20, 10), _b("1/12", 0, 12, 30, 22)]
    tb = detect_title_block(blocks)
    assert tb["scale"]["value"] == "1/12"


def test_region_gate_excludes_a_body_heading_far_from_the_title_block():
    # a 'Material' heading in the body must not be read as a title-block field when a region is given
    blocks = [_b("Material", 0, 0, 40, 10), _b("and Methods", 42, 0, 90, 10),
              _b("Maßstab", 500, 700, 530, 710), _b("2:1", 532, 700, 550, 710)]
    tb = detect_title_block(blocks, region=[480, 680, 600, 760])   # bottom-right frame only
    assert "material" not in tb and tb["scale"]["value"] == "2:1"


def test_unknown_labels_and_missing_values_yield_nothing():
    assert detect_title_block([_b("본문 문장", 0, 0, 100, 10)]) == {}      # no known key
    assert detect_title_block([_b("Werkstoff", 0, 0, 40, 10)]) == {}      # key but no value cell


def test_a_key_is_not_paired_with_another_key_as_its_value():
    # Maßstab | Werkstoff | 2:1 : Werkstoff is a key, so Maßstab's right value skips to nothing on the row;
    # each key resolves to a real value, never to another key
    blocks = [_b("Maßstab", 0, 0, 30, 10), _b("Werkstoff", 40, 0, 75, 10), _b("16MnCr5", 80, 0, 120, 10)]
    tb = detect_title_block(blocks)
    assert tb.get("material", {}).get("value") == "16MnCr5"
    # V2d: Maßstab must NOT reach past the Werkstoff key to steal 16MnCr5 -> scale has no value here
    assert "scale" not in tb


def test_v1_generic_english_aliases_need_a_region():
    # 'Scale'/'Material' are common prose words: without a region they must NOT match a title-block field
    prose = [_b("Scale", 0, 0, 30, 10), _b("bar", 35, 0, 60, 10),
             _b("Material", 0, 20, 40, 30), _b("and Methods", 45, 20, 100, 30)]
    assert detect_title_block(prose) == {}                       # region=None -> generic aliases off
    # with a region, the generic alias IS enabled (spatial title-block context)
    with_region = detect_title_block(prose, region=[-1, -1, 200, 40])
    assert with_region.get("scale", {}).get("value") == "bar"


def test_v1_drawing_specific_aliases_match_without_a_region():
    # Maßstab / 재질 are drawing-specific, safe to match anywhere
    tb = detect_title_block([_b("Maßstab", 0, 0, 30, 10), _b("2:1", 35, 0, 55, 10)])
    assert tb["scale"]["value"] == "2:1"


def test_v3_below_pairing_is_distance_bounded():
    # a key with no right value does not grab a far-below block
    blocks = [_b("Werkstoff", 0, 0, 40, 10), _b("무관한 하단 블록", 0, 900, 90, 920)]
    assert detect_title_block(blocks) == {}


def test_v4_gated_entry_auto_region_and_density():
    # a drawing page: title block clustered bottom-right; a 'Material' heading top-left must be excluded
    blocks = [
        _b("Material", 0, 0, 40, 10), _b("and Methods", 45, 0, 100, 10),          # body heading (top-left)
        _b("Maßstab", 600, 700, 640, 712), _b("2:1", 645, 700, 680, 712),          # title block (bottom-right)
        _b("Werkstoff", 600, 714, 650, 726), _b("16MnCr5", 655, 714, 720, 726),
        _b("frame", 0, 0, 1000, 1000),                                             # sets the page extent
    ]
    tb = detect_title_block_gated(blocks)                 # no region -> auto bottom-right quadrant
    assert tb["scale"]["value"] == "2:1" and tb["material"]["value"] == "16MnCr5"
    assert "and" not in {v.get("value") for v in tb.values()}   # top-left heading excluded


def test_v4_density_gate_suppresses_a_single_stray_field():
    # only one matched field on the page -> below min_fields -> {}
    blocks = [_b("Werkstoff", 600, 700, 650, 712), _b("16MnCr5", 655, 700, 720, 712),
              _b("frame", 0, 0, 1000, 1000)]
    assert detect_title_block_gated(blocks, min_fields=2) == {}
