from __future__ import annotations

from itertools import count

from odl_vl.jsonsearch import find_first_string
from odl_vl.paddle_jobs import (
    classify_status,
    extract_job_id,
    extract_status,
    find_result_json_url,
    poll_job,
)
from odl_vl.providers import HttpResponse


def test_find_first_string_walks_nested_and_optionally_strips():
    payload = {"a": {"b": [{"text": "  hi  "}]}}
    assert find_first_string(payload, frozenset({"text"})) == "  hi  "
    assert find_first_string(payload, frozenset({"text"}), strip=True) == "hi"
    assert find_first_string(payload, frozenset({"missing"})) is None


def test_extract_job_id_ignores_bare_id_key():
    # A generic 'id' must not be mistaken for the job id.
    assert extract_job_id({"id": "trace-xyz", "data": {"jobId": "job-1"}}) == "job-1"
    assert extract_job_id({"id": "trace-only"}) is None


def test_extract_status_lowercases_and_classifies():
    assert extract_status({"data": {"state": "DONE"}}) == "done"
    assert classify_status("done") == "complete"
    assert classify_status("failed") == "failed"
    assert classify_status("queued") is None


def test_find_result_json_url_locates_signed_url():
    body = {"data": {"resultUrl": {"jsonUrl": "https://signed.example/r.json"}}}
    assert find_result_json_url(body) == "https://signed.example/r.json"


class _ListTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.client_sends = 0

    def send(self, _request):
        self.client_sends += 1
        return self.responses.pop(0)


def _client(responses):
    from odl_vl.providers import ProviderHttpClient

    return ProviderHttpClient(_ListTransport(responses))


def _body(payload: str) -> HttpResponse:
    return HttpResponse(status_code=200, body=payload.encode("utf-8"))


def test_poll_job_returns_complete_with_body():
    client = _client([_body('{"data":{"state":"queued"}}'), _body('{"data":{"state":"done"}}')])
    clock = (lambda c=count(): float(next(c)))
    outcome = poll_job(
        client=client,
        build_request=lambda: object(),  # type: ignore[arg-type]
        timeout_seconds=100,
        poll_interval_seconds=0,
        sleep=lambda _s: None,
        now=clock,
    )
    assert outcome.terminal == "complete"
    assert outcome.polls == 2
    assert outcome.status == "done"


def test_poll_job_reports_http_error():
    client = _client([HttpResponse(status_code=500, body=b"")])
    clock = (lambda c=count(): float(next(c)))
    outcome = poll_job(
        client=client,
        build_request=lambda: object(),  # type: ignore[arg-type]
        timeout_seconds=100,
        poll_interval_seconds=0,
        sleep=lambda _s: None,
        now=clock,
    )
    assert outcome.terminal == "http_error"
    assert outcome.status_code == 500
