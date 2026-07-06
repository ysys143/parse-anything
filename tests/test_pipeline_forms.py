from __future__ import annotations

from parse_anything.pipeline.forms import detect_form_fields, detect_form_fields_gated


def _b(text, x0, y0, x1, y1, id=None):
    return {"text": text, "bbox": [x0, y0, x1, y1], "id": id}


def test_pairs_colon_label_with_value_to_the_right():
    blocks = [_b("성명:", 0, 0, 30, 10, "l1"), _b("육도연", 35, 0, 80, 10, "v1")]
    assert detect_form_fields(blocks) == [{"label": "성명", "value": "육도연", "label_bbox": [0, 0, 30, 10],
                                           "value_bbox": [35, 0, 80, 10], "label_id": "l1", "value_id": "v1"}]


def test_pairs_label_with_value_below_when_none_to_the_right():
    blocks = [_b("주소：", 0, 0, 40, 10), _b("대전광역시 미산회원구", 0, 12, 90, 22)]
    fields = detect_form_fields(blocks)
    assert len(fields) == 1 and fields[0]["label"] == "주소" and fields[0]["value"] == "대전광역시 미산회원구"


def test_short_field_names_still_pair():
    blocks = [_b("실명번호:", 0, 0, 45, 10), _b("321617-1107612", 50, 0, 140, 10)]
    fields = detect_form_fields(blocks)
    assert fields and fields[0]["label"] == "실명번호" and fields[0]["value"] == "321617-1107612"


# ---- adversarial-review guards --------------------------------------------------------------------

def test_v2d_value_cannot_lie_beyond_the_next_label():
    # [성명:] [주소:] [육도연]: 육도연 is 주소's value; 성명's right value is blocked by the 주소 label.
    blocks = [_b("성명:", 0, 0, 30, 10), _b("주소:", 40, 0, 70, 10), _b("육도연", 100, 0, 140, 10)]
    fields = detect_form_fields(blocks)
    assert fields == [{"label": "주소", "value": "육도연", "label_bbox": [40, 0, 70, 10],
                       "value_bbox": [100, 0, 140, 10], "label_id": None, "value_id": None}]


def test_v3_below_pairing_is_distance_bounded():
    # a label with no right value does NOT grab a far-below section heading
    blocks = [_b("서명:", 0, 0, 40, 10), _b("III. 결론", 0, 900, 120, 920)]
    assert detect_form_fields(blocks) == []


def test_v4a_empty_value_is_not_paired():
    blocks = [_b("성명:", 0, 0, 30, 10), _b("   ", 35, 0, 80, 10)]
    assert detect_form_fields(blocks) == []


def test_v1_note_and_sentence_and_url_colons_are_not_labels():
    blocks = [
        _b("참고:", 0, 0, 30, 10), _b("이건 값이 아님", 35, 0, 120, 10),          # note -> reject
        _b("아래 절차는 다음과 같이 진행됩니다:", 0, 20, 220, 30), _b("x", 225, 20, 240, 30),  # sentence -> reject
        _b("https://example.com:", 0, 40, 110, 50), _b("y", 115, 40, 130, 50),   # URL -> reject
    ]
    assert detect_form_fields(blocks) == []


def test_label_is_never_paired_with_another_label_or_itself():
    assert detect_form_fields([_b("성명:", 0, 0, 30, 10)]) == []          # lone label -> no value
    assert detect_form_fields([_b("본문 문장입니다", 0, 0, 100, 10)]) == []  # non-label ignored


def test_v5_density_gate_suppresses_sparse_pages():
    # one incidental field on a prose page -> gated away; a real multi-field form passes
    sparse = [_b("성명:", 0, 0, 30, 10), _b("육도연", 35, 0, 80, 10)]
    assert detect_form_fields_gated(sparse, min_fields=3) == []
    form = [_b("성명:", 0, 0, 30, 10), _b("육도연", 35, 0, 80, 10),
            _b("전화:", 0, 15, 30, 25), _b("010-1234", 35, 15, 90, 25),
            _b("주소:", 0, 30, 30, 40), _b("대전", 35, 30, 70, 40)]
    assert len(detect_form_fields_gated(form, min_fields=3)) == 3


def test_b1b_multiline_value_below_is_merged():
    # a two-line address stacked under the label -> one value (newline-joined), bbox unioned
    blocks = [_b("주소:", 0, 0, 40, 10),
              _b("대전광역시 미산회원구", 0, 12, 90, 22),
              _b("납음로6길 636", 0, 24, 70, 34)]
    fields = detect_form_fields(blocks)
    assert len(fields) == 1
    assert fields[0]["value"] == "대전광역시 미산회원구\n납음로6길 636"
    assert fields[0]["value_bbox"] == [0, 12, 90, 34]      # union of both lines


def test_b1b_a_vertical_gap_ends_the_value_stack():
    # a far block (big gap) is NOT absorbed into the value
    blocks = [_b("주소:", 0, 0, 40, 10), _b("대전", 0, 12, 40, 22), _b("무관한 하단", 0, 200, 60, 210)]
    fields = detect_form_fields(blocks)
    assert fields[0]["value"] == "대전"                    # the far block is excluded


def test_b1b_single_line_and_right_values_unchanged():
    assert detect_form_fields([_b("성명:", 0, 0, 30, 10), _b("육도연", 35, 0, 80, 10)])[0]["value"] == "육도연"


def test_b1b_value_does_not_leak_across_the_next_field_label():
    # tight form: 주소's value must stop at 전화's label, not absorb 전화's value (010)
    blocks = [_b("주소:", 0, 0, 40, 10), _b("대전", 0, 12, 40, 22),
              _b("전화:", 0, 24, 40, 34), _b("010", 0, 36, 40, 46)]
    fields = {f["label"]: f["value"] for f in detect_form_fields(blocks)}
    assert fields == {"주소": "대전", "전화": "010"}      # no leak


def test_b1b_wide_body_line_below_is_not_absorbed():
    # a wide body paragraph right under the value (same gap) is excluded by the width guard
    blocks = [_b("주소:", 0, 0, 40, 10), _b("대전", 0, 12, 40, 22),
              _b("이것은 폼 아래 매우 넓은 본문 문장 블록이다", 0, 24, 400, 34)]
    fields = detect_form_fields(blocks)
    assert fields[0]["value"] == "대전"      # body line not merged (too wide)
