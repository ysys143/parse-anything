from __future__ import annotations

import json

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from parse_anything.pipeline.assemble import _recurring_numbers, assemble_document
from parse_anything.providers import HttpResponse


class _FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)

    def send(self, request):
        return self.responses.pop(0)


def _gemini_ok(text: str) -> HttpResponse:
    return HttpResponse(status_code=200, body=json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}]}).encode("utf-8"))


def _pdf(path, line: str) -> str:
    c = canvas.Canvas(str(path), pagesize=letter)
    c.drawString(72, 720, line)
    c.showPage()
    c.save()
    return str(path)


def _two_page_pdf(path) -> str:
    c = canvas.Canvas(str(path), pagesize=letter)
    c.drawString(72, 720, "page one with a table at the bottom")
    c.showPage()
    c.drawString(72, 720, "page two where the table continues")
    c.showPage()
    c.save()
    return str(path)


_SPANNING_ODL = {
    "number of pages": 2,
    "kids": [
        {"type": "table", "page number": 1, "id": "t1", "bounding box": [50, 400, 400, 600],
         "number of rows": 2, "number of columns": 2,
         "rows": [{"type": "table row", "cells": [{"type": "table cell", "content": "H1"}, {"type": "table cell", "content": "H2"}]},
                  {"type": "table row", "cells": [{"type": "table cell", "content": "a"}, {"type": "table cell", "content": "1"}]}]},
        {"type": "table", "page number": 2, "id": "t2", "previous table id": "t1", "bounding box": [50, 600, 400, 700],
         "number of rows": 1, "number of columns": 2,
         "rows": [{"type": "table row", "cells": [{"type": "table cell", "content": "b"}, {"type": "table cell", "content": "2"}]}]},
    ],
}


def test_det_vlm_spanning_merges_pages_via_multi_image(tmp_path):
    pdf = _two_page_pdf(tmp_path / "s.pdf")
    client = _FakeClient([_gemini_ok("| H1 | H2 |\n| a | 1 |\n| b | 2 |")])   # ONE multi-image request
    res = assemble_document(pdf, mode="det_vlm", vlm_client=client, api_key="k", odl_runner=lambda _p: _SPANNING_ODL)
    assert len(res.pages) == 2
    assert res.pages[0].route == "det_vlm" and "| b | 2 |" in res.pages[0].markdown   # merged across pages
    assert any(f.startswith("spanning_pages:") for f in res.pages[0].flags)
    assert res.pages[1].route == "folded" and "folded_into:0" in res.pages[1].flags
    assert len(client.responses) == 0   # exactly one batched request consumed


def test_det_vlm_no_spanning_processes_pages_separately(tmp_path):
    from parse_anything.pipeline.assemble import DetVlmOptions

    pdf = _two_page_pdf(tmp_path / "s.pdf")
    client = _FakeClient([_gemini_ok("p1"), _gemini_ok("p2")])   # two per-page requests
    res = assemble_document(pdf, mode="det_vlm", vlm_client=client, api_key="k",
                            options=DetVlmOptions(spanning=False), odl_runner=lambda _p: _SPANNING_ODL)
    assert len(res.pages) == 2 and all(p.route == "det_vlm" for p in res.pages)   # no folding


def test_det_vlm_primary_paddle_uses_paddle_transcriber(tmp_path):
    from parse_anything.pipeline.assemble import DetVlmOptions

    pdf = _pdf(tmp_path / "d.pdf", "value 1,234,567")
    paddle = lambda _png: "| H | V |\n| --- | --- |\n| a | 1 |"  # noqa: E731
    res = assemble_document(pdf, mode="det_vlm", vlm_client=None, options=DetVlmOptions(primary="paddle"),
                            primary_transcribe=paddle, odl_runner=lambda _p: {"number of pages": 1, "kids": []})
    assert res.pages[0].route == "det_vlm" and "| H | V |" in res.pages[0].markdown   # Paddle is the primary VLM


