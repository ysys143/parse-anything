from __future__ import annotations

from odl_vl.pipeline.arithmetic import check_table_arithmetic


def test_arithmetic_invariant_holds():
    cells = [["item", "amount"], ["a", "100"], ["b", "200"], ["합계", "300"]]
    result = check_table_arithmetic(cells)
    assert result is not None and result["ok"] is True
    assert result["checks"][0]["total"] == 300.0 and result["checks"][0]["line_sum"] == 300.0


def test_arithmetic_break_flagged():
    cells = [["item", "amount"], ["a", "1,000"], ["b", "2,000"], ["Total", "3,500"]]  # 3000 != 3500
    result = check_table_arithmetic(cells)
    assert result is not None and result["ok"] is False
    assert result["checks"][0]["residual"] == 500.0


def test_no_total_row_returns_none():
    # Not a financial/total table -> the guard does not apply (never a universal check, F7).
    assert check_table_arithmetic([["item", "amount"], ["a", "100"], ["b", "200"]]) is None
    assert check_table_arithmetic([["H", "V"], ["a", "1"]]) is None
