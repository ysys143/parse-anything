from __future__ import annotations

import pytest

from odl_vl.pipeline import ontology as O
from odl_vl.pipeline.ontology import (compute_font_ranks, load_ontology, node_signals, tag_nodes)


def _load_fm(tmp_path, frontmatter: str, name: str = "t"):
    (tmp_path / f"{name}.md").write_text(f"---\n{frontmatter}\n---\n# doc body\n", encoding="utf-8")
    return load_ontology(name, tmp_path)


# ---- scalar parsing --------------------------------------------------------------------------------
def test_scalar_types():
    assert O._scalar("123") == 123 and isinstance(O._scalar("123"), int)
    assert O._scalar("1.5") == 1.5
    assert O._scalar("true") is True and O._scalar("false") is False
    for null in ("null", "~", "none", "None"):
        assert O._scalar(null) is None
    assert O._scalar("'quoted, x'") == "quoted, x"        # quotes stripped, inner comma kept
    assert O._scalar('"dq"') == "dq"
    assert O._scalar("bare word") == "bare word"
    assert O._scalar("") is None


# ---- comment stripping -----------------------------------------------------------------------------
def test_strip_comment_respects_quotes_and_brackets():
    assert O._strip_comment("a: b   # trailing") == "a: b"
    assert O._strip_comment("x: '# not a comment'") == "x: '# not a comment'"
    assert O._strip_comment("{a: b}  # c") == "{a: b}"
    assert O._strip_comment("nohash") == "nohash"
    assert O._strip_comment("a#b") == "a#b"               # '#' not preceded by space is literal


# ---- flow splitting / kv ---------------------------------------------------------------------------
def test_split_flow_respects_nesting_and_quotes():
    assert O._split_flow("a, b, c") == ["a", " b", " c"]
    assert O._split_flow("a, [b, c], d") == ["a", " [b, c]", " d"]
    assert O._split_flow("{x: 1, y: 2}, z") == ["{x: 1, y: 2}", " z"]
    assert O._split_flow("'a, b', c") == ["'a, b'", " c"]


def test_split_kv_uses_first_top_level_colon():
    assert O._split_kv("a: b") == ("a", "b")
    assert O._split_kv("id: odl:ontology/x") == ("id", "odl:ontology/x")
    assert O._split_kv("when: {t: {eq: 1}}") == ("when", "{t: {eq: 1}}")
    with pytest.raises(ValueError):
        O._split_kv("no colon here")


def test_parse_flow_nested():
    assert O._parse_flow("{a: 1, b: [x, y]}") == {"a": 1, "b": ["x", "y"]}
    assert O._parse_flow("{all: [{p: {eq: 0}}, {q: {in: [a, b]}}]}") == \
        {"all": [{"p": {"eq": 0}}, {"q": {"in": ["a", "b"]}}]}
    assert O._parse_flow("[]") == [] and O._parse_flow("{}") == {}


def test_parse_block_sequence_with_nested_block_items(tmp_path):
    # a rule authored in BLOCK style (bare '-' then indented keys) rather than one-line flow
    fm = ("id: x\nversion: 1\nrules:\n"
          "  -\n    id: r\n    when: {}\n    then: {type: paragraph}\n")
    o = _load_fm(tmp_path, fm)
    assert o.rules[0].id == "r" and o.rules[0].then == {"type": "paragraph"}


def test_parse_block_key_with_empty_value(tmp_path):
    # a trailing 'key:' with nothing after and no deeper block -> None (must not crash)
    o = _load_fm(tmp_path, "id: x\nversion: 1\nconformsTo:")
    assert o.conforms_to is None


