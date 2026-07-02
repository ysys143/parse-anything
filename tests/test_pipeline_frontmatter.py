"""Cross-page marginal-column (front-matter sidebar) consolidation.

The detector is purely geometric (block x0/x1 vs the document's dominant body edge), so these fixtures
model the geometry, not any journal. The PLOS title page is the motivating case: a narrow left column
(Citation, Data Availability, Funding ...) that flows page 1 -> page 2 and splits a DOI URL across the
break. Consolidation must (a) pull that column out of the scattered body flow, (b) rejoin the split URL,
(c) emit it as one contiguous block before the first post-title heading, and (d) leave single-column or
isolated-left-block pages untouched.
"""
from dataclasses import dataclass

from parse_anything.pipeline.frontmatter import (
    consolidate_front_matter,
    marginal_paragraphs,
)


@dataclass(frozen=True)
class P:
    bbox: tuple[float, float, float, float]
    text: str
    order: int


# --- a PLOS-like two-page title front matter -------------------------------------------------------
def _plos_paras():
    return {
        0: (
            P((200, 620, 576, 660), "Corrective feedback guides human perceptual decision-making", 3),
            P((48, 436, 105, 448), "OPEN ACCESS", 6),
            P((36, 400, 183, 430), "Citation: Lee H-J, Lee H, Lim CY, Rhim I, Lee S-H (2023) Corrective feedback", 7),
            P((36, 81, 188, 300), "Data Availability Statement: Raw data, processed data files, and codes used in "
                                  "this study are publicly available on GitHub at: "
                                  "https://github.com/hyangjung-lee/lee_2023_corrective-fbk (https://doi.", 13),
            P((200, 595, 562, 610), "Hyang-Jung Lee, Heeseung Lee, Chae Young Lim, Issac Rhim, Sang-Hun Lee", 15),
            P((200, 497, 255, 510), "Abstract", 18),
            P((200, 266, 1028, 480), "Corrective feedback received on perceptual decisions is crucial for adjusting", 19),
        ),
        1: (
            P((200, 562, 576, 590), "Unlike PDM, value-based decision-making (VDM) involves making choices", 22),
            P((36, 674, 180, 700), "org/10.5281/zenodo.8427373). All other relevant data, including numerical data", 23),
            P((36, 525, 188, 640), "Funding: This research was supported by the Seoul National University", 24),
        ),
    }


def _plos_md():
    return {
        0: (
            "# Corrective feedback guides human perceptual decision-making by informing about the "
            "world state rather than rewarding its choice\n\n"
            "OPEN ACCESS\n\n"
            "Citation: Lee H-J, Lee H, Lim CY, Rhim I, Lee S-H (2023) Corrective feedback guides "
            "human perceptual decision-making. PLoS Biol 21(11): e3002373.\n\n"
            "Data Availability Statement: Raw data, processed data files, and codes used in this "
            "study are publicly available on GitHub at: "
            "https://github.com/hyangjung-lee/lee_2023_corrective-fbk (https://doi.\n\n"
            "Hyang-Jung Lee, Heeseung Lee, Chae Young Lim, Issac Rhim, Sang-Hun Lee\n\n"
            "# Abstract\n\n"
            "Corrective feedback received on perceptual decisions is crucial for adjusting "
            "decision-making strategies to improve future choices."
        ),
        1: (
            "Unlike PDM, value-based decision-making (VDM) involves making choices based on "
            "decision-makers' subjective preferences.\n\n"
            "org/10.5281/zenodo.8427373). All other relevant data, including numerical data "
            "underlying each figure, are within the paper and its Supporting Information files.\n\n"
            "Funding: This research was supported by the Seoul National University (SNU) Research Grant."
        ),
    }


def test_marginal_column_is_detected_as_a_cross_page_column():
    marginal, body = marginal_paragraphs(_plos_paras())
    assert body == 200
    assert set(marginal) == {0, 1}                       # the sidebar spans both pages
    assert [p.order for p in marginal[0]] == [6, 7, 13]  # OPEN ACCESS, Citation, Data Availability
    assert [p.order for p in marginal[1]] == [23, 24]    # zenodo-tail, Funding


def test_consolidation_groups_front_matter_before_abstract_and_rejoins_split_url():
    out = consolidate_front_matter(_plos_md(), _plos_paras())
    page0 = out[0]
    # the split DOI URL is rejoined into one token, no page-break gap
    assert "https://doi.org/10.5281/zenodo.8427373" in page0
    assert "https://doi.\n" not in page0
    # front matter sits after the title/authors and before the Abstract heading
    fm = page0.index("OPEN ACCESS")
    assert page0.index("Hyang-Jung Lee") < fm < page0.index("# Abstract")
    # Funding, which lived on page 1, is pulled up into the page-0 front-matter block
    assert "Funding: This research" in page0
    # ...and is therefore gone from the page-1 body flow, whose only survivor is the real body sentence
    assert "Funding" not in out[1]
    assert "zenodo" not in out[1]
    assert out[1].strip().startswith("Unlike PDM")


