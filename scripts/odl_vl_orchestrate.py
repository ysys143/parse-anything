from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, TextIO, TypedDict


_REPO_ROOT: Final = Path(__file__).resolve().parents[1]
_SRC_ROOT: Final = _REPO_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from odl_vl.cli_support import Runtime, safe_client  # noqa: E402
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
    find_result_json_url,
    poll_job,
    submit_job,
)
from odl_vl.providers import (  # noqa: E402
    DEFAULT_PADDLE_MODEL,
    GeminiGenerateContentRequest,
    GeminiInlineImage,
    HttpRequest,
    PaddlePollRequest,
    PaddleSubmitRequest,
    ProviderHttpClient,
    build_gemini_generate_content_request,
    build_paddle_poll_request,
    build_paddle_submit_request,
    is_success_status,
)
from odl_vl.router import EXPECTED_ROUTES, RouteDecision  # noqa: E402


_DEFAULT_MANIFEST: Final = _REPO_ROOT / "tests" / "fixtures" / "manifest.json"

Mode = Literal["offline", "live"]


class ParsedArgs(TypedDict):
    input: str
    output_dir: str
    mode: Mode
    manifest: str
    intent_prompt: str | None
    timeout_seconds: float
    poll_interval_seconds: float
    max_workers: int


def run_cli(argv: Sequence[str], runtime: Runtime) -> int:
    args = _parse_args(argv)
    try:
        document = load_document_input(args["input"])
        family_metadata = _load_family_metadata(args["manifest"])
    except (OSError, ValueError) as error:
        print(f"error=input_or_manifest_invalid detail={error}", file=runtime.stdout)
        return 2

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
    if not isinstance(families, Mapping) or not families:
        raise ValueError(f"manifest {path} has no non-empty 'families' mapping")
    for name, meta in families.items():
        if not isinstance(meta, Mapping):
            raise ValueError(f"manifest family '{name}' must be a JSON object, got {type(meta).__name__}")
        expected_route = meta.get("expected_route")
        if expected_route is not None and not isinstance(expected_route, str):
            raise ValueError(f"manifest family '{name}' expected_route must be a string")
        if expected_route is not None and expected_route not in EXPECTED_ROUTES:
            raise ValueError(
                f"manifest family '{name}' expected_route '{expected_route}' is not one of "
                f"{sorted(EXPECTED_ROUTES)}"
            )
    return families


