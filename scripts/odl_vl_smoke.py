from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal, Protocol, TextIO, TypedDict, assert_never


_REPO_ROOT: Final = Path(__file__).resolve().parents[1]
_SRC_ROOT: Final = _REPO_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from odl_vl.config import Settings, load_settings  # noqa: E402
from odl_vl.providers import (  # noqa: E402
    DEFAULT_GEMINI_MODEL,
    DEFAULT_PADDLE_MODEL,
    GeminiGenerateContentRequest,
    HttpRequest,
    HttpResponse,
    PaddlePollRequest,
    PaddleSubmitRequest,
    ProviderHttpClient,
    Transport,
    UrllibTransport,
    build_gemini_generate_content_request,
    build_paddle_poll_request,
    build_paddle_submit_request,
)


DEFAULT_PADDLE_DEMO_URL: Final = (
    "https://paddle-model-ecology.bj.bcebos.com/paddlex/imgs/demo_image/paddleocr_vl_demo.png"
)
_GEMINI_BASE_URL: Final = "https://generativelanguage.googleapis.com"
_GEMINI_PROMPT: Final = "Return exactly: ok"
_COMPLETE_STATUSES: Final = frozenset({"done", "completed", "complete", "success", "succeeded", "finished"})
_FAILED_STATUSES: Final = frozenset({"failed", "fail", "error", "errored", "canceled", "cancelled"})
_JOB_ID_KEYS: Final = frozenset({"jobId", "job_id", "id", "taskId", "task_id"})
_STATUS_KEYS: Final = frozenset({"status", "state", "jobStatus", "taskStatus"})


JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
ProviderName = Literal["gemini", "paddle"]


class ParsedArgs(TypedDict):
    provider: ProviderName
    dry_config: bool
    live: bool
    demo_url: str
    timeout_seconds: float
    poll_interval_seconds: float


class Sleeper(Protocol):
    def __call__(self, seconds: float) -> None: ...


@dataclass(frozen=True, slots=True)
class Runtime:
    environ: Mapping[str, str] | None = None
    transport: Transport = field(default_factory=UrllibTransport)
    stdout: TextIO = sys.stdout
    sleep: Sleeper = time.sleep


@dataclass(frozen=True, slots=True)
class PaddlePollResult:
    status: str
    polls: int


@dataclass(frozen=True, slots=True)
class PaddleLiveConfig:
    api_key: str = field(repr=False)
    base_url: str
    model: str


@dataclass(frozen=True, slots=True)
class PaddlePollContext:
    config: PaddleLiveConfig
    client: ProviderHttpClient
    runtime: Runtime
    args: ParsedArgs
    job_id: str


def run_cli(argv: Sequence[str], runtime: Runtime) -> int:
    args = _parse_args(argv)
    settings = load_settings(environ=runtime.environ)

    if args["dry_config"]:
        _print_dry_config(args["provider"], settings, runtime.stdout)
        return 0

    match args["provider"]:
        case "gemini":
            return _run_gemini_live(settings, runtime)
        case "paddle":
            return _run_paddle_live(settings, runtime, args)
        case unreachable:
            assert_never(unreachable)


def _parse_args(argv: Sequence[str]) -> ParsedArgs:
    parser = argparse.ArgumentParser(description="ODL-VL provider smoke checks")
    parser.add_argument("--provider", choices=("gemini", "paddle"), required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-config", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--demo-url", default=DEFAULT_PADDLE_DEMO_URL)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    namespace = parser.parse_args(argv)
    return {
        "provider": namespace.provider,
        "dry_config": namespace.dry_config,
        "live": namespace.live,
        "demo_url": namespace.demo_url,
        "timeout_seconds": namespace.timeout,
        "poll_interval_seconds": namespace.poll_interval,
    }


def _print_dry_config(provider: ProviderName, settings: Settings, stdout: TextIO) -> None:
    match provider:
        case "gemini":
            print("provider=gemini", file=stdout)
            print(f"api_key={_presence(settings.gemini_api_key)}", file=stdout)
            print(f"model={DEFAULT_GEMINI_MODEL}", file=stdout)
            print(f"base_url_host={_host(_GEMINI_BASE_URL)}", file=stdout)
        case "paddle":
            print("provider=paddle", file=stdout)
            print(f"api_key={_presence(settings.paddle_api_key)}", file=stdout)
            print(f"model={settings.paddle_model or DEFAULT_PADDLE_MODEL}", file=stdout)
            print(f"base_url_host={_host(settings.paddle_base_url) if settings.paddle_base_url else 'absent'}", file=stdout)
        case unreachable:
            assert_never(unreachable)


