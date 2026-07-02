from __future__ import annotations

from parse_anything.pipeline.output import _assemble_document


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


def test_consolidate_merges_split_caption_and_source_into_figure_unit():
    from parse_anything.pipeline.output import _consolidate_figure_units
    md = "\n\n".join([
        "**Fig 2. Title.** (A) head part ending mid",       # caption head, above the image
        "![Fig 2](assets/f.png)",                            # image
        "<!-- page 3 -->",                                   # a page marker that split the caption
        "sentence continues (B) tail part here.",            # caption tail, below the image
        "Source: https://doi.org/x.g002",                    # figure source
        "Body paragraph after the figure.",                  # body (must survive, untouched)
    ])
    blocks = _consolidate_figure_units(md).split("\n\n")
    assert blocks[0].startswith("![Fig 2]")                  # image first
    assert "**Fig 2. Title.**" in blocks[1] and "tail part here." in blocks[1] and "<!-- page" not in blocks[1]
    assert "Source: https://doi.org/x.g002" in blocks[1]     # source attached to the caption (no blank line)
    assert "Body paragraph after the figure." in "\n\n".join(blocks)


def test_consolidate_leaves_a_sourceless_figure_untouched():
    from parse_anything.pipeline.output import _consolidate_figure_units
    md = "![Fig 9](a.png)\n\n**Fig 9. X.** caption text\n\nbody text here now"
    assert _consolidate_figure_units(md) == md  # no Source line nearby -> no-op, never eats the body


def test_stitch_rejoins_a_paragraph_split_around_a_figure():
    from parse_anything.pipeline.output import _stitch_broken_paragraphs
    md = "the class boundary at the\n\nunbiased value (B=0) and does not update the choices"
    assert "boundary at the unbiased value" in _stitch_broken_paragraphs(md)


def test_stitch_does_not_merge_an_equation_or_a_new_paragraph():
    from parse_anything.pipeline.output import _stitch_broken_paragraphs
    md1 = "the class probabilities, as follows:\n\n$$p(x) = 1$$"    # display equation -> keep separate
    assert _stitch_broken_paragraphs(md1) == md1
    md2 = "This sentence is complete.\n\nThe next paragraph begins here."  # capital start -> new paragraph
    assert _stitch_broken_paragraphs(md2) == md2


def test_consolidate_below_merges_a_wrapped_caption_tail_and_source():
    # a caption BELOW the image that wraps (head ends mid-sentence, a lower-case tail follows) with a
    # Source after it -> head + tail + source fold into one caption unit (the Fig 1 arrangement).
    from parse_anything.pipeline.output import _consolidate_figure_units
    md = "\n\n".join([
        "![Fig 1](a.png)",                                   # image first
        "**Fig 1. Title.** the black arrows depict, where a decision-maker",   # caption head, mid-sentence
        "computes its expected value and makes a choice C.",  # caption tail, wraps in lower case
        "Source: https://doi.org/x.g001",                    # source -> proof this is a caption unit
    ])
    cap = next(b for b in _consolidate_figure_units(md).split("\n\n") if b.startswith("**Fig 1."))
    assert "computes its expected value" in cap and "g001" in cap   # tail + source folded into the caption


def test_figure_unit_floats_out_of_a_paragraph_it_splits():
    # a body paragraph split around a floating figure (marker + image + caption run between its halves) is
    # completed across the run, and the figure re-emerges AFTER the finished paragraph (the Fig 2 case).
    from parse_anything.pipeline.output import _stitch_broken_paragraphs
    md = "\n\n".join([
        "the PSEs of the retrospective",                     # body head, ends mid-sentence
        "<!-- page 10 -->",                                  # page marker, part of the float run
        "![Fig 2](f.png)",                                  # image
        "**Fig 2. Title.** caption text. Source: https://doi.org/x.g002",  # caption + inline source
        "and prospective trials quantify the biases.",       # body tail, continues in lower case
        "# Next Section",
    ])
    blocks = _stitch_broken_paragraphs(md).split("\n\n")
    assert any("the PSEs of the retrospective and prospective trials quantify the biases." in b for b in blocks)
    para_i = next(i for i, b in enumerate(blocks) if "the PSEs of the retrospective and prospective" in b)
    img_i = next(i for i, b in enumerate(blocks) if b.startswith("![Fig 2]"))
    assert para_i < img_i                                    # the figure floats after the completed paragraph
    assert "g002 and prospective" not in "\n\n".join(blocks)  # caption keeps its own source, no body glued


def test_adjacent_cjk_blocks_are_not_merged():
    from parse_anything.pipeline.output import _stitch_broken_paragraphs
    # a grid of Korean cards (each a complete label + description, no terminal period) must stay separate:
    # CJK has no letter case, so a 'lower-case = continuation' signal cannot tell items apart -- two merely
    # ADJACENT CJK blocks are never merged.
    md = "로봇개 (Quadruped) 순찰 및 점검 수행 고도화\n\n휴머노이드 (Humanoid) 작업 자동화 극대화"
    assert _stitch_broken_paragraphs(md) == md


def test_cjk_paragraph_split_by_a_figure_is_still_rejoined():
    from parse_anything.pipeline.output import _stitch_broken_paragraphs
    # but when a figure floats between the two halves of ONE Korean paragraph, that IS a real split -> join
    md = "\n\n".join([
        "경계는 다음 값으로 이동한다",                              # Korean head, ends mid-sentence
        "![Fig 1](f.png)",
        "**그림 1. 제목.** 캡션. Source: https://doi.org/x.g001",
        "즉 편향되지 않은 값이 된다.",                              # Korean tail, continues the sentence
    ])
    out = _stitch_broken_paragraphs(md)
    assert "경계는 다음 값으로 이동한다즉 편향되지 않은 값이 된다." in out   # rejoined across the floated figure


def test_stitch_never_glues_body_onto_a_figure_unit():
    from parse_anything.pipeline.output import _stitch_broken_paragraphs
    md = "![Fig 3](f.png)\n\n**Fig 3. Title.** caption. Source: https://doi.org/x.g003\n\nand more body text here"
    out = _stitch_broken_paragraphs(md)
    assert "g003 and more body" not in out                   # a figure unit never absorbs a body block
    assert "and more body text here" in out                  # body survives as its own block


def test_image_glued_to_trailing_body_is_detached_and_paragraph_reflows():
    # interleave glues an image to the body block just below it (the paragraph above the figure, which
    # wraps around it). Detach the image (text above the figure comes first), then the reflow completes the
    # paragraph across the figure and floats the figure after it -- the Fig 6 arrangement.
    from parse_anything.pipeline.output import (_detach_image_from_trailing_text,
                                        _consolidate_figure_units, _stitch_broken_paragraphs)
    md = "\n\n".join([
        "# Section",
        "![Fig 6](f.png)\nHaving confirmed the results, the model sets the boundary at the",  # image + body head
        "**Fig 6. Title.** caption text. Source: https://doi.org/x.g006",
        "unbiased value and does not update.",               # body tail, continues in lower case
    ])
    out = _stitch_broken_paragraphs(_consolidate_figure_units(_detach_image_from_trailing_text(md)))
    assert "sets the boundary at the unbiased value and does not update." in out   # paragraph reflowed whole
    assert "![Fig 6](f.png)\nHaving confirmed" not in out                          # image detached from body
    blocks = out.split("\n\n")
    para_i = next(i for i, b in enumerate(blocks) if "sets the boundary at the unbiased value" in b)
    img_i = next(i for i, b in enumerate(blocks) if b.startswith("![Fig 6]"))
    assert para_i < img_i                                                          # figure floats after the paragraph
