from __future__ import annotations

from odl_vl.pipeline.pageno import _resolve, printed_to_index


def test_offset_recovered_and_repeated_footnote_ignored():
    # printed pages 128..132 (offset 128); page 2 also carries a stray footnote "5" three times
    per_page = [[128], [129], [5, 5, 130], [131], [132]]
    assert _resolve(per_page, 5) == {0: "128", 1: "129", 2: "130", 3: "131", 4: "132"}


def test_missing_footer_is_extrapolated_from_offset():
    per_page = [[10], [], [12]]   # page 1 has no readable footer number
    assert _resolve(per_page, 3) == {0: "10", 1: "11", 2: "12"}


def test_no_numbers_returns_all_none():
    assert _resolve([[], [], []], 3) == {0: None, 1: None, 2: None}


def test_printed_to_index_inverse_first_wins():
    assert printed_to_index({0: "128", 1: "129", 2: "130"}) == {"128": 0, "129": 1, "130": 2}
    assert printed_to_index({2: "5", 0: "5"})["5"] == 0   # first occurrence wins
