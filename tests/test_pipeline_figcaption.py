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
