# PDF Pipeline Requirements

> 상태: 필수 목표 계약. 현재 구현 완료 선언이 아니라, ODL-VL이 만족해야 하는 PDF 파싱 파이프라인 요구사항이다.
> 적용 범위: 복잡한 PDF를 Markdown, 구조 보존 JSON, 표/이미지 asset, 합본 출력, ledger로 변환하는 end-to-end 파이프라인.
> 운영 경계: processing tier와 domain adaptation 요구사항은 `processing-tiers-and-adaptation.md`가 규정한다.

## 1. Scope and Non-Goals

이 문서는 현재 외부 오케스트레이터 slice보다 넓은 목표 계약이다. 현재 구현은 ODL-like page JSON을 받아 provider를 라우팅하고 per-page markdown/ledger를 쓰는 scaffold다. 최종 파이프라인은 PDF 입력부터 렌더, 결정론 추출, 처리깊이 판단, VLM escalation, 사람 검토 대상 분리, 문서 레벨 병합, 검증 ledger까지 포함해야 한다.

VLM은 숫자 진실성의 source of truth가 아니다. VLM은 구조, 레이아웃, 설명, 누락된 visual context 보강을 담당하고, born-digital 숫자와 텍스트는 결정론 추출 결과가 우선한다.

## 2. Mandatory Requirements

1. 페이지 방향 인식과 보정은 필수다. 회전, skew, 다단 문서의 읽기순서가 downstream markdown/json/table assembly에 반영되어야 한다.
2. 복잡한 표, 병합셀, 중첩 헤더, 단위 row는 텍스트 휴리스틱만으로 처리하지 않는다. ODL의 의미 table 요소, 행/열/셀 bbox, 또는 동등한 구조 추출이 필요하다.
3. OCR/VLM이 필요 없는 born-digital 페이지는 자동으로 결정론 처리한다. processing depth는 fuzzy score가 아니라 명시 트리거 집합으로 결정한다.
4. 페이지에 걸친 표는 하나의 logical table로 인식하고 재구성한다.
5. VLM 입력은 결정론 파싱 데이터, 페이지 이미지, 방향 보정 정보, 커스텀 프롬프트를 함께 포함한다. 페이지에 걸친 표나 이미지는 자동으로 multi-image 입력이 되어야 한다.
6. 출력은 페이지별 markdown/json과 문서 합본 markdown/json을 모두 제공한다. JSON은 표, 셀, bbox, page reference, confidence, guard flag를 보존해야 한다.
7. ledger는 페이지별 route, provider, 비용, 지연, guard flag, confidence, escalation reason을 기록한다.

## 3. Input and Rendering Pipeline

1. PDF 입력은 페이지 이미지로 렌더한다. 기본 렌더러는 라이선스가 clean한 pypdfium2 계열을 우선하며, 고DPI 렌더를 지원해야 한다.
2. 결정론 추출은 텍스트, bbox, reading order 후보, 표 영역, 의미 table 요소를 만든다. born-digital 문서의 정확한 숫자와 구조는 이 단계가 보존한다.
3. scan vs born-digital 판정은 pdf-inspector classify 결과와 텍스트 char 수를 함께 사용한다.
4. 처리깊이 결정은 아래 트리거 집합으로 한다. 기본값은 결정론 처리이며, 트리거가 있으면 VLM/OCR로 escalation한다.
   - 스캔 또는 text layer 부재
   - 그림, 차트, diagram 의미 설명 필요
   - 인코딩 깨짐, CID/ToUnicode 문제, 비정상 글리프
   - 산술 불변식 실패
   - 결정론 table/reading-order/bbox 불완전
   - 낮은 품질, 회전, skew, orientation 불확실
5. Escalation 적극성은 비용/품질/위험 정책 knob로 둔다. 이 값은 실제 코퍼스와 골든셋에서 보정해야 하며, provider 호출을 임의로 늘리는 free-form score로 쓰지 않는다. DET/VLM/HUM 계층 경계와 도메인별 보정 도구는 `processing-tiers-and-adaptation.md`를 따른다.

## 4. Table Policy

복잡한 표는 두 단계로 처리한다.

1. 결정론 단계에서 table region, row, column, cell, bbox, text token을 수집한다.
2. VLM 단계는 병합셀 구조, 헤더 계층, visual grouping, continuation 여부를 보강한다.

페이지에 걸친 표는 다음 규칙으로 인식한다.

1. 연속 페이지의 table bbox 열 좌표, column count, header 또는 continuation caption, y-position 패턴을 비교한다.
2. 연속성이 높으면 해당 페이지들을 multi-image 단일 VLM 요청으로 보낸다.
3. 병합된 logical table은 시작 페이지에 부착한다. continuation 페이지에는 folded reference를 남기고 중복 표를 만들지 않는다.
4. 3쪽 이상 표는 overlap chunk로 나눈다. 각 chunk는 인접 페이지를 겹쳐 보내고, chunk 결과는 table id와 column signature로 병합한다.
5. 병합 후 JSON은 `source_pages`, `source_regions`, `continued_from`, `continued_to`, `cells[].bbox`, `cells[].source_text` 같은 provenance를 보존해야 한다.

