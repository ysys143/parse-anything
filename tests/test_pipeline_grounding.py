from __future__ import annotations

from parse_anything.pipeline.grounding import build_grounded_prompt
from parse_anything.pipeline.odl_extract import OdlPage, OdlParagraph, OdlTable


def test_grounded_prompt_injects_both_deterministic_sources():
    table = OdlTable(0, 2, 2, (50, 50, 400, 200), (("H", "V"), ("a", "1")), label="표 1")
    page = OdlPage(0, "text", (table,), (), paragraphs=(OdlParagraph(0, "heading", (10, 700, 400, 720), "Title"),))
    prompt = build_grounded_prompt("BASE_PROMPT", "authoritative value 1,234,567 here", page)

    assert "BASE_PROMPT" in prompt
    assert "1,234,567" in prompt and "NEVER alter a number" in prompt   # pypdfium2 value authority
    assert "Title" in prompt and "H | V" in prompt                       # ODL structure (heading + table grid)


def test_grounded_prompt_is_noop_without_text_layer():
    # A scan has no text layer -> nothing to ground with -> base prompt unchanged.
    assert build_grounded_prompt("BASE_PROMPT", "   ") == "BASE_PROMPT"
