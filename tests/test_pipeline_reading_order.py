from __future__ import annotations

from types import SimpleNamespace

from parse_anything.pipeline.assemble import _reorder_by_odl_order


def _page(*order_text):
    return SimpleNamespace(paragraphs=[SimpleNamespace(order=o, text=t) for o, t in order_text])


def test_reorders_sidebar_metadata_to_pdf_order():
    # ODL (PDF/UA) logical order: title, then sidebar metadata, then introduction
    page = _page((1, "Document Title Here Long Enough"), (2, "Citation: Author A 2023 Journal Vol"),
                 (3, "Copyright: 2023 Author B all rights reserved"),
                 (4, "Introduction begins here with enough words to match"))
    # VLM visual order put the sidebar AFTER the introduction (the bug)
    vlm = "\n\n".join(["Document Title Here Long Enough",
                       "Introduction begins here with enough words to match",
                       "Citation: Author A 2023 Journal Vol",
                       "Copyright: 2023 Author B all rights reserved"])
    blocks = [b.strip() for b in _reorder_by_odl_order(vlm, page).split("\n\n")]
    assert blocks[0].startswith("Document Title")
    assert blocks[1].startswith("Citation")
    assert blocks[2].startswith("Copyright")
    assert blocks[3].startswith("Introduction")


def test_single_column_page_is_a_noop():
    page = _page((1, "First paragraph alpha content here"), (2, "Second paragraph beta content here"),
                 (3, "Third paragraph gamma content here"), (4, "Fourth paragraph delta content here"))
    vlm = "\n\n".join(p.text for p in page.paragraphs)
    assert _reorder_by_odl_order(vlm, page).strip() == vlm


def test_sibling_blocks_align_to_distinct_paragraphs_not_the_first():
    # the bug this guards: blocks sharing an opening must consume DISTINCT ODL paragraphs
    page = _page((1, "which defines the stimuli distribution clearly"),
                 (2, "which defines the correct answer plainly here"),
                 (3, "which defines the sensory measurement noise level"),
                 (4, "Header line that anchors everything in place"))
    vlm = "\n\n".join(["Header line that anchors everything in place",
                       "which defines the stimuli distribution clearly",
                       "which defines the correct answer plainly here",
                       "which defines the sensory measurement noise level"])
    blocks = [b.strip() for b in _reorder_by_odl_order(vlm, page).split("\n\n")]
    assert blocks[-1].startswith("Header")
    assert "stimuli" in blocks[0] and "correct" in blocks[1] and "sensory" in blocks[2]


def test_unmatched_equation_stays_interleaved_with_its_prose():
    page = _page((1, "We incorporated the above deviation into the model"),
                 (2, "which defines the probability distribution of stimuli here"),
                 (3, "which defines the correct answer of the perceptual task"))
    vlm = "\n\n".join(["We incorporated the above deviation into the model",
                       "$$p(S|B) = N(S; B)$$",  # equation: no ODL text match -> anchored, not flung to the end
                       "which defines the probability distribution of stimuli here",
                       "$$CL = large$$",
                       "which defines the correct answer of the perceptual task"])
    blocks = [b.strip() for b in _reorder_by_odl_order(vlm, page).split("\n\n")]
    assert blocks == vlm.split("\n\n")  # order preserved (equations stay between their prose)


def test_unalignable_page_is_left_untouched():
    page = _page((1, "Totally unrelated ODL text one here now"), (2, "Totally unrelated ODL text two here now"))
    vlm = "\n\n".join(["Alpha block content here now", "Beta block content here now",
                       "Gamma block content here now", "Delta block content here now"])
    assert _reorder_by_odl_order(vlm, page).strip() == vlm.strip()


def test_align_matches_distinct_odl_blocks_one_to_one():
    from parse_anything.pipeline.textalign import align_vlm_to_odl, norm_block
    odl = sorted([(1, norm_block("which defines the stimuli distribution clearly")),
                  (2, norm_block("which defines the correct answer plainly here")),
                  (3, norm_block("Header line that anchors everything in place"))])
    blocks = ["Header line that anchors everything in place",
              "which defines the stimuli distribution clearly",
              "which defines the correct answer plainly here"]
    ms = align_vlm_to_odl(blocks, odl)
    assert [m.order for m in ms] == [3, 1, 2]  # distinct, siblings do not collide on 1


def test_align_leaves_low_prefix_block_unmatched():
    from parse_anything.pipeline.textalign import align_vlm_to_odl, norm_block
    odl = [(1, norm_block("We incorporated the deviation into the model somehow"))]
    blocks = ["We incorporated the deviation into the model somehow", "$$p(S|B) = N(S; B)$$"]
    ms = align_vlm_to_odl(blocks, odl)
    assert ms[0].order == 1 and ms[1].order is None