def test_field_odl_merged_into_a_neighbor_is_still_pulled():
    # 'Academic Editor' is embedded in the Citation ODL block, so no marginal paragraph starts with it
    # and the aligner leaves its md block unmatched. Sitting between two matched sidebar blocks, it must
    # still be pulled out with the rest of the front matter (not stranded at the top of the body).
    paras = {
        0: (
            P((200, 620, 576, 660), "Some Title Heading Line", 3),
            # ODL merged the Academic Editor line into the Citation block's text, so no marginal paragraph
            # STARTS with 'Academic Editor' (the aligner leaves that md block unmatched) -- but its words
            # live in the sidebar vocabulary, which is how the coverage test recognizes it as sidebar.
            P((36, 430, 183, 448), "Citation: Lee H-J et al. (2023). Academic Editor: Matthew F. S. "
                                   "Rushworth, Oxford University, UNITED KINGDOM.", 7),
            P((36, 300, 188, 420), "Data Availability Statement: Raw data are on GitHub.", 13),
            P((200, 497, 255, 510), "Abstract", 18),
            P((200, 260, 576, 480), "Body of the abstract goes here and spans the body column.", 19),
        ),
    }
    md = {
        0: (
            "# Some Title Heading Line\n\n"
            "Citation: Lee H-J et al. (2023).\n\n"
            "Academic Editor: Matthew F. S. Rushworth, Oxford University, UNITED KINGDOM\n\n"
            "Data Availability Statement: Raw data are on GitHub.\n\n"
            "# Abstract\n\nBody of the abstract goes here."
        ),
    }
    out = consolidate_front_matter(md, paras)
    page0 = out[0]
    # Academic Editor is inside the consolidated front-matter block, between Citation and Data Availability
    ce, cit, da = (page0.index(s) for s in ("Academic Editor", "Citation:", "Data Availability"))
    assert cit < ce < da < page0.index("# Abstract")
    # and it is not left orphaned above, ahead of the block
    assert page0.count("Academic Editor") == 1


def test_body_prose_wedged_between_two_sidebar_fields_is_not_pulled():
    # a body sentence the VLM happened to place between two matched sidebar fields (no structural block
    # between them) must NOT be swept into the front matter: its words are not in the sidebar vocabulary.
    paras = {
        0: (
            P((200, 620, 576, 660), "Title", 3),
            P((36, 430, 183, 448), "Funding: supported by SNU grant number 12345 and the NRF program.", 7),
            P((36, 300, 188, 420), "Competing interests: the authors declare no competing interests.", 13),
            P((200, 497, 255, 510), "Abstract", 18),
            P((200, 260, 576, 480), "Body of the abstract spans the full body column width here.", 19),
            P((200, 120, 576, 240), "Another wide body paragraph continues the abstract further down.", 20),
        ),
    }
    md = {
        0: (
            "# Title\n\n"
            "Funding: supported by SNU grant number 12345 and the NRF program.\n\n"
            "Perceptual decision-making means committing to a proposition about the world state.\n\n"
            "Competing interests: the authors declare no competing interests.\n\n"
            "# Abstract\n\nBody of the abstract."
        ),
    }
    out = consolidate_front_matter(md, paras)
    p0 = out[0]
    # Funding and Competing are now contiguous in the front-matter block: the body sentence was NOT swept
    # in between them...
    between = p0[p0.index("Funding:"):p0.index("Competing interests")]
    assert "Perceptual decision-making" not in between
    # ...and the body sentence is still present in the document (not lost)
    assert "Perceptual decision-making" in p0


def test_short_block_with_incidental_overlap_is_not_pulled():
    # a SHORT body line whose few tokens happen to sit in the (verbose) sidebar vocabulary must not slip
    # in on incidental overlap -- it is too short for coverage to be a real signal.
    paras = {
        0: (
            P((200, 620, 576, 660), "Title", 3),
            P((36, 430, 183, 448), "Data Availability: raw data files are on the public repository.", 7),
            P((36, 300, 188, 420), "Funding: research supported by the national grant program office.", 13),
            P((200, 497, 255, 510), "Abstract", 18),
            P((200, 260, 576, 480), "Abstract body sentence spans the full body column width here.", 19),
            P((200, 120, 576, 240), "Second wide body paragraph continues across the column further.", 20),
        ),
    }
    md = {
        0: (
            "# Title\n\n"
            "Data Availability: raw data files are on the public repository.\n\n"
            "Data on file.\n\n"                                     # 3 tokens, all in pool -> cov 1.0 but tiny
            "Funding: research supported by the national grant program office.\n\n"
            "# Abstract\n\nBody."
        ),
    }
    out = consolidate_front_matter(md, paras)
    between = out[0][out[0].index("Data Availability"):out[0].index("Funding:")]
    assert "Data on file." not in between                          # the short line is not swept into the block
    assert "Data on file." in out[0]                               # but it is not lost either


