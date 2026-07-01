from __future__ import annotations

from odl_vl.pipeline.output import _assemble_document


def test_stitches_midsentence_page_break_with_invisible_marker():
    doc = _assemble_document([("128", "本文が家電産業の"), ("129", "製造工程について。")])
    assert doc.startswith("<!-- page 128 -->")
    assert "家電産業の<!-- page 129 -->製造工程について。" in doc   # CJK join, marker invisibly between


def test_paragraph_break_when_sentence_completes_on_the_page():
    doc = _assemble_document([("1", "文が完成した。"), ("2", "新しい段落。")])
    assert "完成した。\n\n<!-- page 2 -->\n\n新しい段落。" in doc   # terminator -> break, marker on its own line


def test_does_not_stitch_a_continuation_into_a_heading_or_table():
    assert "<!-- page 2 -->\n\n## 第2章" in _assemble_document([("1", "未完の文"), ("2", "## 第2章")])
    assert "<!-- page 2 -->\n\n| a | b |" in _assemble_document([("1", "未完の文"), ("2", "| a | b |")])


def test_latin_text_joins_with_a_space():
    doc = _assemble_document([("1", "the quick brown"), ("2", "fox jumped.")])
    assert "the quick brown<!-- page 2 --> fox jumped." in doc   # space sep for non-CJK


def test_url_split_across_a_page_break_is_rejoined():
    # a URL wrapped across the page boundary ('https://doi.' + 'org/...') must rejoin, not stay cut
    out = _assemble_document([("1", "available at: (https://doi."),
                              ("2", "org/10.5281/zenodo.8427373). All other data.")])
    assert "https://doi.org/10.5281/zenodo.8427373" in out


def test_complete_doi_line_is_not_merged_into_the_next_body():
    # a figure-source DOI line ends with a complete URL -> the following body stays a separate block
    out = _assemble_document([("1", "https://doi.org/10.1371/journal.pbio.3002373.g001"),
                              ("2", "value becomes low as evidence weakens.")])
    assert ".g001\n\n" in out.replace("<!-- page 2 -->", "").replace("\n\n\n", "\n\n")
    assert "g001 value becomes low" not in " ".join(out.split())


def test_caption_opening_a_page_is_not_folded_into_prior_prose():
    # a caption is the first block of a full-page-figure page; it must stay its own block, not glue to
    # the previous page's unfinished sentence
    out = _assemble_document([("1", "we quantified the effect in both directions as follows"),
                              ("2", "Fig 2. Experimental design and definition. (A) A chain of episodes.")])
    assert "follows Fig 2. Experimental" not in " ".join(out.split())
    assert "Fig 2. Experimental design and definition." in out
