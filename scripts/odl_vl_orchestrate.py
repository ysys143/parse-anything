from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal, Protocol, TextIO, TypedDict


_REPO_ROOT: Final = Path(__file__).resolve().parents[1]
_SRC_ROOT: Final = _REPO_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from odl_vl.config import Settings, load_settings  # noqa: E402
from odl_vl.ir import NormalizedPage  # noqa: E402
from odl_vl.normalizers import (  # noqa: E402
    extract_gemini_text,
    normalize_gemini,
    normalize_paddle,
    try_decode_json,
)
from odl_vl.orchestrator import (  # noqa: E402
    OrchestratorConfig,
    PageResult,
    ProviderCallable,
    orchestrate_document,
)
from odl_vl.orchestrator_input import (  # noqa: E402
    DocumentInput,
    PageInput,
    load_document_input,
)
from odl_vl.paddle_jobs import (  # noqa: E402
    extract_job_id,
    find_result_json_url,
    poll_job,
)
from odl_vl.providers import (  # noqa: E402
    DEFAULT_PADDLE_MODEL,
    GeminiGenerateContentRequest,
    HttpRequest,
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
from odl_vl.router import RouteDecision  # noqa: E402


_DEFAULT_MANIFEST: Final = _REPO_ROOT / "tests" / "fixtures" / "manifest.json"

Mode = Literal["offline", "live"]


class Sleeper(Protocol):
    def __call__(self, seconds: float) -> None: ...


class ParsedArgs(TypedDict):
    input: str
    output_dir: str
    mode: Mode
    manifest: str
    intent_prompt: str | None
    timeout_seconds: float
    poll_interval_seconds: float
    max_workers: int


@dataclass(frozen=True, slots=True)
class Runtime:
    environ: Mapping[str, str] | None = None
    transport: Transport = field(default_factory=UrllibTransport)
    stdout: TextIO = sys.stdout
    sleep: Sleeper = time.sleep


def run_cli(argv: Sequence[str], runtime: Runtime) -> int:
    args = _parse_args(argv)
    document = load_document_input(args["input"])
    family_metadata = _load_family_metadata(args["manifest"])

    paddle_provider, gemini_provider = _build_providers(args, runtime)
    output_dir = Path(args["output_dir"])
    config = OrchestratorConfig(
        family_metadata=family_metadata,
        paddle_provider=paddle_provider,
        gemini_provider=gemini_provider,
        ledger_path=output_dir / "ledger.jsonl",
        max_workers=args["max_workers"],
    )

    results = orchestrate_document(document, config)
    _write_outputs(output_dir, results)
    _print_summary(document, results, args["mode"], runtime.stdout)
    return 0 if all(result.status == "ok" for result in results) else 1


def _parse_args(argv: Sequence[str]) -> ParsedArgs:
    parser = argparse.ArgumentParser(description="ODL-VL external orchestration over ODL-like page JSON")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--mode", choices=("offline", "live"), default="offline")
    parser.add_argument("--manifest", default=str(_DEFAULT_MANIFEST))
    parser.add_argument("--intent-prompt", default=None)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--max-workers", type=int, default=1, help="Process pages concurrently (live mode)")
    namespace = parser.parse_args(argv)
    return {
        "input": namespace.input,
        "output_dir": namespace.output_dir,
        "mode": namespace.mode,
        "manifest": namespace.manifest,
        "intent_prompt": namespace.intent_prompt,
        "timeout_seconds": namespace.timeout,
        "poll_interval_seconds": namespace.poll_interval,
        "max_workers": max(1, namespace.max_workers),
    }


def _load_family_metadata(path: str | Path) -> Mapping[str, Mapping[str, object]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    families = payload.get("families") if isinstance(payload, Mapping) else None
    return families if isinstance(families, Mapping) else {}


def _build_providers(args: ParsedArgs, runtime: Runtime) -> tuple[ProviderCallable, ProviderCallable]:
    if args["mode"] == "offline":
        return _offline_paddle, _offline_gemini
    # Resolve .env from the repo root so live config does not depend on the CWD.
    settings = load_settings(env_file=_REPO_ROOT / ".env", environ=runtime.environ)
    live = LiveProviders(settings=settings, runtime=runtime, args=args)
    return live.paddle, live.gemini


# --- offline synthetic providers (no network) -------------------------------


def _offline_paddle(page: PageInput, _decision: RouteDecision) -> NormalizedPage:
    text = f"{page.first_pass_md}\n\n<!-- paddle offline OCR placeholder: {page.fixture_family} -->"
    result = {"layoutParsingResults": [{"markdown": {"text": text}, "confidence": 0.5}]}
    return normalize_paddle(result, ledger_fields={"mode": "offline"})


def _offline_gemini(page: PageInput, _decision: RouteDecision) -> NormalizedPage:
    description = f"synthetic visual summary for {page.fixture_family}"
    return normalize_gemini(
        page.first_pass_md,
        image_description=description,
        ledger_fields={"mode": "offline"},
    )


# --- opt-in live providers (real provider calls) ----------------------------


@dataclass(frozen=True, slots=True)
class LiveProviders:
    settings: Settings
    runtime: Runtime
    args: ParsedArgs

    @property
    def _client(self) -> ProviderHttpClient:
        # Wrap so live HTTP/URL errors become status codes and surface as
        # gemini_http_<code>/paddle_*_<code> rather than opaque URLError.
        return ProviderHttpClient(SafeTransport(self.runtime.transport))

    def gemini(self, page: PageInput, _decision: RouteDecision) -> NormalizedPage:
        if self.settings.gemini_api_key is None:
            raise RuntimeError("missing_gemini_api_key")
        prompt = page.intent_prompt or self.args["intent_prompt"] or _default_prompt(page)
        request = build_gemini_generate_content_request(
            GeminiGenerateContentRequest(api_key=self.settings.gemini_api_key, prompt=prompt)
        )
        response = self._client.send(request)
        if response.status_code != 200:
            raise RuntimeError(f"gemini_http_{response.status_code}")
        text = extract_gemini_text(try_decode_json(response.body))
        if text is None or text.strip() == "":
            # A 200 with no usable text (safety block, empty candidates) is a real
            # failure, not a successful empty page.
            raise RuntimeError("gemini_empty_text")
        return normalize_gemini(text, ledger_fields={"mode": "live"})

    def paddle(self, page: PageInput, _decision: RouteDecision) -> NormalizedPage:
        if self.settings.paddle_api_key is None or self.settings.paddle_base_url is None:
            raise RuntimeError("missing_paddle_api_key_or_base_url")
        api_key = self.settings.paddle_api_key
        base_url = self.settings.paddle_base_url
        model = self.settings.paddle_model or DEFAULT_PADDLE_MODEL
        submit = self._client.send(
            build_paddle_submit_request(
                PaddleSubmitRequest(
                    api_key=api_key,
                    base_url=base_url,
                    document_url=page.page_image,
                    model=model,
                )
            )
        )
        job_id = extract_job_id(try_decode_json(submit.body))
        if not is_success_status(submit.status_code) or job_id is None:
            raise RuntimeError(f"paddle_submit_{submit.status_code}")
        completion = self._poll_paddle(api_key, base_url, job_id)
        result_doc = self._fetch_paddle_result(completion)
        return normalize_paddle(_extract_paddle_result(result_doc), ledger_fields={"mode": "live"})

    def _fetch_paddle_result(self, completion: object) -> object:
        # The completed job exposes the layout result behind a signed URL
        # (data.resultUrl.jsonUrl). Fetch it through the same transport; never
        # log the signed URL or the raw result body.
        json_url = find_result_json_url(completion)
        if json_url is None:
            raise RuntimeError("paddle_result_url_missing")
        response = self._client.send(HttpRequest(method="GET", url=json_url, headers={}))
        if not is_success_status(response.status_code):
            raise RuntimeError(f"paddle_result_{response.status_code}")
        return try_decode_json(response.body)

    def _poll_paddle(self, api_key: str, base_url: str, job_id: str) -> object:
        outcome = poll_job(
            client=self._client,
            build_request=lambda: build_paddle_poll_request(
                PaddlePollRequest(api_key=api_key, base_url=base_url, job_id=job_id)
            ),
            timeout_seconds=self.args["timeout_seconds"],
            poll_interval_seconds=self.args["poll_interval_seconds"],
            sleep=self.runtime.sleep,
            now=time.monotonic,
        )
        match outcome.terminal:
            case "complete":
                return outcome.body
            case "failed":
                raise RuntimeError(f"paddle_status_{outcome.status}")
            case "http_error":
                raise RuntimeError(f"paddle_poll_{outcome.status_code}")
            case "timeout":
                raise RuntimeError("paddle_poll_timeout")


def _default_prompt(page: PageInput) -> str:
    return f"Describe and transcribe page {page.page_id} as markdown."


def _extract_paddle_result(body: object) -> object:
    if isinstance(body, Mapping):
        result = body.get("result")
        if isinstance(result, Mapping) and "layoutParsingResults" in result:
            return result
    return body


# --- output writing ---------------------------------------------------------


def _write_outputs(output_dir: Path, results: Sequence[PageResult]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    pages_dir = output_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    results_path = output_dir / "results.jsonl"
    with results_path.open("w", encoding="utf-8") as results_file:
        for ordinal, result in enumerate(results):
            # Use the write ordinal (always unique) so page_ids that slug to the
            # same string cannot overwrite each other's markdown.
            markdown_name = f"page-{ordinal:03d}-{_slug(result.page_id)}.md"
            markdown = result.normalized.markdown if result.normalized is not None else ""
            (pages_dir / markdown_name).write_text(markdown, encoding="utf-8")
            record = result.to_record()
            record["markdown_file"] = f"pages/{markdown_name}"
            results_file.write(json.dumps(record, sort_keys=True, separators=(",", ":")))
            results_file.write("\n")


def _print_summary(
    document: DocumentInput,
    results: Sequence[PageResult],
    mode: Mode,
    stdout: TextIO,
) -> None:
    providers = ",".join(sorted({str(result.provider) for result in results}))
    ok = sum(1 for result in results if result.status == "ok")
    print(
        f"document={document.document_id} mode={mode} pages={len(results)} "
        f"ok={ok} providers={providers}",
        file=stdout,
    )
    # Surface failed pages so an incomplete run is never silent.
    for result in results:
        if result.status != "ok":
            print(f"failed page={result.page_id} reason={result.error}", file=stdout)


# --- helpers ----------------------------------------------------------------


def _slug(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)


if __name__ == "__main__":
    raise SystemExit(run_cli(sys.argv[1:], Runtime(environ=None)))
