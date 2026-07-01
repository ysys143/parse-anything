from __future__ import annotations

from odl_vl.pipeline.odl_extract import OdlParagraph
from odl_vl.pipeline.output import interleave_figures


def _block(text: str, top_y: float) -> OdlParagraph:
    # bbox = (x0, y0, x1, y1); y1 (index 3) is the top edge in PDF space (larger y = higher).
    return OdlParagraph(0, "paragraph", (0.0, top_y - 10, 100.0, top_y), text)


def _fig(fid: str, top_y: float, label=None) -> dict:
    return {"figure_id": fid, "file": f"assets/{fid}.png", "bbox": [0.0, top_y - 10, 50.0, top_y], "label": label}


def test_no_figs_returns_markdown_unchanged():
    assert interleave_figures("# Title\n\nbody", [], ()) == "# Title\n\nbody"


def test_figure_above_all_blocks_goes_to_top():
    md = "## Section A\n\ntext"
    blocks = (_block("Section A", 800.0),)
    out = interleave_figures(md, [_fig("f001", 900.0)], blocks)  # logo above the heading
    assert out.startswith("![figure](assets/f001.png)")
    assert "## Section A" in out and "text" in out  # body preserved


def test_figure_inserted_after_nearest_block_above():
    md = "## Section One\n\nfirst\n\n## Section Two\n\nsecond"
    blocks = (_block("Section One", 800.0), _block("Section Two", 500.0))
    out = interleave_figures(md, [_fig("f002", 480.0)], blocks)  # figure just below Section Two
    lines = out.split("\n")
    i_two = next(i for i, l in enumerate(lines) if "Section Two" in l)
    i_ref = next(i for i, l in enumerate(lines) if "assets/f002.png" in l)
    i_one = next(i for i, l in enumerate(lines) if "Section One" in l)
    assert i_one < i_two < i_ref  # ref lands after Section Two, not Section One


def test_anchor_matches_longest_prefix_when_vlm_resplits():
    # ODL joins two reading-order lines into one block; the VLM lays them out as a 2-column table.
    # A fixed-length prefix ("El titular o representante The owner...") matches no single line, so we
    # must shrink to the longest matching phrase ("El titular o representante") to anchor correctly.
    md = "El titular o representante | El cliente\n:--- | :---\nThe owner or representative | The Guest\n\n19/02/2026"
    blocks = (_block("El titular o representante The owner or representative", 416.8),)
    out = interleave_figures(md, [_fig("f002", 386.8)], blocks)
    lines = out.split("\n")
    i_anchor = next(i for i, l in enumerate(lines) if "El titular o representante" in l)
    i_ref = next(i for i, l in enumerate(lines) if "assets/f002.png" in l)
    i_date = next(i for i, l in enumerate(lines) if "19/02/2026" in l)
    assert i_anchor < i_ref <= i_date  # ref placed in reading order, not dumped at the end


def test_figure_not_inserted_inside_table():
    # Anchor lands on a table header row; the figure must go AFTER the whole table, never between
    # the header and its separator (which would break the Markdown table).
    md = "Header A | Header B\n:--- | :---\nrow1 | row2\n\nfooter"
    blocks = (_block("Header A Header B", 400.0),)
    out = interleave_figures(md, [_fig("f001", 386.0)], blocks)
    lines = out.split("\n")
    i_hdr = next(i for i, l in enumerate(lines) if "Header A" in l)
    assert ":---" in lines[i_hdr + 1]  # separator stays directly under the header -> table intact
    i_ref = next(i for i, l in enumerate(lines) if "assets/f001.png" in l)
    i_row = next(i for i, l in enumerate(lines) if "row1" in l)
    assert i_ref > i_row  # ref placed after the table body, not inside it


def test_anchor_text_missing_appends_at_end():
    md = "totally different VLM phrasing"
    blocks = (_block("Datos del Cliente", 500.0),)
    out = interleave_figures(md, [_fig("f001", 480.0)], blocks)
    assert out.endswith("![figure](assets/f001.png)")
    assert out.startswith("totally different")  # original body untouched


def test_no_blocks_appends_at_end():
    out = interleave_figures("body only", [_fig("f001", 480.0)], ())
    assert "body only" in out and out.strip().endswith("![figure](assets/f001.png)")


def test_label_used_as_alt_text():
    out = interleave_figures("x", [_fig("f001", 480.0, label="Figure 1")], ())
    assert "![Figure 1](assets/f001.png)" in out


def test_transcribed_text_preserved_loss_aware():
    # The VLM typed the signature as "Jaesol Shin"; interleaving must NOT remove it (loss-aware).
    md = "The Guest\n\nJaesol Shin\n\n19/02/2026"
    blocks = (_block("The Guest", 400.0),)
    out = interleave_figures(md, [_fig("f002", 386.0)], blocks)
    assert "Jaesol Shin" in out and "assets/f002.png" in out
