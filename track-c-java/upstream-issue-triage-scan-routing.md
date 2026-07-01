# Upstream 이슈 초안 (미발행) — triage 스캔 오라우팅

**상태**: **발행됨** (이슈 [#619](https://github.com/opendataloader-project/opendataloader-pdf/issues/619)) + **PR [#620](https://github.com/opendataloader-project/opendataloader-pdf/pull/620)** 제출
**대상**: `opendataloader-project/opendataloader-pdf` (Issues)
**관련 fork 브랜치**: `ysys143/opendataloader-pdf` → `feat/triage-scan-routing` (수정+patch)
**근거 문서**: `worktree-b/docs/measurement-findings.md` F23 (근본원인·재현·baseline 대조표)

발행 시 제목: `Hybrid triage routes full-page scanned pages to the Java path → empty output`

---

## Summary

In hybrid mode with `--hybrid-mode auto`, a **full-page scanned (image-only) page is routed to the Java path**, which cannot transcribe it, producing empty output. The page's text and tables are silently lost — the backend (which could OCR/transcribe it) never sees the page.

## Root cause

`TriageProcessor` routes large images to the backend via `hasLargeImage()`, which requires **both** a size gate and an aspect-ratio gate:

```java
// TriageProcessor.java (SignalAccumulator / TriageSignals)
public boolean hasLargeImage() {
    return largeImageRatio >= MIN_LARGE_IMAGE_RATIO      // 0.11
            && largeImageAspectRatio >= MIN_IMAGE_ASPECT_RATIO; // 1.75
}
```

`largeImageAspectRatio` is `width / height` of the largest image. The `>= 1.75` gate targets **wide** table/chart images (added in Experiment 005), but it also excludes standard document scans:

- Portrait A4 scan: aspect ≈ 0.71 → fails the gate
- Landscape A4 scan: aspect ≈ 1.41 → fails the gate

A full-page scan therefore does not trigger `hasLargeImage()`. With no text layer, none of the other signals (TableBorder / vector-table / text-pattern / line-ratio) fire either, so `classifyPage` falls through to the default `JAVA` decision. The Java path only extracts the embedded image reference, not the content.

## Reproduction

A single-page portrait A4 PDF whose only content is one full-page scanned image (no text layer):

```
$ opendataloader-pdf scan.pdf --format markdown -o out
# out/scan.md (35 bytes):
![](<scan_images/imageFile1.png>)
```

Under `--hybrid-mode auto`, triage classifies this page as JAVA, so the backend is never called and the scanned content is dropped. (`--hybrid-mode full` avoids the bug by skipping triage, but `auto` is the default.)

## Impact

Any scanned / image-only page in an otherwise-`auto` hybrid run loses all of its text and tables, with no error or warning. This affects the common case of scanned documents and scanned pages embedded in born-digital PDFs.

## Suggested direction

Treat a page dominated by a single image with no extractable text as a scan and route it to the backend regardless of aspect ratio, e.g. a leading condition in `hasLargeImage()`:

```java
// Full-page image with no extractable text = scan -> backend (Java yields empty output).
if (largeImageRatio >= FULL_PAGE_IMAGE_RATIO /* e.g. 0.5 */ && textChunkCount == 0) {
    return true;
}
```

This leaves born-digital text pages (textChunkCount > 0) and the existing wide-image path unchanged. I have a working patch and can open a PR if the direction looks right — I'd want to validate it against the benchmark suite first to confirm no NID/TEDS/Table-F1 regression.
