from __future__ import annotations

from odl_vl.pipeline.output import interleave_figures


def _fig(label, caption, bbox=(0.0, 0.0, 100.0, 700.0)):
    return {"label": label, "caption": caption, "file": f"assets/{label}.png", "bbox": list(bbox)}


def test_recovers_dropped_caption_on_empty_page():
    # a full-page figure leaves the page empty in the transcription; the bound caption is re-emitted
    out = interleave_figures("", [_fig("Fig 2", "Fig 2. Experimental design and definition.")], ())
    assert "![Fig 2]" in out
    assert "Fig 2. Experimental design and definition." in out


def test_does_not_duplicate_an_already_transcribed_caption():
    md = "Fig 1. Two possible scenarios for what humans learn.\n\nbody text"
    out = interleave_figures(md, [_fig("Fig 1", "Fig 1. Two possible scenarios for what humans learn.")], ())
    assert out.count("Fig 1. Two possible scenarios") == 1


def test_skips_a_caption_mis_bound_to_a_body_paragraph():
    # caption that does not start with the figure label is a mis-binding -> not emitted into the body
    out = interleave_figures("body text", [_fig("Fig 6", "Having confirmed the distinct predictions.")], ())
    assert "Having confirmed" not in out
    assert "![Fig 6]" in out


def test_bold_vlm_caption_suppresses_the_recovered_one():
    # the VLM renders the caption bold; the recovery must recognise it (markdown-insensitive) -> no dup
    md = "**Fig 7. Ex post simulation results.** (A-C) content that is sufficiently long here."
    out = interleave_figures(md, [_fig("Fig 7", "Fig 7. Ex post simulation results. (A-C) content")], ())
    assert out.count("Fig 7. Ex post simulation results") == 1


def test_caption_bold_is_normalized_consistently():
    from odl_vl.pipeline.output import _normalize_captions
    assert _normalize_captions("Fig 2. Title here. (A) panel.").startswith("**Fig 2. Title here.**")
    # already-bold stays bold; inline italics in the body survive
    out = _normalize_captions("**Fig 7. Results.** (A-C) across *toi* episodes.")
    assert out.startswith("**Fig 7. Results.**") and "*toi*" in out
    assert _normalize_captions("S1 Fig. Schematic of BMBU. (A) x.").startswith("**S1 Fig. Schematic of BMBU.**")
    # a colon label separator ('Figure 3:') is bolded like a period one
    assert _normalize_captions("Figure 3: Neural activity from cells. a) foo").startswith(
        "**Figure 3: Neural activity from cells.**")
    # a title with NO terminal period (a short caption) bolds the whole label+title
    assert _normalize_captions("Table 1. Hyperparameter range of the methods") == (
        "**Table 1. Hyperparameter range of the methods**")
    # an all-caps label with no separator ('FIGURE 1 Title.')
    assert _normalize_captions("FIGURE 1 Two dimensional subspaces. Panel a shows.").startswith(
        "**FIGURE 1 Two dimensional subspaces.**")
    # a title ends at a SENTENCE period, not a mid-token one: an inline URL is not split by the bold
    url = "http://www." + "example.com/x"
    out = _normalize_captions("Fig 8. Overview (" + url + ")")
    assert out.count("**") == 2 and url in out   # exactly one bold span, URL intact (no ** mid-token)
    # ordinary prose is untouched (label not at line start)
    assert _normalize_captions("The figure 2 shows a trend.") == "The figure 2 shows a trend."


def test_display_equation_strips_are_dropped_but_real_figures_kept():
    from odl_vl.pipeline.output import _text_line_strip, _tiny_figure
    # a thin horizontal band a text line or two tall = a display equation ODL mis-detected as a figure
    assert _text_line_strip([100, 500, 456, 527])      # 356 x 27 -> equation strip
    assert _text_line_strip([100, 500, 503, 518])      # 403 x 18 -> equation strip
    # real figures (tall) are kept; a small square icon is left to _tiny_figure, not this filter
    assert not _text_line_strip([100, 100, 568, 350])  # 468 x 250 -> real figure
    assert not _text_line_strip([100, 100, 190, 145])  # 90 x 45  -> tall enough, real figure
    assert not _text_line_strip([100, 100, 130, 122])  # 30 x 22  -> square-ish (a _tiny_figure case)
    assert not _text_line_strip(None)


def test_equation_strip_is_only_dropped_on_a_page_with_math():
    # height/shape alone must not drop a figure: a thin strip is a display-equation crop ONLY when the
    # page actually contains display math (the VLM transcribed the equation as LaTeX).
    from odl_vl.pipeline.output import _page_has_math
    assert _page_has_math(r"text $$x = \sum_i a_i$$ more text")       # a display equation present
    assert _page_has_math("dense $a$ $b$ $c$ $d$ inline $e$ math $f$")  # dense inline math
    assert not _page_has_math("A wide thin figure caption with no math at all here.")  # no math -> keep strip
    assert not _page_has_math("")


def test_labels_a_bare_figure_source_doi():
    from odl_vl.pipeline.output import _label_figure_sources
    assert _label_figure_sources("https://doi.org/10.1371/journal.pbio.3002373.g007").startswith(
        "Source: https://doi.org/10.1371/journal.pbio.3002373.g007")
    # a DOI embedded in prose (not a bare source line) is left untouched
    assert _label_figure_sources("see https://doi.org/x.g007 here") == "see https://doi.org/x.g007 here"


def test_restores_misread_panel_label_but_keeps_copyright():
    from odl_vl.pipeline.output import _restore_panel_labels
    assert _restore_panel_labels("as in (B) and ©.") == "as in (B) and (C)."
    assert _restore_panel_labels("black cube. © The 3D state") == "black cube. (C) The 3D state"
    assert _restore_panel_labels("**Copyright:** © 2023 Lee et al.") == "**Copyright:** © 2023 Lee et al."


def test_escapes_currency_dollar_but_not_math():
    from odl_vl.pipeline.output import _escape_currency
    assert _escape_currency("paid $10/h.") == "paid \\$10/h."
    assert _escape_currency("cost $1,000.50 total") == "cost \\$1,000.50 total"
    assert _escape_currency("was $5 \\times 2") == "was $5 \\times 2"      # math token kept
    assert _escape_currency("$B_t$ and $m'_t$") == "$B_t$ and $m'_t$"       # math kept
