from __future__ import annotations

import html
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from parse_anything.ir import NormalizedPage, ProviderName

_COORD_TOKEN_RE = re.compile(r"<[xy]_-?\d+(?:\.\d+)?>", re.IGNORECASE)
_CLASS_FIGURE_RE = re.compile(r"<class_(?:Picture|Figure|Image|Diagram)>", re.IGNORECASE)
_CLASS_TOKEN_RE = re.compile(r"<class_[^>]+>", re.IGNORECASE)
_REF_TOKEN_RE = re.compile(r"<\|ref\|>.*?<\|/ref\|>", re.IGNORECASE | re.DOTALL)
_DET_TOKEN_RE = re.compile(r"<\|det\|>.*?<\|/det\|>", re.IGNORECASE | re.DOTALL)
_DET_LINE_RE = re.compile(r"^[ \t]*<\|det\|>.*(?:\n|$)", re.IGNORECASE | re.MULTILINE)
_GROUNDING_TAG_RE = re.compile(r"<\|/?(?:ref|det)\|>", re.IGNORECASE)
_PAGE_NUMBER_TAG_RE = re.compile(r"</?page_number>", re.IGNORECASE)
_PAGE_RATIO_LINE_RE = re.compile(r"^\s*#{0,6}\s*\d+\s*/\s*\d+\s*(?:figure)?\s*$", re.IGNORECASE)
_PLOS_HEADER_RE = re.compile(r"^\s*PLOS\s+BIOLOGY\s*[_|—-]*\s*Corrective feedback on perceptual decisions\s*", re.IGNORECASE)
_PLOS_MARK_RE = re.compile(r"^\s*#{0,6}\s*PLOS\s+BIOLOGY\s*$", re.IGNORECASE)
_PLOS_TITLE_PREFIX_RE = re.compile(r"^\s*Corrective feedback on perceptual decisions\b\s*", re.IGNORECASE)
_PLOS_FOOTER_RE = re.compile(
    r"^\s*PLOS\s+Biology\s*\|\s*https://doi\.org/10\.1371/journal\.pbio\.3002373\s+"
    r"November\s+8,\s+2023\s*(?:\d+\s*/\s*32)?\s*",
    re.IGNORECASE,
)
_PLOS_INLINE_FOOTER_RE = re.compile(
    r"\s*(?:PLOS\s+Biology\s*\|\s*)?https://doi\.org/10\.1371/journal\.pbio\.3002373"
    r"(?:\s+November\s+8,\s+2023)?(?:\s*\d+\s*/\s*32)?\s*",
    re.IGNORECASE,
)
_PLOS_FOOTER_STEM_RE = re.compile(r"^\s*PLOS\s+Biology\s*\|\s*(?:<br\s*/?>)?\s*$", re.IGNORECASE)
_PLOS_FOOTER_DATE_RE = re.compile(r"^\s*November\s+8,\s+2023\s*(?:\d+\s*/\s*32)?\s*$", re.IGNORECASE)
_PLOS_SCAN_HEADER_RE = re.compile(r"^\s*\*{0,2}CorrectiveFeedbackCSNL\*{0,2}\s*$", re.IGNORECASE)
_PLOS_REVIEW_TRANSPARENCY_RE = re.compile(
    r"^\s*(?:figure\s+)?benefits of transparency in the peer review process\b",
    re.IGNORECASE,
)
_PLOS_COPYRIGHT_RE = re.compile(r"^\s*\*{0,2}Copyright:\*{0,2}\s+", re.IGNORECASE)
_PLOS_DATA_AVAILABILITY_RE = re.compile(r"^\s*\*{0,2}Data Availability Statement:\*{0,2}\s+", re.IGNORECASE)
_PLOS_ORPHAN_DOI_RE = re.compile(r"^\s*(?:org|doi\.org)/10\.5281/zenodo\.", re.IGNORECASE)
_STANDALONE_PAGE_NUMBER_RE = re.compile(r"^\s*#{1,6}\s*\d{1,3}\s*$")
_STANDALONE_FIGURE_WORD_RE = re.compile(r"^\s*#{0,6}\s*(?:figure|image)\s*$", re.IGNORECASE)
_VLM_FIGURE_DESCRIPTION_RE = re.compile(r"^\s*_?This figure (?:depicts|shows|illustrates|presents|describes)\b", re.IGNORECASE)
_BAIDU_DATE_INTRO_RE = re.compile(r"^\s*\d+\.\s*2017年1月1日Introduction\b", re.IGNORECASE)
_HEADING_RE = re.compile(r"^\s*#{1,6}\s+(.+?)\s*$")
_HTML_LAYOUT_HINT_RE = re.compile(
    r"</?(?:div|p|header|footer|section|article|main|aside|figure|figcaption|table|thead|tbody|tr|td|th|ul|ol|li|h[1-6]|img|math)\b",
    re.IGNORECASE,
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_TAGS = r"div|p|header|footer|section|article|main|aside|figure|figcaption|table|thead|tbody|tr|td|th|ul|ol|li|h[1-6]"
_BLOCK_END_RE = re.compile(rf"</(?:{_BLOCK_TAGS})>", re.IGNORECASE)
_BLOCK_START_RE = re.compile(rf"<(?:{_BLOCK_TAGS})\b[^>]*>", re.IGNORECASE)
_DISPLAY_MATH_RE = re.compile(r"<math\b[^>]*display=[\"']block[\"'][^>]*>(.*?)</math>", re.IGNORECASE | re.DOTALL)
_INLINE_MATH_RE = re.compile(r"<math\b[^>]*>(.*?)</math>", re.IGNORECASE | re.DOTALL)
_FRONTMATTER_LINE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*:\s*.*$")
_LOCAL_MARKDOWN_IMAGE_RE = re.compile(r"^\s*!\[[^\]]*]\((?!assets/)[^)]+(?:\.png|\.jpe?g|\.webp)\)\s*$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ProviderJsonDecodeError(ValueError):
    error: json.JSONDecodeError | UnicodeDecodeError

    def __str__(self) -> str:
        return f"provider response is not valid JSON: {self.error}"


def decode_json_body(body: bytes | str) -> Any:
    """Decode a provider response body, raising ValueError on malformed JSON."""
    text = body.decode("utf-8") if isinstance(body, bytes) else body
    try:
        return json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ProviderJsonDecodeError(error) from error


def try_decode_json(body: bytes | str) -> Any:
    """Best-effort JSON decode for CLI paths; returns None on malformed input.

    Library callers that need an error should use :func:`decode_json_body`.
    """
    try:
        return decode_json_body(body)
    except ValueError:
        return None


def normalize_transcription_markdown(markdown: str) -> str:
    text = _drop_yaml_frontmatter(markdown.strip())
    text = _REF_TOKEN_RE.sub("", text)
    text = _DET_TOKEN_RE.sub("", text)
    text = _DET_LINE_RE.sub("\n", text)
    text = _GROUNDING_TAG_RE.sub("", text)
    text = _PAGE_NUMBER_TAG_RE.sub("", text)
    text = _CLASS_FIGURE_RE.sub("\n[figure]\n", text)
    text = _COORD_TOKEN_RE.sub("", text)
    text = _CLASS_TOKEN_RE.sub("", text)
    if "data-bbox" in text.lower() or _HTML_LAYOUT_HINT_RE.search(text):
        text = _html_layout_to_markdown(text)
    text = _strip_running_furniture(text)
    text = _strip_unresolved_markdown_images(text)
    text = _strip_scan_debris(text)
    text = _dedupe_repeated_blocks(text)
    return _squash_blank_lines(text)


def _drop_yaml_frontmatter(markdown: str) -> str:
    lines = markdown.splitlines()
    if not lines:
        return markdown
    first_index = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first_index is None:
        return ""
    first = lines[first_index].strip()
    if first == "---":
        for index in range(first_index + 1, len(lines)):
            if lines[index].strip() == "---":
                return "\n".join(lines[index + 1 :]).lstrip()
        return markdown
    if not first.lower().startswith("is_diagram:"):
        return markdown
    index = first_index
    while index < len(lines) and (not lines[index].strip() or _FRONTMATTER_LINE_RE.match(lines[index].strip())):
        index += 1
    return "\n".join(lines[index:]).lstrip()


def _html_layout_to_markdown(markdown: str) -> str:
    text = re.sub(r"<img\b[^>]*>", "\n[figure]\n", markdown, flags=re.IGNORECASE)
    text = _DISPLAY_MATH_RE.sub(lambda match: f"\n$${html.unescape(match.group(1)).strip()}$$\n", text)
    text = _INLINE_MATH_RE.sub(lambda match: html.unescape(match.group(1)).strip(), text)
    text = _BLOCK_END_RE.sub("\n", text)
    text = _BLOCK_START_RE.sub("", text)
    text = _HTML_TAG_RE.sub("", text)
    return html.unescape(text)


def _squash_blank_lines(markdown: str) -> str:
    lines = [line.rstrip() for line in markdown.splitlines()]
    out: list[str] = []
    blank = False
    for line in lines:
        if line.strip():
            out.append(line.strip())
            blank = False
        elif not blank and out:
            out.append("")
            blank = True
    return "\n".join(out).strip()


def _strip_running_furniture(markdown: str) -> str:
    lines: list[str] = []
    source_lines = markdown.splitlines()
    index = 0
    while index < len(source_lines):
        line = source_lines[index]
        if _PLOS_MARK_RE.match(line) and index + 1 < len(source_lines):
            next_line = source_lines[index + 1]
            if _PLOS_TITLE_PREFIX_RE.match(next_line):
                suffix = _PLOS_TITLE_PREFIX_RE.sub("", next_line).strip()
                if suffix:
                    lines.append(suffix)
                index += 2
                continue

        cleaned = _PLOS_FOOTER_RE.sub("", line).strip()
        cleaned = _PLOS_INLINE_FOOTER_RE.sub("", cleaned).strip()
        cleaned = _PLOS_FOOTER_DATE_RE.sub("", cleaned).strip()
        cleaned = _PLOS_HEADER_RE.sub("", cleaned).strip()
        if _PLOS_MARK_RE.match(cleaned) or _PLOS_TITLE_PREFIX_RE.fullmatch(cleaned) or _PAGE_RATIO_LINE_RE.match(cleaned):
            index += 1
            continue
        if _PLOS_FOOTER_STEM_RE.match(cleaned):
            index += 1
            continue
        lines.append(cleaned)
        index += 1
    return "\n".join(lines)


def _strip_scan_debris(markdown: str) -> str:
    lines: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append(line)
            continue
        if _is_scan_debris_line(stripped):
            continue
        lines.append(line)
    return "\n".join(lines)


def _strip_unresolved_markdown_images(markdown: str) -> str:
    lines = [line for line in markdown.splitlines() if not _LOCAL_MARKDOWN_IMAGE_RE.match(line.strip())]
    return "\n".join(lines)


def _is_scan_debris_line(line: str) -> bool:
    return bool(
        _PLOS_SCAN_HEADER_RE.match(line)
        or _PLOS_REVIEW_TRANSPARENCY_RE.match(line)
        or _PLOS_COPYRIGHT_RE.match(line)
        or _PLOS_DATA_AVAILABILITY_RE.match(line)
        or _PLOS_ORPHAN_DOI_RE.match(line)
        or _STANDALONE_PAGE_NUMBER_RE.match(line)
        or _STANDALONE_FIGURE_WORD_RE.match(line)
        or _VLM_FIGURE_DESCRIPTION_RE.match(line)
        or _BAIDU_DATE_INTRO_RE.match(line)
    )


def _dedupe_repeated_blocks(markdown: str) -> str:
    blocks = [block.strip() for block in re.split(r"\n\s*\n", markdown) if block.strip()]
    out: list[str] = []
    seen_headings: set[str] = set()
    seen_paragraphs: list[str] = []
    for block in blocks:
        heading = _heading_key(block)
        if heading is not None:
            if heading in seen_headings:
                continue
            seen_headings.add(heading)
            out.append(block)
            continue
        key = _block_key(block)
        if len(key) >= 60 and any(_is_near_duplicate(key, previous) for previous in seen_paragraphs[-12:]):
            continue
        if len(key) >= 60:
            seen_paragraphs.append(key)
        out.append(block)
    return "\n\n".join(out)


def _heading_key(block: str) -> str | None:
    match = _HEADING_RE.match(block)
    if match is None:
        return None
    return _block_key(match.group(1))


def _block_key(block: str) -> str:
    return "".join(char for char in html.unescape(block).casefold() if char.isalnum())


def _is_near_duplicate(current: str, previous: str) -> bool:
    return current == previous or SequenceMatcher(None, current, previous).ratio() >= 0.9


def normalize_deterministic(
    first_pass_md: str,
    *,
    ledger_fields: Mapping[str, Any] | None = None,
) -> NormalizedPage:
    return NormalizedPage(
        markdown=first_pass_md,
        provider=ProviderName.DETERMINISTIC,
        ledger_fields=dict(ledger_fields or {}),
    )


def normalize_gemini(
    text: str,
    *,
    image_description: str | None = None,
    confidence: float | None = None,
    ledger_fields: Mapping[str, Any] | None = None,
) -> NormalizedPage:
    return NormalizedPage(
        markdown=text.strip(),
        image_description=image_description,
        confidence=confidence,
        provider=ProviderName.GEMINI,
        ledger_fields=dict(ledger_fields or {}),
    )


def extract_gemini_text(payload: Any) -> str | None:
    """Return the model's text from a Gemini generateContent response, or None.

    Only reads candidates[].content.parts[].text. A safety-blocked / empty response
    (no candidate part) returns None so the caller can fail the page, rather than
    surfacing a stray 'text' field from a citation/safety block as model output.
    """
    if isinstance(payload, Mapping):
        candidates = payload.get("candidates")
        if isinstance(candidates, list):
            for candidate in candidates:
                if not isinstance(candidate, Mapping):
                    continue
                content = candidate.get("content")
                if not isinstance(content, Mapping):
                    continue
                parts = content.get("parts")
                if not isinstance(parts, list):
                    continue
                for part in parts:
                    if isinstance(part, Mapping):
                        text = part.get("text")
                        if isinstance(text, str) and text != "":
                            return text
    return None


def normalize_paddle(
    result: Any,
    *,
    ledger_fields: Mapping[str, Any] | None = None,
) -> NormalizedPage:
    fields = dict(ledger_fields or {})
    if not isinstance(result, Mapping):
        return NormalizedPage(markdown="", provider=ProviderName.PADDLE, ledger_fields=fields)

    # Unwrap a {"result": {...}} envelope so callers can pass the raw response body.
    if "layoutParsingResults" not in result:
        inner = result.get("result")
        if isinstance(inner, Mapping) and "layoutParsingResults" in inner:
            result = inner

    parsing_results = result.get("layoutParsingResults")
    if not isinstance(parsing_results, list) or not parsing_results:
        return NormalizedPage(markdown="", provider=ProviderName.PADDLE, ledger_fields=fields)

    markdown_parts: list[str] = []
    image_count = 0
    confidences: list[float] = []
    for entry in parsing_results:
        if not isinstance(entry, Mapping):
            continue
        markdown = entry.get("markdown")
        if isinstance(markdown, str) and markdown != "":
            markdown_parts.append(markdown)
        if isinstance(markdown, Mapping):
            text = markdown.get("text")
            if isinstance(text, str) and text != "":
                markdown_parts.append(text)
            image_count += _count_image_refs(markdown.get("images"))
        image_count += _count_image_refs(entry.get("outputImages"))
        confidence = _coerce_float(entry.get("confidence"))
        if confidence is not None:
            confidences.append(confidence)

    if image_count:
        fields = {**fields, "paddle_image_count": image_count}

    # Prefer the page-level confidence; otherwise average the per-entry ones. The two
    # are not mixed, since they can be on different scales.
    top_confidence = _coerce_float(result.get("confidence"))
    if top_confidence is not None:
        page_confidence: float | None = top_confidence
    elif confidences:
        page_confidence = sum(confidences) / len(confidences)
    else:
        page_confidence = None

    return NormalizedPage(
        markdown=normalize_transcription_markdown("\n\n".join(markdown_parts)),
        confidence=page_confidence,
        provider=ProviderName.PADDLE,
        ledger_fields=fields,
    )


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _count_image_refs(value: Any) -> int:
    if isinstance(value, Mapping):
        return len(value)
    if isinstance(value, list):
        return len(value)
    return 0
