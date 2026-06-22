# VLM Provider and Fixture Plan

> 상태: 개발 결정 기록, 프로덕션 준비 선언 아님  
> 범위: ODL-VL 초기 개발에서 사용할 VLM/OCR provider, serving/routing 구조, fixture/golden-set 전략

## 1. Provider 결정

초기 개발은 **PaddleOCR 공식 API + Gemini direct** 조합으로 진행한다.

- PaddleOCR 공식 API는 OCR/VLM 계열의 주 provider다. 초기 목표는 PaddleOCR-VL-1.6 데모 경로를 기준으로 실제 job 제출, 완료, 결과 수집 흐름을 붙이는 것이다.
- Gemini direct는 비교용 VLM provider이자 fallback 후보로 둔다. Gemini는 직접 API 호출 경로가 이미 통과했으므로 초기 개발에 포함한다.
- Ollama Cloud는 계정 키와 모델 목록 조회가 동작하는 것을 확인했지만, 현재 OCR path의 초기 provider로 보지 않는다. 목표 OCR/VLM 모델은 초기 범위가 아니며, 일부 모델은 subscription이 필요하다.
- NGC/Nemotron과 GLM-OCR/Ollama 경로는 보류한다. 지금은 선택지를 넓히기보다 PaddleOCR 공식 API와 Gemini direct로 평가 루프를 먼저 고정한다.

## 2. 환경 변수 이름

실제 값은 문서에 기록하지 않는다. 로컬, CI, 배포 환경에는 아래 이름만 사용한다.

```bash
GEMINI_API_KEY=<gemini api key>
PADDLE_API_KEY=<paddle official api key>
PADDLE_BASE_URL=<paddle official api base url>
PADDLE_MODEL=<optional paddle model override>
```

`PADDLE_MODEL`은 선택값이다. 지정하지 않으면 구현체의 기본 PaddleOCR-VL 계열 모델을 쓰는 방향으로 둔다.

## 3. 이번 세션에서 확인된 상태

이번 결정의 근거는 실제 호출 가능성과 초기 범위 적합성이다.

- Gemini direct 호출은 통과했다.
- PaddleOCR 공식 API는 PaddleOCR-VL-1.6 데모 job 제출과 완료까지 확인했다.
- Ollama Cloud는 key와 model list 조회가 동작했다. 다만 목표 OCR/VLM 모델은 초기 범위 밖이고, 일부 모델은 subscription이 필요하므로 현재 OCR path에 바로 쓸 수 있다고 약속하지 않는다.
- 위 검증은 개발 착수 가능성을 확인한 수준이다. 품질, 비용, 지연, 장애 대응까지 포함한 운영 준비 상태를 뜻하지 않는다.

## 4. Serving and Routing Architecture

현재 repo 문서는 ODL을 결정론 front 또는 hybrid backend caller로 두고 VLM 2-pass를 붙이는 두 방향을 비교한다. 기존 스파이크 문서는 테스트 코퍼스와 골든셋을 공유 컴포넌트로 두고 평가 공정성을 확보하라고 기록한다. 참고: `docs/parsing-engine-spike-plan.md:30`, `docs/parsing-engine-spike-plan.md:75`.

초기 serving 구조는 provider client를 orchestration layer 뒤에 숨긴다.

1. 입력 PDF를 페이지 이미지와 1차 markdown/json 후보로 분해한다.
2. Routing policy가 페이지별로 deterministic-only, PaddleOCR official API, Gemini direct 중 하나를 고른다.
3. PaddleOCR official API와 Gemini direct는 같은 내부 IR로 정규화한다.
4. 결과는 markdown, json element, bbox, table HTML, confidence, ledger field를 포함하는 비교 가능한 형태로 남긴다.
5. Ledger에는 provider, model alias, route reason, latency, cost estimate, status, fallback 여부를 기록한다. 비밀값은 기록하지 않는다.

ODL 내부 Track A는 현재 hybrid protocol의 한계를 갖는다. 기존 문서에 따르면 backend는 원본 PDF와 page range를 받고, ODL의 1차 markdown이나 prompt field를 받지 않는다. 참고: `docs/parsing-engine-tracks-pdf.md:14`, `docs/parsing-engine-tracks-pdf.md:16`. 그래서 no-fork Track A에서는 adapter가 자체 렌더링과 필요 시 adapter-side 1차 pass를 맡는다. 반대로 외부 orchestration Track B는 ODL local output, prompt policy, VLM call, merge, ledger를 더 자연스럽게 소유한다.

공유 VLM 2-pass 계약은 `page_image`, 선택적 `first_pass_md`, 선택적 `intent_prompt`를 받아 markdown/json/table/image description/confidence를 돌려주는 형태로 둔다. 참고: `docs/parsing-engine-tracks-pdf.md:26`.

## 5. Fixture and Golden-Set Strategy

초기 fixture는 두 층으로 둔다.

- Public generated fixtures 8개: repo에 넣을 수 있는 합성 fixture다. 레이아웃, 언어, 표, 이미지, 회전, 스캔 느낌, text-as-image, 저해상도 같은 실패 모드를 의도적으로 나눈다.
- External manifest/private shadow set: 공개할 수 없는 실제 또는 준실제 문서는 파일 대신 manifest와 평가 메타데이터만 관리한다. 원본은 private storage에 두고, repo에는 fingerprint, fixture family, expected challenge, 평가 결과 요약만 남긴다.

