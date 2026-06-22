from __future__ import annotations

import argparse
import sys
import time
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
from odl_vl.jsonsearch import find_first_string  # noqa: E402
from odl_vl.normalizers import try_decode_json  # noqa: E402
from odl_vl.paddle_jobs import extract_job_id, poll_job  # noqa: E402
from odl_vl.providers import (  # noqa: E402
    DEFAULT_GEMINI_MODEL,
    DEFAULT_PADDLE_MODEL,
    GeminiGenerateContentRequest,
    PaddlePollRequest,
    PaddleSubmitRequest,
    ProviderHttpClient,
    SafeTransport,
    Transport,
    UrllibTransport,
    build_gemini_generate_content_request,
    build_paddle_poll_request,
    build_paddle_submit_request,
    is_success_status,
)


DEFAULT_PADDLE_DEMO_URL: Final = (
    "https://paddle-model-ecology.bj.bcebos.com/paddlex/imgs/demo_image/paddleocr_vl_demo.png"
)
_GEMINI_BASE_URL: Final = "https://generativelanguage.googleapis.com"
_GEMINI_PROMPT: Final = "Return exactly: ok"


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
class PaddleLiveConfig:
    api_key: str = field(repr=False)
    base_url: str
    model: str


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

    client = ProviderHttpClient(SafeTransport(runtime.transport))
    request = build_gemini_generate_content_request(
        GeminiGenerateContentRequest(api_key=settings.gemini_api_key, prompt=_GEMINI_PROMPT)
    )
    response = client.send(request)
    text = find_first_string(try_decode_json(response.body), frozenset({"text"}), strip=True)
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
    client = ProviderHttpClient(SafeTransport(runtime.transport))
    submit_response = client.send(
        build_paddle_submit_request(
            PaddleSubmitRequest(
                api_key=config.api_key,
                base_url=config.base_url,
                document_url=args["demo_url"],
                model=config.model,
            )
        )
    )
    job_id = extract_job_id(try_decode_json(submit_response.body))
    if not is_success_status(submit_response.status_code) or job_id is None:
        print(f"provider=paddle live=fail submit_status={submit_response.status_code}", file=runtime.stdout)
        return 1

    outcome = poll_job(
        client=client,
        build_request=lambda: build_paddle_poll_request(
            PaddlePollRequest(api_key=config.api_key, base_url=config.base_url, job_id=job_id)
        ),
        timeout_seconds=args["timeout_seconds"],
        poll_interval_seconds=args["poll_interval_seconds"],
        sleep=runtime.sleep,
        now=time.monotonic,
    )
    poll_status = _poll_status_label(outcome.terminal, outcome.status, outcome.status_code)
    verdict = "pass" if outcome.terminal == "complete" else "fail"
    print(
        f"provider=paddle live={verdict} "
        f"submit_status={submit_response.status_code} poll_status={poll_status} polls={outcome.polls}",
        file=runtime.stdout,
    )
    return 0 if outcome.terminal == "complete" else 1


def _poll_status_label(terminal: str, status: str | None, status_code: int | None) -> str:
    if terminal == "http_error":
        return f"http_{status_code}"
    if terminal == "timeout":
        return "timeout"
    return status or "unknown"


def _presence(value: str | None) -> str:
    return "present" if value is not None else "absent"


def _host(url: str) -> str:
    return urllib.parse.urlparse(url).hostname or "absent"


if __name__ == "__main__":
    raise SystemExit(run_cli(sys.argv[1:], Runtime(environ=None)))