# ---- frontmatter framing ---------------------------------------------------------------------------
def test_frontmatter_requires_opening_and_closing_fence(tmp_path):
    (tmp_path / "a.md").write_text("no fence\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_ontology("a", tmp_path)
    (tmp_path / "b.md").write_text("---\nid: x\nversion: 1\n", encoding="utf-8")   # unterminated
    with pytest.raises(ValueError):
        load_ontology("b", tmp_path)


def test_missing_id_or_version_raises(tmp_path):
    with pytest.raises(ValueError):
        _load_fm(tmp_path, "version: 1")
    with pytest.raises(ValueError):
        _load_fm(tmp_path, "id: x")


def test_rule_missing_fields_raises(tmp_path):
    with pytest.raises(ValueError):
        _load_fm(tmp_path, "id: x\nversion: 1\nrules:\n  - {id: r, when: {}}")   # no 'then'


# ---- node types + chunk policy ---------------------------------------------------------------------
def test_node_types_and_chunk_policy(tmp_path):
    o = _load_fm(tmp_path, "id: x\nversion: 2\nnode_types:\n  fig: {meaning: doco:F, atomic: true}\n"
                           "  para: {meaning: doco:P}\nchunking: {child_tokens: 128, tokenizer: gpt2}")
    assert o.node_types["fig"].atomic is True and o.node_types["fig"].meaning == "doco:F"
    assert o.node_types["para"].atomic is False
    assert o.chunking.child_tokens == 128 and o.chunking.tokenizer == "gpt2"
    assert o.chunking.parent == "section" and "table" in o.chunking.keep_atomic   # defaults


def test_profile_stamp_includes_conforms_to_only_when_present(tmp_path):
    o1 = _load_fm(tmp_path, "id: a\nversion: 1\nconformsTo: http://x", name="a")
    o2 = _load_fm(tmp_path, "id: b\nversion: 1", name="b")
    assert o1.profile_stamp()["conformsTo"] == "http://x"
    assert "conformsTo" not in o2.profile_stamp()
    assert o1.profile_stamp()["sha256"] == o1.sha256 and len(o1.sha256) == 64


def test_load_missing_ontology_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_ontology("does_not_exist", tmp_path)


def test_sha256_tracks_content(tmp_path):
    a = _load_fm(tmp_path, "id: x\nversion: 1", name="s1")
    b = _load_fm(tmp_path, "id: x\nversion: 2", name="s2")
    assert a.sha256 != b.sha256


# ---- classify: comparison operators ----------------------------------------------------------------
def _rule_onto(tmp_path, when: str, then: str = "{type: heading}", name: str = "t"):
    return _load_fm(tmp_path, f"id: x\nversion: 1\nrules:\n  - {{id: r, when: {when}, then: {then}}}\n"
                              f"  - {{id: d, when: {{}}, then: {{type: paragraph}}}}", name=name)


@pytest.mark.parametrize("when,sig,hit", [
    ("{page_index: {eq: 0}}", {"page_index": 0}, True),
    ("{page_index: {eq: 0}}", {"page_index": 3}, False),
    ("{odl_type: {in: [heading, title]}}", {"odl_type": "title"}, True),
    ("{odl_type: {not_in: [heading]}}", {"odl_type": "para"}, True),
    ("{font_rank: {gte: 0.8}}", {"font_rank": 0.9}, True),
    ("{font_rank: {gte: 0.8}}", {"font_rank": 0.5}, False),
    ("{font_rank: {lte: 0.2}}", {"font_rank": 0.1}, True),
    ("{page_index: {gt: 1}}", {"page_index": 2}, True),
    ("{page_index: {lt: 1}}", {"page_index": 0}, True),
    ("{odl_heading_level: {not_null: true}}", {"odl_heading_level": 2}, True),
    ("{odl_heading_level: {not_null: true}}", {"odl_heading_level": None}, False),
])
def test_classify_comparison_ops(tmp_path, when, sig, hit):
    o = _rule_onto(tmp_path, when)
    base = {"page_index": 9, "odl_type": "x", "font_rank": 0.0, "odl_heading_level": None, "text": ""}
    assert (o.classify({**base, **sig}).role == "heading") is hit


def test_classify_combinators(tmp_path):
    o = _rule_onto(tmp_path, "{all: [{page_index: {eq: 0}}, {odl_type: {eq: heading}}]}")
    assert o.classify({"page_index": 0, "odl_type": "heading", "text": ""}).role == "heading"
    assert o.classify({"page_index": 0, "odl_type": "para", "text": ""}).role == "paragraph"
    o2 = _rule_onto(tmp_path, "{any: [{page_index: {eq: 0}}, {page_index: {eq: 5}}]}", name="a")
    assert o2.classify({"page_index": 5, "text": ""}).role == "heading"
    o3 = _rule_onto(tmp_path, "{not: {page_index: {eq: 0}}}", name="b")
    assert o3.classify({"page_index": 2, "text": ""}).role == "heading"
    assert o3.classify({"page_index": 0, "text": ""}).role == "paragraph"


def test_classify_text_matches_scalar_and_dict(tmp_path):
    o = _rule_onto(tmp_path, "{text_matches: '(?i)^references$'}", "{zone: references, opens_zone: true}")
    v = o.classify({"text": "REFERENCES"})
    assert v.zone == "references" and v.opens_zone is True
    o2 = _rule_onto(tmp_path, "{text_matches: {pattern: '^ref', flags: i}}", "{zone: references}", name="a")
    assert o2.classify({"text": "Ref list"}).zone == "references"


def test_classify_numbering_predicate(tmp_path):
    o = _rule_onto(tmp_path, "{classify_numbering: not_null}")
    assert o.classify({"text": "1.2 Method"}).role == "heading"
    assert o.classify({"text": "Just prose"}).role == "paragraph"


def test_classify_unknown_predicate_and_op_raise(tmp_path):
    bad_pred = _rule_onto(tmp_path, "{bogus: 1}")
    with pytest.raises(ValueError):
        bad_pred.classify({"text": "x"})
    bad_op = _rule_onto(tmp_path, "{page_index: {wat: 1}}", name="a")
    with pytest.raises(ValueError):
        bad_op.classify({"page_index": 0, "text": "x"})


def test_classify_scalar_equality_spec(tmp_path):
    o = _rule_onto(tmp_path, "{odl_type: heading}")            # spec is a bare scalar -> equality
    assert o.classify({"odl_type": "heading", "text": ""}).role == "heading"
    assert o.classify({"odl_type": "para", "text": ""}).role == "paragraph"


@pytest.mark.parametrize("when,sig", [
    ("{odl_type: {not_in: [heading]}}", {"odl_type": "heading"}),   # value IS in -> fail
    ("{page_index: {gt: 5}}", {"page_index": 5}),                   # equal -> gt fails
    ("{page_index: {lt: 5}}", {"page_index": 5}),                   # equal -> lt fails
    ("{font_rank: {lte: 0.2}}", {"font_rank": 0.9}),                # above ceiling -> lte fails
    ("{font_rank: {gte: 0.5}}", {"font_rank": None}),               # non-numeric -> gte fails
    ("{odl_heading_level: {not_null: false}}", {"odl_heading_level": 2}),  # present but want-null
])
def test_classify_comparison_fail_branches(tmp_path, when, sig):
    o = _rule_onto(tmp_path, when)
    base = {"page_index": 0, "odl_type": "x", "font_rank": 0.0, "odl_heading_level": None, "text": ""}
    assert o.classify({**base, **sig}).role == "paragraph"       # rule misses -> default


def test_split_kv_quoted_key_with_inner_colon():
    assert O._split_kv("'a:b': value") == ("'a:b'", "value")       # quoted key, colon inside is not a split


def test_classify_type_rule_can_open_a_zone(tmp_path):
    o = _rule_onto(tmp_path, "{odl_type: {eq: heading}}", "{type: heading, opens_zone: true}")
    assert o.classify({"odl_type": "heading", "text": ""}).opens_zone is True   # opens set on the type axis


def test_frontmatter_skips_blank_and_comment_lines(tmp_path):
    o = _load_fm(tmp_path, "id: x\n\n# a comment line\nversion: 1\nzones: [a]")
    assert o.id == "x" and o.zones == ("a",)


def test_classify_zone_rule_opens_zone_when_type_preset(tmp_path):
    o = _load_fm(tmp_path, "id: x\nversion: 1\nrules:\n"
                           "  - {id: a, when: {odl_type: {eq: heading}}, then: {type: heading}}\n"
                           "  - {id: b, when: {odl_type: {eq: heading}}, then: {zone: references, opens_zone: true}}\n")
    v = o.classify({"odl_type": "heading", "text": ""})
    assert v.role == "heading" and v.zone == "references" and v.opens_zone is True


def test_when_not_a_mapping_raises(tmp_path):
    o = _rule_onto(tmp_path, "[a, b]")                           # when is a sequence, not a mapping
    with pytest.raises(ValueError):
        o.classify({"text": "x"})


def test_frontmatter_root_must_be_a_mapping(tmp_path):
    (tmp_path / "seq.md").write_text("---\n- a\n- b\n---\nbody\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_ontology("seq", tmp_path)


def test_authority_level_matches_and_abstains():
    from odl_vl.pipeline.outline import HeadingAuthority, OutlineEntry
    from odl_vl.pipeline.sections import _authority_level
    auth = HeadingAuthority(entries=[
        OutlineEntry("Introduction", 1, None, 0, "pdf_outline"),
        OutlineEntry("Methods", 2, "7", None, "printed_toc"),    # resolved via printed_to_pdf
    ], toc_page_indices=frozenset(), source="mixed")
    assert _authority_level("Introduction", 1, auth, {}) == 1    # title match on its page
    assert _authority_level("Methods", 7, auth, {"7": 6}) == 2   # printed page 7 -> pdf index 6, page 7 (idx 6)
    assert _authority_level("Introduction", 9, auth, {}) is None  # right title, wrong page -> abstain
    assert _authority_level("Totally different heading", 1, auth, {}) is None  # ratio too low -> abstain
    assert _authority_level("", 1, auth, {}) is None             # empty normalized title -> None


def test_first_match_per_axis(tmp_path):
    # two rules set type; the FIRST wins. a later rule can still fill the zone axis.
    o = _load_fm(tmp_path, "id: x\nversion: 1\nrules:\n"
                           "  - {id: a, when: {odl_type: {eq: heading}}, then: {type: heading}}\n"
                           "  - {id: b, when: {odl_type: {eq: heading}}, then: {type: title, zone: cover}}\n")
    v = o.classify({"odl_type": "heading", "text": ""})
    assert v.role == "heading" and v.zone == "cover"          # type from rule a, zone from rule b


# ---- signals / font ranks / tagging ----------------------------------------------------------------
def test_compute_font_ranks_percentile_and_none():
    blocks = [{"id": "a", "font_size": 8.0}, {"id": "b", "font_size": 10.0},
              {"id": "c", "font_size": 12.0}, {"id": "d"}]
    r = compute_font_ranks(blocks)
    assert r["a"] == 0.0 and r["c"] == 2 / 3 and r["d"] is None
    assert compute_font_ranks([]) == {}
    assert compute_font_ranks([{"id": "x"}]) == {"x": None}    # no fonts at all


def test_node_signals_shape():
    s = node_signals({"id": "b", "type": "heading", "odl_role": "Subtitle", "heading_level": 2,
                      "font_size": 12.0, "page": 3, "text": "Hi"}, {"b": 0.9}, is_landscape=True)
    assert s == {"page_index": 2, "odl_type": "heading", "odl_role": "Subtitle", "odl_heading_level": 2,
                 "font_size": 12.0, "font_rank": 0.9, "is_landscape": True, "text": "Hi"}


def test_tag_nodes_roles_zones_and_spanning():
    onto = load_ontology("default", __import__("pathlib").Path(__file__).resolve().parents[1] / "ontology")
    blocks = [
        {"id": "b1", "type": "paragraph", "page": 1, "order": 1, "text": "Body here."},
        {"id": "b2", "type": "heading", "page": 2, "order": 2, "text": "References"},
        {"id": "b3", "type": "paragraph", "page": 2, "order": 3, "text": "[1] an entry"},
    ]
    tables = [{"id": "t1", "type": "table", "pages": [1], "order": 1}]
    figures = [{"id": "f1", "type": "figure", "page": 2, "order": 5}]
    tag_nodes(blocks, tables, figures, onto)
    z = {n["id"]: n["zone"] for n in (*blocks, *tables, *figures)}
    assert z["b1"] == "body" and z["b3"] == "references"        # spanning from the References heading
    assert {n["id"]: n["role"] for n in tables + figures} == {"t1": "table", "f1": "figure"}
