from __future__ import annotations

from odl_vl.pipeline.run import DocumentResult, PageOutcome
from odl_vl.pipeline.scorecard import PageGold, score_document


def _result() -> DocumentResult:
    return DocumentResult(
        (
            PageOutcome(0, "oracle_vlm", True, "totals 1,234,567 and 89", 10.0, ("unsourced_number:9999999",)),
            PageOutcome(1, "deterministic", False, "plain prose", 1.0, ()),
        )
    )


def test_numeric_recall_counts_expected_numbers_present():
    golden = [PageGold(0, expected_numbers=("1,234,567", "89", "0")), PageGold(1)]
    sc = score_document(golden, _result())
    assert sc["numeric_hit"] == 2 and sc["numeric_total"] == 3  # "0" is absent
    assert abs(sc["numeric_recall"] - 2 / 3) < 1e-9


def test_routing_accuracy_compares_expected_route():
    golden = [PageGold(0, expected_route="oracle_vlm"), PageGold(1, expected_route="scan_vlm")]
    sc = score_document(golden, _result())
    assert sc["routing_accuracy"] == 0.5  # page 0 matches, page 1 (deterministic vs scan) does not


def test_flag_summary_aggregates_by_flag_kind():
    sc = score_document([], _result())
    assert sc["flagged_pages"] == 1
    assert sc["flag_counts"] == {"unsourced_number": 1}


def test_empty_golden_yields_none_ratios():
    sc = score_document([], _result())
    assert sc["numeric_recall"] is None and sc["routing_accuracy"] is None
