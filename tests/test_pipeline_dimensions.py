from __future__ import annotations

from parse_anything.pipeline.dimensions import detect_dimensions, detect_dimensions_gated


def _t(text, bbox=None):
    return {"text": text, "bbox": bbox}


def _kinds(text):
    return [(d["value"], d["kind"]) for d in detect_dimensions([_t(text)])]


def test_shaped_dimensions_are_classified():
    # values from the schneckenwelle golden drawing
    assert ("Ø17", "diameter") in _kinds("Ø17 k6")
    assert ("Ø32-0.1", "diameter") in _kinds("Ø32-0.1")
    assert ("R50", "radius") in _kinds("R50")
    assert ("17°", "angle") in _kinds("17°")
    assert ("± 0.25", "tolerance") in _kinds("47 ± 0.25")   # spacing preserved as printed


def test_diameter_absorbs_its_own_tolerance_suffix_not_double_counted():
    dims = detect_dimensions([_t("Ø32-0.1")])
    assert dims == [{"value": "Ø32-0.1", "kind": "diameter", "bbox": None}]  # one entry, not Ø32 + length 0.1


def test_lengths_need_two_shaped_dims_no_single_stray_cascade():
    # V4: a lone stray shaped ("R5") must NOT turn every bare number on the page into a "length"
    mixed = [_t("Order R5 confirmed"), _t("Invoice 4500"), _t("Page 3"), _t("Year 2024")]
    kinds = {(d["value"], d["kind"]) for d in detect_dimensions(mixed)}
    assert ("R5", "radius") in kinds
    assert not any(k == "length" for _, k in kinds)          # no cascade
    # with real drawing context (>=2 shaped), bare lengths ARE emitted
    drawing = [_t("Ø17"), _t("R50"), _t("114.5"), _t("50.5")]
    dk = {(d["value"], d["kind"]) for d in detect_dimensions(drawing)}
    assert ("114.5", "length") in dk and ("50.5", "length") in dk


def test_v4b_length_regex_does_not_split_thousands_time_or_phone():
    # under drawing context, a thousands-separated number stays whole; times/phones don't become lengths
    ctx = [_t("Ø17"), _t("R50")]  # establish drawing context
    assert ("12,345", "length") in {(d["value"], d["kind"]) for d in detect_dimensions(ctx + [_t("12,345")])}
    assert not any(k == "length" for _, k in
                   {(d["value"], d["kind"]) for d in detect_dimensions(ctx + [_t("16:9")])} if _[0] in {"16", "9"})
    phone = {d["value"] for d in detect_dimensions(ctx + [_t("010-1234-5678")]) if d["kind"] == "length"}
    assert "010-1234" not in phone    # the signed suffix no longer absorbs "010-1234" as one dimension
    # (residual, documented: the bare pieces 010/1234/5678 can still appear -- a title-block gate is B3)


def test_v2_angle_excludes_temperature_and_coordinates():
    assert _kinds("20°C") == []          # celsius, not an angle
    assert _kinds("37°N") == []          # latitude, not an angle
    assert ("45°", "angle") in _kinds("45°")
    assert ("30 degrees", "angle") in _kinds("a 30 degrees turn")  # plural now matched


def test_patent_figure_is_a_clean_negative_control():
    toks = [_t("FIG. 3"), _t("Sheet 3 of 14"), _t("38"), _t("42"), _t("44"), _t("US 7,663,607 B2")]
    assert detect_dimensions(toks) == []


def test_1x45_degree_chamfer_reads_as_angle_only():
    assert _kinds("1x45°") == [("45°", "angle")]   # the "1" is not a stray length (followed by a letter)


def test_v5_gated_entry_requires_drawing_context():
    prose = [_t("note R1"), _t("total 4500"), _t("page 3")]   # 1 stray shaped -> not a drawing
    assert detect_dimensions_gated(prose) == []
    drawing = [_t("Ø17"), _t("R50"), _t("114.5")]
    assert len(detect_dimensions_gated(drawing)) >= 3         # diameter + radius + length
