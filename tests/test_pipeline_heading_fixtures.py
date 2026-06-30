from __future__ import annotations

import pytest

from fixtures.heading_cases import HEADING_CASES
from odl_vl.pipeline.numbering import classify_numbering
from odl_vl.pipeline.sections import _CAPTION_LEAD, _is_list_not_heading, _is_prose_not_heading


def _detects_as_heading(text: str) -> bool:
    """Mirror the detection in _assign_heading_levels: a recognized numbering prefix that survives the
    list / prose / caption guards."""
    nc = classify_numbering(text)
    return (nc is not None and not _is_list_not_heading(text, "")
            and not _is_prose_not_heading(text) and not _CAPTION_LEAD.match(text))


@pytest.mark.parametrize("case", HEADING_CASES, ids=lambda c: c.note or c.text[:20])
def test_heading_detection_generalizes_across_doc_types(case):
    assert _detects_as_heading(case.text) is case.is_heading, f"{case.note}: {case.text!r}"