초기 public generated fixture family는 아래 8개로 시작한다.

| Fixture family | 주 실패 모드 | 기대 변별력 |
|---|---|---|
| `simple_text` | born-digital 단순 본문 | deterministic-only가 충분한지 확인 |
| `two_column_ko_en` | 다단, 한영 혼재, 각주 | reading order와 CJK/영문 혼재 처리 |
| `merged_table` | 병합셀, 중첩헤더, 단위 row | 표 구조 보존과 markdown/HTML table 품질 |
| `formula_symbols` | 수식, 첨자, 화살표, 특수기호 | 수식/기호 손실과 OCR 오염 감지 |
| `chart_like_page` | 차트, 다이어그램, 그림 설명 | OCR이 아닌 의미 설명에서 Gemini fallback 효용 확인 |
| `text_as_image` | 텍스트 레이어 없는 이미지 텍스트 | OCR 필요 라우팅과 text recovery |
| `rotated_scan` | 회전, orientation 오류 | orientation classify/unwarping 옵션 효과 |
| `low_quality_scan` | blur, JPEG artifact, 낮은 해상도 | 실전 robustness와 confidence 저하 감지 |

골든셋은 페이지 단위로 관리한다. 각 페이지는 기대 reading order, table structure, key field, image description expectation, bbox tolerance, provider별 허용 차이를 포함한다. 스파이크 계획의 공유 컴포넌트도 골든셋을 페이지별 정답으로 정의한다. 참고: `docs/parsing-engine-spike-plan.md:30`.

## 6. Fixture Sufficiency Criteria

Fixture set은 다음 기준을 만족해야 충분하다고 본다.

- Coverage: 단순 born-digital, 다단 한영 혼재, 병합셀/중첩헤더 표, 이미지 겹침, text-as-image, 수기 또는 회전 글자, 스캔 PDF, 비-PDF 후보가 최소 한 번씩 등장한다.
- Oracle clarity: 각 fixture의 정답이 애매하지 않아야 한다. 사람이 봐도 합의하기 어려운 fixture는 골든셋이 아니라 shadow investigation으로 보낸다.
- Route observability: 각 fixture는 deterministic-only 또는 VLM route 중 기대 경로를 설명할 수 있어야 한다.
- Cost visibility: provider 호출 횟수와 페이지 수를 fixture별로 집계할 수 있어야 한다.
- Repeatability: 같은 입력과 같은 provider 설정에서 의미 있는 출력 차이가 없어야 한다. provider nondeterminism은 ledger에 따로 표시한다.

## 7. Discriminativeness Criteria

Fixture는 provider와 routing policy의 차이를 드러내야 한다. 단순히 모두 통과하거나 모두 실패하면 결정력이 낮다.

다음 신호가 있으면 변별력이 있다고 본다.

- PaddleOCR official API와 Gemini direct의 reading order, table structure, image description, key field extraction 중 하나 이상에서 차이가 난다.
- Deterministic-only 경로와 VLM 경로의 품질 차이가 scorecard에 잡힌다.
- Routing policy 변경이 비용 또는 지연뿐 아니라 품질에도 영향을 준다.
- 실패가 fixture family와 연결된다. 예를 들어 병합셀 표, text-as-image, 회전 글자 같은 원인이 분리되어야 한다.
- 기존 scorecard 항목인 읽기순서, 표 충실도, 그림/다이어그램 서술, OCR 오염 여부, 라우팅 정확도, 비용, bbox 보존, md/json 정확성에 결과가 매핑된다. 참고: `docs/parsing-engine-spike-plan.md:75`.

## 8. 변별력이 낮을 때 할 일

Fixture가 provider 선택이나 routing 결정을 가르지 못하면 fixture를 늘리기 전에 실패 유형을 채굴한다.

1. Mutation mining: 기존 fixture에서 회전, crop, blur, table border 제거, font size 축소, image overlap, language mix 비율을 바꿔 약점을 만든다.
2. Disagreement mining: PaddleOCR official API, Gemini direct, deterministic parser 결과가 서로 다르게 나오는 페이지를 shadow set에서 찾는다.
3. Route conflict mining: deterministic-only로 충분해 보이지만 실제 골든셋에서 깨지는 페이지, 또는 VLM을 호출해도 개선이 없는 페이지를 분리한다.
4. Golden refinement: 정답이 애매해서 점수가 흔들리면 fixture를 버리거나 expected answer를 더 좁힌다.
5. Private shadow promotion: private shadow set에서 공개 가능한 형태로 재생성할 수 있는 실패 패턴을 합성 fixture로 승격한다.

## 9. Deferred Providers

아래 provider는 이번 초기 개발 범위에서 제외한다.

- NGC/Nemotron: 현재는 PaddleOCR official API와 Gemini direct로 provider interface, ledger, scorecard를 먼저 고정한다.
- GLM-OCR/Ollama: Ollama Cloud key와 model list 동작은 확인했지만, 목표 OCR/VLM 모델은 초기 범위가 아니며 일부 모델은 subscription이 필요하다. 현재 OCR path의 즉시 사용 provider로 기록하지 않는다.

보류 provider는 interface가 안정된 뒤 별도 provider adapter와 fixture bake-off로 다시 검토한다.