def _build_providers(args: ParsedArgs, runtime: Runtime) -> tuple[ProviderCallable, ProviderCallable]:
    if args["mode"] == "offline":
        return _offline_paddle, _offline_gemini
    # Resolve .env from the repo root so live config does not depend on the CWD.
    settings = load_settings(env_file=_REPO_ROOT / ".env", environ=runtime.environ)
    # Build the HTTP client once (stateless SafeTransport wrapper) and reuse it.
    live = LiveProviders(settings=settings, runtime=runtime, args=args, client=safe_client(runtime))
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
    # Client wraps SafeTransport so live HTTP/URL errors become status codes and
    # surface as gemini_http_<code>/paddle_*_<code> rather than opaque URLError.
    client: ProviderHttpClient

    def gemini(self, page: PageInput, _decision: RouteDecision) -> NormalizedPage:
        if self.settings.gemini_api_key is None:
            raise RuntimeError("missing_gemini_api_key")
        prompt = page.intent_prompt or self.args["intent_prompt"] or _default_prompt(page)
        # Fetch the page image and send it to the VLM so it actually sees the page.
        image = self._fetch_page_image(page.page_image)
        request = build_gemini_generate_content_request(
            GeminiGenerateContentRequest(api_key=self.settings.gemini_api_key, prompt=prompt, image=image)
        )
        response = self.client.send(request)
        if not is_success_status(response.status_code):
            raise RuntimeError(f"gemini_http_{response.status_code}")
        text = extract_gemini_text(try_decode_json(response.body))
        if text is None or text.strip() == "":
            # A 200 with no usable text (safety block, empty candidates) is a real
            # failure, not a successful empty page.
            raise RuntimeError("gemini_empty_text")
        return normalize_gemini(text, ledger_fields={"mode": "live"})

    def _fetch_page_image(self, page_image: str) -> GeminiInlineImage:
        _require_http_url(page_image, "gemini_image")
        response = self.client.send(HttpRequest(method="GET", url=page_image, headers={}))
        if not is_success_status(response.status_code) or not response.body:
            raise RuntimeError(f"gemini_image_fetch_{response.status_code}")
        # Use the Content-Type only if it is a real image/* type; many object stores
        # serve images as application/octet-stream, which the VLM rejects. HTTP header
        # names are case-insensitive, so look it up without assuming the casing.
        header_mime = (_header_value(response.headers, "Content-Type") or "").split(";")[0].strip()
        mime = header_mime if header_mime.startswith("image/") else _guess_image_mime(page_image)
        return GeminiInlineImage(mime_type=mime, data=response.body)

    def paddle(self, page: PageInput, _decision: RouteDecision) -> NormalizedPage:
        if self.settings.paddle_api_key is None or self.settings.paddle_base_url is None:
            raise RuntimeError("missing_paddle_api_key_or_base_url")
        api_key = self.settings.paddle_api_key
        base_url = self.settings.paddle_base_url
        model = self.settings.paddle_model or DEFAULT_PADDLE_MODEL
        # Paddle fetches the document server-side from this URL, so it must be http(s).
        _require_http_url(page.page_image, "paddle_image")
        submit, job_id = submit_job(
            self.client,
            build_paddle_submit_request(
                PaddleSubmitRequest(
                    api_key=api_key,
                    base_url=base_url,
                    document_url=page.page_image,
                    model=model,
                )
            ),
        )
        if not is_success_status(submit.status_code):
            raise RuntimeError(f"paddle_submit_{submit.status_code}")
        if job_id is None:
            raise RuntimeError("paddle_submit_no_job_id")
        completion = self._poll_paddle(api_key, base_url, job_id)
        result_doc = self._fetch_paddle_result(completion)
        normalized = normalize_paddle(result_doc, ledger_fields={"mode": "live"})
        if normalized.markdown == "":
            # A completed job that yields no markdown means the result shape was not
            # recognized (or was empty); fail rather than emit a silently blank page.
            raise RuntimeError("paddle_empty_result")
        return normalized

    def _fetch_paddle_result(self, completion: object) -> object:
        # The completed job exposes the layout result behind a signed URL
        # (data.resultUrl.jsonUrl). Fetch it through the same transport; never
        # log the signed URL or the raw result body.
        json_url = find_result_json_url(completion)
        if json_url is None:
            raise RuntimeError("paddle_result_url_missing")
        response = self.client.send(HttpRequest(method="GET", url=json_url, headers={}))
        if not is_success_status(response.status_code):
            raise RuntimeError(f"paddle_result_{response.status_code}")
        result = try_decode_json(response.body)
        if result is None:
            # A 200 that is not JSON (HTML error/expired-link page) is a real failure,
            # not a silently empty successful page.
            raise RuntimeError("paddle_result_not_json")
        return result

    def _poll_paddle(self, api_key: str, base_url: str, job_id: str) -> object:
        outcome = poll_job(
            client=self.client,
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


def _require_http_url(url: str, context: str) -> str:
    # Live providers fetch (Gemini) or hand off (Paddle) the page image over HTTP, so a
    # non-http(s) reference (e.g. a fixtures:// or file path used in offline data) must
    # fail with a clear, human-readable reason instead of an opaque fetch_0 status.
    if not url.startswith(("http://", "https://")):
        raise RuntimeError(f"{context}_non_http_url")
    return url


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    # HTTP header names are case-insensitive; match without assuming the server's casing.
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return value
    return None


def _guess_image_mime(url: str) -> str:
    guessed, _ = mimetypes.guess_type(url.split("?", 1)[0])
    return guessed if guessed and guessed.startswith("image/") else "image/png"


def _default_prompt(page: PageInput) -> str:
    return f"Describe and transcribe page {page.page_id} as markdown."


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
            # result.error is an opaque provider code (e.g. gemini_http_429); no secret to print.
            print(f"failed page={result.page_id} reason={result.error}", file=stdout)


# --- helpers ----------------------------------------------------------------


def _slug(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)


if __name__ == "__main__":
    raise SystemExit(run_cli(sys.argv[1:], Runtime(environ=None)))
