from __future__ import annotations

from parse_anything.pipeline.guards import (
    extract_numbers,
    normalize_number,
    ratio_holds,
    source_gate,
    sum_residual,
)


def test_normalize_strips_grouping_commas():
    assert normalize_number(" 1,234,567 ") == "1234567"
    assert normalize_number("42") == "42"


def test_extract_numbers_in_order_with_min_value():
    text = "qty 3 unit 1,234,567 total 3,703,701 note 12"
    assert extract_numbers(text) == ["3", "1234567", "3703701", "12"]
    assert extract_numbers(text, min_value=1_000_000) == ["1234567", "3703701"]


def test_source_gate_flags_only_values_absent_from_source():
    # F5: every emitted value must exist in the deterministic source; fabrications are flagged.
    source = ["1,234,567", "3,703,701", "10,000,000"]
    emitted = ["1234567", "3703701", "9999999", "10000000"]
    assert source_gate(emitted, source) == ["9999999"]


def test_source_gate_passes_all_when_grounded():
    source = ["100", "200"]
    assert source_gate(["100", "200"], source) == []


def test_sum_residual_detects_unreconciled_total():
    assert sum_residual([10.0, 20.0, 30.0], 60.0) == 0.0
    assert sum_residual([10.0, 20.0, 30.0], 65.0) == 5.0


def test_ratio_holds_for_vat_like_relationship():
    # derived = base * 1.1 (e.g. VAT-inclusive vs exclusive). Synthetic values, not real data.
    assert ratio_holds(1_000_000.0, 1_100_000.0, 1.1)
    assert not ratio_holds(1_000_000.0, 1_200_000.0, 1.1)