def test_figure_interposed_breaks_the_run_and_body_prose_stays():
    # page-2 shape: sidebar tail + Funding, THEN a figure (image + caption), THEN more sidebar, THEN the
    # figure's caption-body prose. The figure splits the sidebar run; caption-body (after the last matched
    # block) must stay with the figure, not be pulled into the front matter.
    paras = {
        # a realistic title page is body-dominant, so the document's dominant left edge is the body (200)
        0: (
            P((200, 700, 576, 720), "Title", 1),
            P((200, 600, 576, 640), "Abstract", 2),
            P((200, 500, 576, 560), "Abstract body sentence one runs the body column.", 3),
            P((200, 400, 576, 460), "Authors and affiliations line spanning the body column.", 4),
            P((200, 300, 576, 360), "Introduction body continues across the body column.", 5),
        ),
        1: (
            P((200, 562, 576, 590), "Unlike PDM, value-based decision-making involves choices.", 22),
            P((36, 674, 180, 700), "org/10.5281/zenodo.8427373). All other relevant data.", 23),
            P((36, 525, 188, 640), "Funding: This research was supported by SNU.", 24),
            P((36, 497, 179, 510), "Competing interests: none declared.", 26),
            P((36, 392, 180, 480), "Abbreviations: AICc, Akaike information criterion.", 27),
            P((200, 88, 576, 120), "computes its expected value by multiplying the probability.", 28),
        ),
    }
    md = {
        0: "# Title\n\n# Abstract\n\nAbstract body.",
        1: (
            "Unlike PDM, value-based decision-making involves choices.\n\n"
            "org/10.5281/zenodo.8427373). All other relevant data.\n\n"
            "Funding: This research was supported by SNU.\n\n"
            "![Fig 1](assets/p2_173.png)\n\n"
            "**Fig 1. Two possible scenarios.** (A) Decision-making platform for classification.\n\n"
            "Competing interests: none declared.\n\n"
            "Abbreviations: AICc, Akaike information criterion.\n\n"
            "computes its expected value by multiplying the probability that the choice is correct.\n\n"
            "Source: https://doi.org/10.1371/journal.pbio.3002373.g001"
        ),
    }
    out = consolidate_front_matter(md, paras)
    page1 = out[1]
    # the figure, its caption, its caption-body prose, and the real body sentence all remain on page 1
    assert "![Fig 1]" in page1
    assert "**Fig 1. Two possible scenarios.**" in page1
    assert "computes its expected value" in page1
    assert page1.strip().startswith("Unlike PDM")
    # the four sidebar blocks are pulled up into the page-0 front matter
    for tok in ("Funding:", "Competing interests", "Abbreviations", "zenodo"):
        assert tok in out[0]
        assert tok not in page1


def test_front_matter_fields_stay_distinct_blocks():
    out = consolidate_front_matter(_plos_md(), _plos_paras())
    blocks = out[0].split("\n\n")
    # distinct metadata fields are NOT merged together (each opens in upper case, ends in a terminator)
    assert any(b.startswith("OPEN ACCESS") for b in blocks)
    assert any(b.startswith("Citation:") for b in blocks)
    assert any(b.startswith("Funding:") for b in blocks)


# --- no-op guards ----------------------------------------------------------------------------------
def test_stitch_does_not_glue_a_complete_url_to_the_next_block():
    # a block ending in a COMPLETE url path segment must NOT be glued (no space) to whatever follows --
    # that would corrupt both texts ('repo' + 'g001' -> 'repog001'). Only a url cut mid-token ('.'/'/'
    # tail) rejoins.
    paras = {
        0: (
            P((200, 620, 576, 660), "Title", 3),
            P((36, 430, 183, 448), "Data Availability: code at https://github.com/lab/repo", 7),
            P((36, 300, 188, 420), "Funding: grant supports figure g001 and related work here.", 13),
            P((200, 497, 255, 510), "Abstract", 18),
            P((200, 260, 576, 480), "Body of the abstract spans the body column fully.", 19),
        ),
    }
    md = {
        0: (
            "# Title\n\n"
            "Data Availability: code at https://github.com/lab/repo\n\n"
            "Funding: grant supports figure g001 and related work here.\n\n"
            "# Abstract\n\nBody."
        ),
    }
    out = consolidate_front_matter(md, paras)
    assert "repoFunding" not in out[0] and "repog001" not in out[0]     # not glued
    assert "https://github.com/lab/repo" in out[0]                       # both texts intact
    assert "Funding: grant" in out[0]