## 5. VLM Call Recipe

VLM 요청은 다음 입력을 포함한다.

- 결정론 markdown 후보
- 결정론 JSON 후보: 텍스트 token, bbox, table regions, cell candidates, source page ids
- 방향 인식/보정 결과: rotation, skew, corrected image metadata
- 페이지 이미지: 단일 페이지 또는 자동 multi-image
- 커스텀 프롬프트: 문서/사용자 목적별 구조화 지시
- guard policy: 숫자 oracle, source gate, arithmetic invariant

VLM 출력은 구조 보강 결과로 취급한다. 숫자 값은 결정론 source text와 매칭된 경우에만 신뢰한다. VLM이 source에 없는 숫자를 생성하면 거부하거나 flag한다.

## 6. Numeric Accuracy and Hallucination Guards

Born-digital 문서는 숫자 oracle을 주입한다. 텍스트 레이어에서 추출한 값을 셀 후보에 넣고, VLM이 숫자를 새로 읽거나 추측하지 않게 한다.

필수 guard는 다음과 같다.

1. Source gate: VLM 출력 숫자가 결정론 source text에 없으면 거부하거나 flag한다.
2. Arithmetic invariant: 소계 = 라인 합, VAT = 소계 x 1.1, 수량 x 단가 = 합계 같은 문서별 불변식을 검증한다.
3. Escalation gate: 결정론 결과가 arithmetic invariant를 깨면 VLM/OCR 또는 사람 검토로 보낸다.
4. Scan guard: oracle이 없는 스캔 문서는 프롬프트 기권, 이중 provider pass, 입력 품질 게이팅을 함께 적용한다.
5. Human review: 스캔에서 잔여 위험 셀만 사람 검토 대상으로 남긴다. 완전 자동 숫자 신뢰를 약속하지 않는다.

검증 목표는 hallucinated number 차단, 낮은 오거부율, flag된 셀과 미flag 셀의 신뢰도 분리다.

## 7. Output Contract

최종 산출물은 최소 아래를 포함한다.

- `pages/`: 페이지별 markdown
- `document.md`: 문서 합본 markdown
- `document.json`: loss-aware 구조 JSON
- `tables/`: logical table별 JSON/HTML/Markdown view
- `assets/`: 추출 또는 렌더된 이미지/표 crop metadata
- `results.jsonl`: 페이지별 route/provider/status/output pointers
- `ledger.jsonl`: route, provider, cost, latency, guard flags, confidence, escalation reason

Markdown은 사람이 읽기 좋은 view다. JSON은 source of truth이며, element id, page id, bbox, table/cell hierarchy, source text, asset pointer, continuation relation을 보존해야 한다.

## 8. Verification Contract

검증은 실제 코퍼스 30~50페이지와 골든셋으로 한다. 현재 소수 샘플만으로 품질을 주장하지 않는다.

필수 지표:

- reading order accuracy
- page orientation correction accuracy
- complex table fidelity / TEDS
- page-spanning table reconstruction accuracy
- numeric accuracy
- hallucination rate
- source-gate false reject rate
- routing / processing-depth accuracy
- provider cost and latency
- guard flag precision/recall
- human-review volume and precision
- domain adaptation before/after error and cost deltas

코퍼스는 born-digital, scan, 다단, 회전/skew, 복잡 표, 페이지 걸친 표, 그림/차트, 산술 불변식이 있는 문서, 민감 문서 제약 케이스를 포함해야 한다.

## 9. Licensing and Privacy Constraints

라이선스 clean path를 우선한다.

- Prefer: pypdfium2, pdf-inspector, OpenDataLoader/ODL
- Avoid by default: PyMuPDF / PyMuPDF4LLM, unless AGPL or commercial-license implications are explicitly accepted

민감 문서는 provider I/O 제약을 route 결정에 반영한다. PaddleOCR official API가 이미지 URL fetch만 지원하고 base64 inline image를 지원하지 않는 경로라면, 공개 호스팅이 필요한 민감 문서에는 부적합하다. 그런 문서는 inline image 지원 provider, private network hosting, or local/self-hosted provider 경로로만 보낸다.

## 10. Current Implementation Gap

현재 구현은 아래만 충족한다.

- ODL-like page JSON 입력
- per-page `first_pass_md`, `page_image`, `intent_prompt` 계약
- deterministic/Paddle/Gemini route 선택
- offline/live provider seam
- per-page markdown 파일, `results.jsonl`, `ledger.jsonl`

아직 없는 것:

- PDF 입력과 pypdfium2 렌더
- ODL 실행/결정론 추출 통합
- 방향 인식/보정
- processing depth 자동화
- 복잡 표 구조 JSON 정규화
- 페이지 걸친 표 재구성
- multi-image VLM 요청
- 숫자 oracle/source gate/arithmetic invariant
- asset manifest와 문서 합본 출력
- 30~50페이지 코퍼스 기반 scorecard
