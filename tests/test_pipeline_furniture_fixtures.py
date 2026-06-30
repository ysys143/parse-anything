from __future__ import annotations

import pytest

from fixtures.furniture_cases import FURNITURE_CASES
from odl_vl.pipeline.sections import strip_page_furniture


@pytest.mark.parametrize("case", FURNITURE_CASES, ids=lambda c: c.name)
def test_furniture_removal_generalizes_across_doc_types(case):
    out = strip_page_furniture(dict(case.pages), dict(case.page_labels))
    joined = "\n".join(out[i] for i in sorted(out))
    for r in case.removed:
        assert r not in joined, f"{case.name}: {r!r} should have been removed"
    for k in case.kept:
        assert k in joined, f"{case.name}: {k!r} should have survived"