def test_whole_doc_transcribes_all_pages_in_one_call(tmp_path):
    from parse_anything.pipeline.assemble import DetVlmOptions

    pdf = _two_page_pdf(tmp_path / "w.pdf")
    seen = {}

    def multi(pngs):
        seen["pages"] = len(pngs)          # ALL pages arrive in one call
        return "# Whole Document\n\npage one and page two, one coherent markdown"

    res = assemble_document(pdf, mode="det_vlm", vlm_client=None,
                            options=DetVlmOptions(whole_doc=True), primary_transcribe_multi=multi,
                            odl_runner=lambda _p: _SPANNING_ODL)
    assert seen["pages"] == 2                                   # one multi-image call over both pages
    assert res.pages[0].route == "det_vlm" and "Whole Document" in res.pages[0].markdown  # page 0 carries the doc
    assert any(f.startswith("whole_doc_pages:0-") for f in res.pages[0].flags)
    assert res.pages[1].route == "folded" and res.pages[1].markdown == "" and "folded_into:0" in res.pages[1].flags
    assert res.structure is not None                           # ODL substrate still attached for rich output


def test_whole_doc_degrades_to_deterministic_on_failure(tmp_path):
    from parse_anything.pipeline.assemble import DetVlmOptions

    pdf = _two_page_pdf(tmp_path / "w.pdf")

    def boom(_pngs):
        raise RuntimeError("model down")

    res = assemble_document(pdf, mode="det_vlm", vlm_client=None,
                            options=DetVlmOptions(whole_doc=True), primary_transcribe_multi=boom,
                            odl_runner=lambda _p: _SPANNING_ODL)
    assert len(res.pages) == 2 and all(p.route == "det_vlm" for p in res.pages)   # never dropped, no folding
    assert all("whole_doc_failed" in p.flags for p in res.pages)


def test_openai_multi_transcriber_sends_one_request_with_all_images():
    from parse_anything.pipeline.openai_vlm import make_multi_transcriber

    ok = HttpResponse(status_code=200,
                      body=json.dumps({"choices": [{"message": {"content": "# DOC"}}]}).encode("utf-8"))
    client = _CaptureClient([ok])
    transcribe = make_multi_transcriber(client, base_url="http://x/v1", token="EMPTY", model="model")
    out = transcribe([b"p1", b"p2", b"p3"])
    assert out == "# DOC"
    assert len(client.requests) == 1                           # ONE request for the whole document
    body = json.loads(client.requests[0].body)
    content = body["messages"][0]["content"]
    assert sum(1 for c in content if c["type"] == "image_url") == 3   # all 3 pages in that request
    assert sum(1 for c in content if c["type"] == "text") == 1


class _CaptureClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def send(self, request):
        self.requests.append(request)
        return self.responses.pop(0)


def test_det_vlm_grounding_default_injects_deterministic_text(tmp_path):
    pdf = _pdf(tmp_path / "d.pdf", "authoritative value 1,234,567")
    client = _CaptureClient([_gemini_ok("ok")])
    odl = {"number of pages": 1, "kids": [{"type": "paragraph", "page number": 1, "content": "Title"}]}
    assemble_document(pdf, mode="det_vlm", vlm_client=client, api_key="k", odl_runner=lambda _p: odl)
    body = client.requests[0].body.decode("utf-8")
    assert "1,234,567" in body and "NEVER alter a number" in body   # grounding on by default


def test_det_vlm_no_ground_option_is_image_only(tmp_path):
    from parse_anything.pipeline.assemble import DetVlmOptions

    pdf = _pdf(tmp_path / "d.pdf", "authoritative value 1,234,567")
    client = _CaptureClient([_gemini_ok("ok")])
    assemble_document(pdf, mode="det_vlm", vlm_client=client, api_key="k", options=DetVlmOptions(ground=False),
                      odl_runner=lambda _p: {"number of pages": 1, "kids": []})
    body = client.requests[0].body.decode("utf-8")
    assert "NEVER alter a number" not in body   # --no-ground -> no grounding block


