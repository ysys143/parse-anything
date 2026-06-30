# Track C — ODL Java HybridRequest 확장 (1차 결정론 grounding 전달)

ODL Java를 수정해 hybrid 백엔드 요청에 **1차 결정론 Markdown**을 실어 보낸다. 백엔드(우리 proxy)는
이걸로 grounding하므로 B-4의 **in-proxy 재파싱(odl_extract/pypdfium2)을 제거**한다.

ODL 소스는 `.local/workspace/opendataloader-pdf`(git 미추적, 별도 fork)라 변경을 patch로 보존한다.

## 변경 (3파일, +89/-6) — `hybridrequest-firstpass-markdown.patch`

1. **`HybridClient.java`** — `HybridRequest`에 `firstPassMarkdown` 필드 + `withFirstPassMarkdown()` 빌더 + getter.
2. **`DoclingFastServerClient.java`** — `buildConvertRequest`의 multipart에 `markdown_1st` 파트 추가.
3. **`HybridDocumentProcessor.java`** — `processBackendPath`에 `filteredContents`/`totalPages` 인자 추가 +
   `buildFirstPassMarkdown()` 헬퍼.

### 핵심 메커니즘 (재파싱 0)

- `filteredContents`(1차 결정론 IObject)는 **triage 전에** 이미 계산됨(L269) → 재추출 없음.
- 단, 그건 **raw chunks**라 `MarkdownGenerator`(의미구조만 지원)가 빈 출력. 그래서 chunk 페이지에
  `processJavaPath`를 적용해 의미구조(SemanticParagraph/TableBorder/...)로 변환 후 직렬화.
- **함정**: `processJavaPath`는 heading-level 후처리를 안 거쳐 `SemanticHeading.getHeadingLevel()`이
  `null` → `MarkdownGenerator.writeHeading`에서 NPE → 0 chars. **unset level을 1로 보정**해 해결.

## 빌드 / 적용

```bash
cd .local/workspace/opendataloader-pdf
git apply <this-dir>/hybridrequest-firstpass-markdown.patch   # 또는 이미 적용돼 있으면 생략
cd java && mvn clean package -DskipTests                       # Maven 3.9.10, Java 17
# 산출 JAR을 사용 venv에 교체:
cp opendataloader-pdf-cli/target/opendataloader-pdf-cli-0.0.0.jar \
   <venv>/lib/python3.12/site-packages/opendataloader_pdf/jar/opendataloader-pdf-cli.jar
```

## proxy(B-4) 측 (worktree-b, track-b)

`det_aug.make_grounding_hook(use_supplied=...)` + proxy `--ignore-supplied` 플래그로 전환:
- **Track C**: `proxy --det-aug` → ODL이 보낸 `markdown_1st`로 grounding (재파싱 0)
- **B-4**: `proxy --det-aug --ignore-supplied` → in-proxy 재파싱

## 측정 (born-digital, 고난이도)

`hard.pdf`(밀집 16×7 표)·`wide.pdf`(18열 광폭), full mode, 완전 oracle(텍스트레이어):

| 경로 | hard recall/prec | wide recall/prec | 출력 |
|------|---|---|---|
| 직접 VLM | 0.989/0.989 | 0.987/1.0 | 동일 |
| B-4 (재파싱) | 0.989/0.989 | 0.987/1.0 | 동일 |
| Track C (전달) | 0.989/0.989 | 0.987/1.0 | 동일 |

**결론(정직)**:
- **grounding은 깨끗한 born-digital에선 직접 VLM 대비 실이득 0** — Gemini가 이미 정확히 읽어 grounding이
  더 줄 게 없다. (우리가 반복 확인한 "born-digital은 변종 무관"이 Track C에서도 성립.)
- **Track C(전달) = B-4(재파싱) 출력 완전 동일** — Track C는 B-4의 재파싱을 ODL 전달로 정확히 대체.
  프로토콜 확장은 성공(markdown_1st 1133자 왕복 입증), 결과는 B-4와 동등.
- Track C의 유일한 이점(재파싱 제거)은 지연인데, VLM API 지연(수 초)에 묻혀 이 코퍼스에선 미미.
- Track C의 가치가 드러날 영역은 born-digital 정확도가 아니라 (a) 재파싱 비용이 지배적인 대규모 배치
  (b) F22의 cross-page 표·조작숫자-0-보장 같은 별도 축 — 둘 다 여기선 미측정.