def _run_gemini_live(settings: Settings, runtime: Runtime) -> int:
    if settings.gemini_api_key is None:
        print("provider=gemini live=fail reason=missing_api_key", file=runtime.stdout)
        return 2

    request = _build_gemini_smoke_request(settings.gemini_api_key)
    response = _safe_send(ProviderHttpClient(runtime.transport), request)
    text = _extract_gemini_text(response)
    if response.status_code == 200 and text == "ok":
        print("provider=gemini live=pass status=200 text=ok", file=runtime.stdout)
        return 0

    print(f"provider=gemini live=fail status={response.status_code}", file=runtime.stdout)
    return 1


def _run_paddle_live(settings: Settings, runtime: Runtime, args: ParsedArgs) -> int:
    if settings.paddle_api_key is None or settings.paddle_base_url is None:
        print("provider=paddle live=fail reason=missing_api_key_or_base_url", file=runtime.stdout)
        return 2

    config = PaddleLiveConfig(
        api_key=settings.paddle_api_key,
        base_url=settings.paddle_base_url,
        model=settings.paddle_model or DEFAULT_PADDLE_MODEL,
    )
    client = ProviderHttpClient(runtime.transport)
    submit_response = _safe_send(
        client,
        build_paddle_submit_request(
            PaddleSubmitRequest(
                api_key=config.api_key,
                base_url=config.base_url,
                document_url=args["demo_url"],
                model=config.model,
            )
        ),
    )
    job_id = _extract_job_id(submit_response.body)
    if not _is_success_status(submit_response.status_code) or job_id is None:
        print(f"provider=paddle live=fail submit_status={submit_response.status_code}", file=runtime.stdout)
        return 1

    poll_result = _poll_paddle(PaddlePollContext(config=config, client=client, runtime=runtime, args=args, job_id=job_id))
    if poll_result.status in _COMPLETE_STATUSES:
        print(
            "provider=paddle live=pass "
            f"submit_status={submit_response.status_code} poll_status={poll_result.status} polls={poll_result.polls}",
            file=runtime.stdout,
        )
        return 0

    print(
        "provider=paddle live=fail "
        f"submit_status={submit_response.status_code} poll_status={poll_result.status} polls={poll_result.polls}",
        file=runtime.stdout,
    )
    return 1


def _poll_paddle(context: PaddlePollContext) -> PaddlePollResult:
    deadline = time.monotonic() + context.args["timeout_seconds"]
    polls = 0
    last_status = "timeout"
    while time.monotonic() <= deadline:
        polls += 1
        response = _safe_send(
            context.client,
            build_paddle_poll_request(
                PaddlePollRequest(
                    api_key=context.config.api_key,
                    base_url=context.config.base_url,
                    job_id=context.job_id,
                )
            ),
        )
        if not _is_success_status(response.status_code):
            return PaddlePollResult(status=f"http_{response.status_code}", polls=polls)
        status = _extract_status(response.body)
        last_status = status or f"http_{response.status_code}"
        if last_status in _COMPLETE_STATUSES or last_status in _FAILED_STATUSES:
            break
        context.runtime.sleep(context.args["poll_interval_seconds"])
    return PaddlePollResult(status=last_status, polls=polls)


def _extract_gemini_text(response: HttpResponse) -> str | None:
    payload = _decode_json(response.body)
    return _find_text(payload, frozenset({"text"}))


def _build_gemini_smoke_request(api_key: str) -> HttpRequest:
    base_request = build_gemini_generate_content_request(GeminiGenerateContentRequest(api_key=api_key, prompt=_GEMINI_PROMPT))
    return HttpRequest(
        method=base_request.method,
        url=base_request.url,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        body=base_request.body,
    )


def _safe_send(client: ProviderHttpClient, request: HttpRequest) -> HttpResponse:
    try:
        return client.send(request)
    except urllib.error.HTTPError as error:
        return HttpResponse(status_code=error.code, body=b"")
    except urllib.error.URLError:
        return HttpResponse(status_code=0, body=b"")


def _extract_job_id(body: bytes) -> str | None:
    return _find_text(_decode_json(body), _JOB_ID_KEYS)


def _extract_status(body: bytes) -> str | None:
    status = _find_text(_decode_json(body), _STATUS_KEYS)
    return status.lower() if status is not None else None


def _decode_json(body: bytes) -> JsonValue:
    try:
        return json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return None


def _find_text(value: JsonValue, keys: frozenset[str]) -> str | None:
    match value:
        case dict():
            for key, nested in value.items():
                if key in keys and isinstance(nested, str):
                    return nested.strip()
                found = _find_text(nested, keys)
                if found is not None:
                    return found
            return None
        case list():
            for nested in value:
                found = _find_text(nested, keys)
                if found is not None:
                    return found
            return None
        case str() | int() | float() | bool() | None:
            return None
        case unreachable:
            assert_never(unreachable)


def _is_success_status(status_code: int) -> bool:
    return 200 <= status_code < 300


def _presence(value: str | None) -> str:
    return "present" if value is not None else "absent"


def _host(url: str) -> str:
    return urllib.parse.urlparse(url).hostname or "absent"


if __name__ == "__main__":
    raise SystemExit(run_cli(sys.argv[1:], Runtime(environ=None)))