def test_recurring_numbers_excludes_header_like():
    texts = ["report 200 page one", "report 200 page two", "report 200 has 40 here"]
    rec = _recurring_numbers(texts)
    assert "200" in rec      # on every page -> running header
    assert "40" not in rec   # one page -> potential real data


def test_deterministic_mode_uses_odl_text_and_flags_dropped_numbers(tmp_path):
    pdf = _pdf(tmp_path / "d.pdf", "Spec A100 40GB value 12345")
    odl_json = {  # ODL clean text dropped 40 and 12345 (kept A100 -> 100)
        "number of pages": 1,
        "kids": [{"type": "paragraph", "page number": 1, "content": "Spec A100 GB value"}],
    }
    res = assemble_document(pdf, mode="deterministic", odl_runner=lambda _p: odl_json)
    page = res.pages[0]
    assert page.route == "deterministic" and page.used_vlm is False
    assert "Spec A100 GB value" in page.markdown          # ODL clean text is the output
    assert "odl_dropped_number:40" in page.flags          # pypdfium2 completeness backstop (F17)
    assert "odl_dropped_number:12345" in page.flags


def test_deterministic_mode_renders_odl_tables(tmp_path):
    pdf = _pdf(tmp_path / "d.pdf", "page")
    odl_json = {
        "number of pages": 1,
        "kids": [{
            "type": "table", "page number": 1, "bounding box": [50, 50, 400, 200],
            "number of rows": 2, "number of columns": 2,
            "rows": [
                {"type": "table row", "cells": [{"type": "table cell", "content": "H"}, {"type": "table cell", "content": "V"}]},
                {"type": "table row", "cells": [{"type": "table cell", "content": "a"}, {"type": "table cell", "content": "1"}]},
            ],
        }],
    }
    md = assemble_document(pdf, mode="deterministic", odl_runner=lambda _p: odl_json).pages[0].markdown
    assert "| H | V |" in md and "| a | 1 |" in md


def test_det_vlm_mode_uses_vlm_and_gates_numbers(tmp_path):
    pdf = _pdf(tmp_path / "d.pdf", "authoritative value 1,234,567")  # pypdfium2 source
    odl_json = {"number of pages": 1, "kids": [{"type": "paragraph", "page number": 1, "content": "text"}]}
    client = _FakeClient([_gemini_ok("Value 1,234,567 and fabricated 9,999,999")])
    res = assemble_document(pdf, mode="det_vlm", vlm_client=client, api_key="k", odl_runner=lambda _p: odl_json)
    page = res.pages[0]
    assert page.route == "det_vlm" and page.used_vlm is True
    assert page.markdown == "Value 1,234,567 and fabricated 9,999,999"   # VLM is the output
    assert "unsourced_number:9999999" in page.flags                       # value oracle (pypdfium2) gates VLM
    assert "unsourced_number:1234567" not in page.flags


def test_det_vlm_without_client_degrades_to_deterministic(tmp_path):
    pdf = _pdf(tmp_path / "d.pdf", "page text")
    odl_json = {"number of pages": 1, "kids": [{"type": "paragraph", "page number": 1, "content": "odl clean text"}]}
    res = assemble_document(pdf, mode="det_vlm", vlm_client=None, odl_runner=lambda _p: odl_json)
    page = res.pages[0]
    assert page.used_vlm is False and "vlm_unavailable" in page.flags
    assert "odl clean text" in page.markdown   # degrades to deterministic (ODL text), never dropped


def test_det_vlm_illegible_scan_abstains(tmp_path):
    pdf = _pdf(tmp_path / "d.pdf", "page")
    client = _FakeClient([_gemini_ok("IMAGE_TOO_LOW_QUALITY")])
    res = assemble_document(pdf, mode="det_vlm", vlm_client=client, api_key="k", odl_runner=lambda _p: {"number of pages": 1, "kids": []})
    page = res.pages[0]
    assert page.markdown == "" and "illegible_low_quality" in page.flags
