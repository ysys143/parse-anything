"""Page-furniture fixtures -- multi-page markdowns with running headers/footers, page-number leaks,
and unique body content, to test that strip_page_furniture removes repeated furniture (across document
types: journal footer, running header, repeated section header) WITHOUT eating varied body text.
Add a document type -> add a case.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FurnitureCase:
    name: str
    pages: dict[int, str]
    page_labels: dict[int, str | None] = field(default_factory=dict)
    removed: list[str] = field(default_factory=list)   # substrings that must be gone from every page
    kept: list[str] = field(default_factory=list)       # substrings that must survive somewhere


_BODIES = ["Perceptual decisions rely on corrective feedback.", "The world-updating model predicts a bias.",
           "Results show a clear retrospective effect.", "We discuss the Bayesian account.",
           "Methods used a maximum-likelihood fit.", "Conclusions and directions for future work."]


def _journal(n: int) -> dict[int, str]:
    foot = "PLOS Biology | https://doi.org/10.1371/journal.pbio.3002373 November 8, 2023 {p} / 6"
    return {i: f"{_BODIES[i]}\n\nPLOS BIOLOGY | Corrective feedback\n\n{foot.format(p=i + 1)}" for i in range(n)}


FURNITURE_CASES: list[FurnitureCase] = [
    # journal running footer (page number varies) + running header, varied body per page
    FurnitureCase("journal_header_footer", _journal(6),
                  removed=["PLOS Biology |", "PLOS BIOLOGY | Corrective feedback"],
                  kept=["Perceptual decisions", "Conclusions and directions"]),
    # a chapter/section heading repeated at each page top (running header) -> dropped; one-off kept
    FurnitureCase("repeated_section_header",
                  {0: "## 6 セメント産業\n\n本文A", 1: "## 6 セメント産業\n\nもっと本文", 2: "## 7 工作機械\n\n本文C"},
                  removed=["6 セメント産業"], kept=["## 7 工作機械", "本文A"]),
    # printed page number leaked as a bare line -> dropped via page_labels
    FurnitureCase("page_number_leak", {0: "Body one.\n\n128", 1: "Body two.\n\n129"},
                  page_labels={0: "128", 1: "129"}, removed=["128", "129"], kept=["Body one.", "Body two."]),
    # unique pages, nothing repeats -> nothing removed
    FurnitureCase("no_repetition", {0: "Alpha section content.", 1: "Beta section content.", 2: "Gamma section."},
                  kept=["Alpha section", "Beta section", "Gamma section"]),
]