def test_front_matter_goes_below_a_non_heading_title():
    # the VLM sometimes renders the title in bold rather than as a '#' heading. The front matter must land
    # AFTER that title block, never prepended above it.
    paras = {
        0: (
            P((200, 620, 576, 660), "Corrective feedback guides decision-making", 3),
            P((36, 430, 183, 448), "Citation: Lee H-J et al. (2023) PLoS Biol.", 7),
            P((36, 300, 188, 420), "Funding: supported by the SNU research grant program.", 13),
            P((200, 260, 576, 480), "Abstract body sentence spans the full body column here.", 19),
            P((200, 120, 576, 240), "A second body paragraph continues below across the column.", 20),
        ),
    }
    md = {
        0: (
            "**Corrective feedback guides decision-making**\n\n"      # bold title, not a '#' heading
            "Citation: Lee H-J et al. (2023) PLoS Biol.\n\n"
            "Funding: supported by the SNU research grant program.\n\n"
            "Abstract body sentence."
        ),
    }
    out = consolidate_front_matter(md, paras)
    assert out[0].index("**Corrective feedback") < out[0].index("Citation:")   # title stays on top
    assert out[0].index("Citation:") < out[0].index("Funding:")


def test_single_column_document_is_untouched():
    paras = {
        0: (
            P((200, 700, 576, 720), "# Title of a single column paper", 1),
            P((200, 600, 576, 680), "Body paragraph one runs the full column width like normal prose.", 2),
            P((200, 400, 576, 560), "Body paragraph two also spans the body column with nothing to its left.", 3),
        ),
    }
    md = {0: "# Title of a single column paper\n\nBody paragraph one.\n\nBody paragraph two."}
    marginal, _ = marginal_paragraphs(paras)
    assert marginal == {}
    assert consolidate_front_matter(md, paras) == md


def test_isolated_left_block_is_not_a_column():
    # a single centered display equation starts left of the body but is one block, not a stacked column
    paras = {
        0: (
            P((200, 700, 576, 720), "Body text above the equation continues here.", 1),
            P((125, 600, 475, 640), "x = a + b + c", 2),                # x0 < body but only ONE such block
            P((200, 400, 576, 560), "Body text below the equation resumes.", 3),
        ),
    }
    md = {0: "Body text above the equation continues here.\n\nx = a + b + c\n\nBody text below."}
    marginal, _ = marginal_paragraphs(paras)
    assert marginal == {}
    assert consolidate_front_matter(md, paras) == md


def test_two_column_body_is_not_mistaken_for_front_matter():
    # a genuine two-column body: a narrow-ish left column on EVERY page. Even if the mode picks the right
    # column as the body edge (so the left column looks "marginal" per page), a column present on the
    # majority of pages is body text, not front matter -> the pass must refuse (no-op).
    paras = {}
    md = {}
    for pi in range(4):
        paras[pi] = (
            P((50, 700, 280, 720), f"left column block A on page {pi}", pi * 10 + 1),
            P((50, 500, 280, 560), f"left column block B on page {pi}", pi * 10 + 2),
            P((300, 700, 560, 720), f"right column block A on page {pi}", pi * 10 + 3),
            P((300, 500, 560, 560), f"right column block B on page {pi}", pi * 10 + 4),
            P((300, 300, 560, 360), f"right column block C on page {pi}", pi * 10 + 5),
        )
        md[pi] = f"Left A p{pi}\n\nLeft B p{pi}\n\nRight A p{pi}\n\nRight B p{pi}\n\nRight C p{pi}"
    marginal, _ = marginal_paragraphs(paras)
    assert marginal == {}                                # pervasive column -> not front matter
    assert consolidate_front_matter(md, paras) == md


def test_wide_left_starting_blocks_are_not_a_marginal_column():
    # figure caption + source that begin slightly left (x0=171) but span across the body -> NOT marginal
    paras = {
        0: (
            P((200, 700, 576, 720), "Body sentence at the top of the page.", 1),
            P((171, 500, 576, 560), "Fig 3. Implementation of the value-updating and world-updating models.", 2),
            P((171, 470, 323, 485), "https://doi.org/10.1371/journal.pbio.3002373.g003", 3),
        ),
    }
    md = {0: "Body sentence.\n\nFig 3. Implementation...\n\nhttps://doi.org/...g003"}
    marginal, _ = marginal_paragraphs(paras)
    assert marginal == {}                                # majority x1 NOT left of body -> excluded
    assert consolidate_front_matter(md, paras) == md
