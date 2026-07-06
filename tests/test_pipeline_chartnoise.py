from __future__ import annotations

from parse_anything.pipeline.odl_extract import OdlParagraph
from parse_anything.pipeline.output import (
    _KEEP_IN_FIG, _chart_internal_noise, _gate_figure_descriptions, _mark_chart_label_blocks,
    _suppress_chart_noise,
)


def test_suppress_chart_noise_drops_only_matching_standalone_lines():
    md = "本文です。\n\n1,000\n\nドイツ イタリア\n\n図3 タイトル"
    out = _suppress_chart_noise(md, {"1,000", "ドイツ イタリア"})
    lines = out.split("\n")
    assert "1,000" not in lines and "ドイツ イタリア" not in lines     # chart noise gone
    assert "本文です。" in lines and "図3 タイトル" in lines           # body + caption untouched


def test_keep_in_fig_protects_caption_and_source_lines():
    assert _KEEP_IN_FIG.match("図146−3 熱エネルギー原単位")   # caption
    assert _KEEP_IN_FIG.match("資料：セメント協会")            # source
    assert _KEEP_IN_FIG.match("備考：推定値")                  # note
    assert not _KEEP_IN_FIG.match("1,000")                     # axis tick -> droppable
    assert not _KEEP_IN_FIG.match("ドイツ イタリア 中国")      # legend -> droppable


def test_chart_internal_noise_drops_ticks_inside_bbox_but_keeps_caption_and_outside():
    paras = (
        OdlParagraph(0, "paragraph", (10.0, 100.0, 50.0, 110.0), "1,000"),        # inside -> noise
        OdlParagraph(0, "heading", (10.0, 120.0, 200.0, 130.0), "図3 推移"),       # inside but caption -> keep
        OdlParagraph(0, "paragraph", (500.0, 500.0, 540.0, 510.0), "本文の段落"),  # outside -> keep
    )
    fig = {"source": "vector", "page": 1, "bbox": [0.0, 90.0, 250.0, 140.0]}
    assert _chart_internal_noise([fig], {0: paras}) == {0: {"1,000"}}


def test_chart_internal_noise_attaches_chart_data_with_bbox():
    # FR-5.5: the same internal tokens that get suppressed from prose are ALSO kept, structured, on
    # the figure (text + bbox) instead of being discarded.
    paras = (
        OdlParagraph(0, "paragraph", (10.0, 100.0, 50.0, 110.0), "51,685"),      # inside -> chart_data
        OdlParagraph(0, "heading", (10.0, 120.0, 200.0, 130.0), "図3 推移"),      # caption -> not data
        OdlParagraph(0, "paragraph", (500.0, 500.0, 540.0, 510.0), "本文の段落"),  # outside -> not data
    )
    fig = {"source": "vector", "page": 1, "bbox": [0.0, 90.0, 250.0, 140.0]}
    _chart_internal_noise([fig], {0: paras})
    assert fig["chart_data"] == [{"text": "51,685", "bbox": [10.0, 100.0, 50.0, 110.0]}]


def test_gate_figure_descriptions_flags_unsourced_numbers():
    # §5-A: a number in the VLM description that is NOT among the chart's own tokens is
    # fabrication-suspect; a matching one is not flagged.
    fabricated = {"description": "총인구는 99,999로 급감했다", "chart_data": [{"text": "51,685", "bbox": [0, 0, 1, 1]}]}
    sourced = {"description": "총인구는 51,685이다", "chart_data": [{"text": "51,685", "bbox": [0, 0, 1, 1]}]}
    _gate_figure_descriptions([fabricated, sourced])
    assert fabricated["description_flags"] == ["unsourced_number:99999"]
    assert "description_flags" not in sourced


def test_gate_figure_descriptions_raster_falls_back_to_page_text_layer():
    # A1/§5-A: a raster figure has no chart_data, so its description is gated against the page's
    # born-digital text-layer numbers instead. A number present in the layer is clean; one absent --
    # including EVERY number when the page has no sourceable numbers -- is flagged (unverifiable, not
    # silently trusted), mirroring the transcription gate.
    # raster numbers live in pixels, not the text layer, so they flag as `unverifiable_number` (not
    # `unsourced_number`, which is reserved for a number absent from a chart's OWN tokens).
    raster_bad = {"page": 1, "description": "총계는 88,888건이다"}                 # 88888 not on page -> flag
    raster_ok = {"page": 1, "description": "총계는 51,685건이다"}                  # 51685 on page -> clean
    raster_nosrc = {"page": 2, "description": "총계는 77,777건이다"}               # page 2: empty source -> flag
    _gate_figure_descriptions([raster_bad, raster_ok, raster_nosrc], page_numbers={0: ["51685"]})
    assert raster_bad["description_flags"] == ["unverifiable_number:88888"]
    assert "description_flags" not in raster_ok
    assert raster_nosrc["description_flags"] == ["unverifiable_number:77777"]  # empty source -> flagged

    # No PDF at all (page_numbers=None): raster descriptions have no source -> skipped (not flagged).
    raster_nopdf = {"page": 1, "description": "총계는 99,999건이다"}
    _gate_figure_descriptions([raster_nopdf])
    assert "description_flags" not in raster_nopdf


