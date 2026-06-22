from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final, Literal

from odl_vl.jsonsearch import find_first_string
from odl_vl.normalizers import try_decode_json
from odl_vl.providers import HttpRequest, HttpResponse, ProviderHttpClient, is_success_status


COMPLETE_STATUSES: Final = frozenset({"done", "completed", "complete", "success", "succeeded", "finished"})
FAILED_STATUSES: Final = frozenset({"failed", "fail", "error", "errored", "canceled", "cancelled"})
# Note: the bare "id" key is intentionally excluded so an unrelated request/trace
# id in a submit response cannot be mistaken for the real job id.
JOB_ID_KEYS: Final = frozenset({"jobId", "job_id", "taskId", "task_id"})
STATUS_KEYS: Final = frozenset({"status", "state", "jobStatus", "taskStatus"})

Terminal = Literal["complete", "failed", "http_error", "timeout"]


def extract_job_id(body: object) -> str | None:
    return find_first_string(body, JOB_ID_KEYS, strip=True)


def extract_status(body: object) -> str | None:
    status = find_first_string(body, STATUS_KEYS, strip=True)
    return status.lower() if status is not None else None


def classify_status(status: str | None) -> Terminal | None:
    if status in COMPLETE_STATUSES:
        return "complete"
    if status in FAILED_STATUSES:
        return "failed"
    return None


@dataclass(frozen=True, slots=True)
class PollOutcome:
    terminal: Terminal
    status: str | None
    body: object
    polls: int
    status_code: int | None = None


def poll_job(
    *,
    client: ProviderHttpClient,
    build_request: Callable[[], HttpRequest],
    timeout_seconds: float,
    poll_interval_seconds: float,
    sleep: Callable[[float], None],
    now: Callable[[], float],
) -> PollOutcome:
    """Drive a Paddle-style poll loop until a terminal state, http error, or timeout.

    Shared by the smoke CLI and the orchestrator so terminal-status detection and
    job/status key handling never drift between the two. Each caller adapts the
    returned ``PollOutcome`` to its own reporting contract.
    """
    deadline = now() + timeout_seconds
    polls = 0
    last_status: str | None = None
    last_body: object = None
    while True:  # always poll at least once, even with timeout <= 0
        polls += 1
        response: HttpResponse = client.send(build_request())
        if not is_success_status(response.status_code):
            return PollOutcome("http_error", None, None, polls, status_code=response.status_code)
        last_body = try_decode_json(response.body)
        last_status = extract_status(last_body)
        terminal = classify_status(last_status)
        if terminal is not None:
            return PollOutcome(terminal, last_status, last_body, polls)
        if now() >= deadline:
            return PollOutcome("timeout", last_status, last_body, polls)
        sleep(poll_interval_seconds)


def find_result_json_url(body: object) -> str | None:
    # Prefer the documented location (data.resultUrl.jsonUrl) so an unrelated
    # nested 'jsonUrl' elsewhere in the payload cannot be picked by mistake.
    if isinstance(body, Mapping):
        data = body.get("data")
        if isinstance(data, Mapping):
            result_url = data.get("resultUrl")
            if isinstance(result_url, Mapping):
                json_url = result_url.get("jsonUrl")
                if isinstance(json_url, str):
                    return json_url
    return find_first_string(body, frozenset({"jsonUrl"}))
