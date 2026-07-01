from __future__ import annotations

from odl_vl.pipeline.reflow import reflow_markdown


def test_cjk_softwrap_joins_without_space():
    md = "我が国の販売数量（輸出\n含む）6,874万トンに\nなっている。"
    assert reflow_markdown(md) == "我が国の販売数量（輸出含む）6,874万トンになっている。"


def test_latin_softwrap_joins_with_space():
    md = "Institutional causes of\nmacroeconomic volatility and\ngrowth."
    assert reflow_markdown(md) == "Institutional causes of macroeconomic volatility and growth."


def test_blank_line_is_a_paragraph_break():
    md = "first paragraph line\nwrapped.\n\nsecond paragraph."
    assert reflow_markdown(md) == "first paragraph line wrapped.\n\nsecond paragraph."


def test_table_rows_untouched():
    md = "| a | b |\n| --- | --- |\n| 1 | 2 |"
    assert reflow_markdown(md) == md  # every row starts with | -> never folded


def test_heading_not_folded_into():
    md = "# 6 セメント産業\n本文がここから始まる。"
    assert reflow_markdown(md) == "# 6 セメント産業\n本文がここから始まる。"


def test_section_heading_keeps_body_separate_but_body_wraps_fold():
    md = "（１）現状\n本文がここで\n折り返す。\n（２）次の項目"
    # （１）/（２） are sub-headings -> own line (body does NOT fold into them); the body's own
    # mid-sentence wrap still folds into one flowing line.
    assert reflow_markdown(md) == "（１）現状\n本文がここで折り返す。\n（２）次の項目"


def test_circled_number_heading_does_not_absorb_body():
    md = "①強み\n我が国の産業は強い。"
    assert reflow_markdown(md) == "①強み\n我が国の産業は強い。"


def test_hierarchical_toc_entries_stay_separate():
    # a table of contents: each entry ('3.', '3.1.', '3.2.') is its own line, not a wrap continuation,
    # so they must NOT be folded into one run-on ('...랩온어칩3.1. 현장진단...').
    md = ("3. 진단기기로서 미세유체공학 기반 랩온어칩\n"
          "3.1. 현장진단 시험 기기\n"
          "3.2. 질병 진단, 예후예측")
    assert reflow_markdown(md) == md
    # a decimal that is NOT a list marker ('3.5 mm', no trailing dot) still folds as a normal wrap
    assert reflow_markdown("두께는\n3.5 mm 이다.") == "두께는3.5 mm 이다."


def test_label_colon_starts_new_line_but_its_wrap_folds():
    # the real footnote: 備考 / numbered items / 資料 stay separate; each item's wrap folds in.
    md = (
        "備考：１．売上高は各企業の年度の単独決算のセメント部門の売上高\n"
        "合計。\n"
        "　　　２．輸出額はセメント及びクリンカ（中間製品）の合計額。\n"
        "資料：売上高、従業者は「（社）セメント協会統計」、輸出額、輸入額\n"
        "は財務省「日本貿易統計」。"
    )
    expected = (  # each item's mid-sentence wrap folds in; item starts keep their original indent
        "備考：１．売上高は各企業の年度の単独決算のセメント部門の売上高合計。\n"
        "　　　２．輸出額はセメント及びクリンカ（中間製品）の合計額。\n"
        "資料：売上高、従業者は「（社）セメント協会統計」、輸出額、輸入額は財務省「日本貿易統計」。"
    )
    assert reflow_markdown(md) == expected


def test_table_without_leading_pipes_not_corrupted():
    md = "Header A | Header B\n:--- | :---\nrow1 | row2"
    assert reflow_markdown(md) == md  # any line with a pipe is treated as a table row, never folded


def test_code_block_contents_untouched():
    md = "intro.\n```\nline one\nline two\n```\nafter."
    assert reflow_markdown(md) == md  # nothing inside the fence reflows


def test_image_and_figure_lines_are_preserved():
    md = "本文。\n![figure](assets/f001.png)\n[figure]\n続きの段落。"
    out = reflow_markdown(md)
    assert "![figure](assets/f001.png)" in out.split("\n")
    assert "[figure]" in out.split("\n")  # not folded into the image or the text