def test_gate_figure_descriptions_flags_dropped_scale_unit():
    # §5-A: the chart declares '단위: 천 명' but the description states a magnitude WITHOUT the scale
    # (reads 천-scaled values as bare) -> unit_unstated. The number itself IS in chart_data, so plain
    # number matching would pass; the unit check is what catches the misread.
    data = [{"text": "단위: 천 명", "bbox": [0, 0, 1, 1]}, {"text": "51,685", "bbox": [0, 0, 1, 1]}]
    dropped = {"page": 1, "description": "총인구는 51,685명이다", "chart_data": data}      # 천 dropped -> flag
    kept = {"page": 1, "description": "총인구는 51,685천 명이다", "chart_data": data}       # 천 present -> clean
    _gate_figure_descriptions([dropped, kept])
    assert dropped["description_flags"] == ["unit_unstated:천"]
    assert "description_flags" not in kept

    # No explicit '단위:' declaration -> no unit check (bare Korean scale words are not matched).
    no_decl = {"page": 1, "description": "총인구 51,685명",
               "chart_data": [{"text": "인구 51,685", "bbox": [0, 0, 1, 1]}]}
    _gate_figure_descriptions([no_decl])
    assert "description_flags" not in no_decl


def test_mark_chart_label_blocks_flags_inside_excludes_caption_and_outside():
    blocks = [
        {"id": "b1", "page": 1, "bbox": [10.0, 100.0, 50.0, 110.0], "text": "1,000"},       # inside -> mark
        {"id": "b2", "page": 1, "bbox": [10.0, 120.0, 200.0, 130.0], "text": "図3 推移"},    # caption -> keep
        {"id": "b3", "page": 1, "bbox": [500.0, 500.0, 540.0, 510.0], "text": "本文の段落"},  # outside -> keep
    ]
    _mark_chart_label_blocks([{"source": "vector", "page": 1, "bbox": [0.0, 90.0, 250.0, 140.0], "id": "f1"}], blocks)
    assert blocks[0].get("figure") == "f1"
    assert not blocks[1].get("figure") and not blocks[2].get("figure")


def test_classify_figure_kinds_vector_chart_vs_diagram():
    from parse_anything.pipeline.output import _classify_figure_kinds

    def data(*texts):
        return [{"text": t, "bbox": [0, 0, 1, 1]} for t in texts]

    chart = {"source": "vector", "chart_data": data("2020", "2021", "51,685", "12,300")}  # number-dense
    lineart = {"source": "vector"}                                              # no tokens -> diagram (guess)
    # a flowchart's box labels also land in chart_data; word-dense with <2 numbers must NOT be a chart
    flowchart = {"source": "vector", "chart_data": data("승인", "반려", "검토 1단계")}  # 1 number -> diagram
    # a number-sprinkled flowchart hits >=2 numerics but is word-dominant -> chart, but LOW confidence
    numbered_flow = {"source": "vector", "chart_data": data("1단계", "2단계", "3단계", "승인", "반려", "보류")}
    raster = {"source": "odl_image", "kind": "image"}    # producer kind kept
    vlm = {"source": "vlm", "kind": "figure"}            # kept
    _classify_figure_kinds([chart, lineart, flowchart, numbered_flow, raster, vlm])
    assert chart["kind"] == "chart" and "kind_confidence" not in chart   # strong numeric evidence
    assert lineart["kind"] == "diagram" and lineart["kind_confidence"] == "low"   # label-less guess
    assert flowchart["kind"] == "diagram" and flowchart["kind_confidence"] == "low"  # 1 number = thin
    assert numbered_flow["kind"] == "chart" and numbered_flow["kind_confidence"] == "low"  # word-dominant
    assert raster["kind"] == "image"        # untouched (deterministic pass does not reclassify raster)
    assert vlm["kind"] == "figure"          # untouched
