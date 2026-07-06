# Semantic Captioning — 상세 설계 (드릴다운)

> [gap-analysis](./semantic-captioning-gap-analysis.md)의 각 FR 갭을 코드 근거 위에서 닫는 설계.
> 레버리지 순 트랜치로 진행. file:line은 조사 시점 기준(`src/parse_anything/`), 사용 전 재확인.
> 트랜치 1 = 관문(캡셔닝 정책 + value oracle 캡션 확장 + 차트 반전).

---

## 트랜치 1 — 관문: FR-3.2 · value oracle 캡션 확장 · FR-5.5

세 항목은 물려 있어 하나의 설계다. 결론: **신규 "검출기"는 없다.** pa가 이미 가진
(캡션 프롬프트 + oracle 함수 + 차트값 수집)을 **연결(wiring)**하는 작업이며, 완성되면
참조 파서가 못 하는 "**oracle로 검증된 의미 캡셔닝**"이 된다.

### 이미 존재하는 조각 (재프레이밍)

| 조각 | 위치 | 무엇을 하나 |
|---|---|---|
| 캡셔닝 프롬프트 | `cli.py:22` `_FIG_DESCRIBE_PROMPT` | "축·단위·주요 추세·핵심 값을 2~4문장으로, figure 언어로" = FR-3.2/5.5 그 자체 |
| 값 게이트 | `guards.py:38` `source_gate` | 전사 숫자 중 소스에 없는 것 → fabrication-suspect (§5-A/C) |
| 산술 검산 | `guards.py:47` `sum_residual`, `:55` `ratio_holds` | 부분합≠전체, 비율 붕괴 (§5-B) |
| 차트 내부값 수집 | `output.py:685` `_chart_internal_noise` | 벡터차트 bbox 내부 축·범례·연도·값을 bbox와 함께 수집 |

### 세 개의 단절 (문제)

1. `_FIG_DESCRIBE_PROMPT`이 **벡터차트에만** 적용(`output.py:530` `source=="vector"`) →
   raster figure·도면·스캔 도식엔 캡션 안 붙음.
2. 그 description이 **value oracle을 안 거침** → pa 자신의 figure 설명이 지금 §5-A/B/C 위험에 노출.
   `fabrication_flags`는 `markdown`(전사)에만 호출되고 `Figure.description`엔 미적용.
3. `_chart_internal_noise`가 모은 값(축·범례·수치)을 **폐기**(`_suppress_chart_noise`) →
   description을 검증할 결정적 소스 값을 스스로 버림.

### 관문 결정 (FR-3.2): F14 반전이 아니라 경로 분리

`run.py:20` F14("전사 프롬프트에서 figure 서술 금지")는 **옳다**(전사에 해설 섞이면 오염). 반전 불필요.

- **전사 경로**: `[figure]` placeholder 유지 (F14 존중).
- **캡션 경로(별도)**: `_FIG_DESCRIBE_PROMPT`를 **모든 content figure로 확장**, 산출 description을
  **oracle 게이팅 후** `Figure.description`에 저장.

즉 "정책 반전"이 아니라 **"전사 ⊥ 캡션 분리 + 캡션에 oracle 부착"**. pa 철학("값 안 지어냄")을
깨지 않고 FR-3.2를 켜는 유일한 방법.

### value oracle 캡션 확장 (핵심)

`fabrication_flags(markdown, source_values, min_value=)`를 description에 재사용. 관건은 source set 구성:

```
description numbers ──source_gate──▶ flagged? ──▶ escalate/재생성
        ▲
   source set =
     [텍스트레이어 숫자  deterministic.number_tokens]
   + [_chart_internal_noise가 수집한 축·범례·값]   ← 지금 버리는 그 값
   + [단위 토큰(천/만/%/원/명 …) 정규화]           ← §5-A 전용
```

- **§5-A(단위 오독)**: source set에 축 단위 토큰 포함, description이 raw 숫자에 붙인 단위를 축 단위와 대조.
  불일치 시 flag. (참조 파서 "51,685명" 류 오류를 여기서 포착.)
- **§5-B(산술)**: 차트/표 부분값에 `sum_residual` 적용(함수 기존), description 인용 합계와 대조.
- **§5-C(엔티티)**: 고유명사·식별자는 description에서 VLM 생성 금지, `_chart_internal_noise`/OCR 토큰을
  그대로 인용하도록 프롬프트 제약 + 사후 대조.

난이도 **중**: 신규 검출기 불필요, `guards`/`oracle` 함수를 description에 호출하는 배선 + source set 구성.

### FR-5.5 반전: 폐기 → 구조화 (최저비용 고효과)

`_chart_internal_noise`(`output.py:685-699`)는 이미 벡터차트 bbox 내부 ODL paragraph를 순회하며
캡션/출처가 아닌 것(축·범례·연도·값)을 `p.bbox`+`p.text`와 함께 골라낸다. 지금은 `set[str]`로 만들어
`_suppress_chart_noise`가 prose에서 삭제만 한다. 반전:

```
_chart_internal_noise → (1) prose suppress (현행 유지)
                      → (2) 구조화 추출(신규): Figure.chart_data = {
                             axis_labels[], legend[], series/values[]  ← p.text + p.bbox
                             unit_tokens[]                             ← 정규식
                           }
                      → (3) oracle source set으로 재사용
```

- 버리는 대신 `Figure`에 구조화 필드로 부착 → FR-5.5(축·수치·추세) 달성.
- prose 억제는 유지(embedding 오염 방지) — 삭제와 구조화는 배타적이지 않음.
- 이 구조화 값이 캡션 oracle의 소스 → FR-3.2 검증과 한 몸.

난이도 **중**: 수집·bbox 로직 재사용. 의존: `Figure` 계약에 `chart_data` 필드 추가(`contracts.py:161` 근방),
grounding id-graph에 bbox 이미 있어 좌표 연결 무료.

### 트랜치 1 요약

| 항목 | 실제 작업 성격 | 난이도 | 재사용 |
|---|---|:--:|---|
| FR-3.2 | 전사/캡션 경로 분리 + describe를 content figure 전체로 확장 | 중 | `_FIG_DESCRIBE_PROMPT` |
| oracle 캡션 확장 | `source_gate`/`sum_residual`을 description에 배선 + source set | 중 | `guards.py`/`oracle.py` |
| FR-5.5 | `_chart_internal_noise` 수집물 폐기→구조화(+prose 억제 유지) | 중 | 수집·bbox 로직 |

### 검증 (골든셋 연계)
- `statistics/`(kostat 통계): 단위(천 명) source set 대조로 §5-A 재현 테스트.
- `drawing_dim/`(schneckenwelle): 치수 값 인용 정합(트랜치 2 치수 검출과 결합).
- 회귀: description numbers ⊆ source set 불변식을 Phase 9 하네스에 추가.

---

## 트랜치 2 — 그린필드 검출기: FR-4.3 · 5.1 · 5.2 · 5.3/5.4

신규 검출기가 필요한 항목들. 공통 전략: **결정적 1차(텍스트레이어/AcroForm/기하) → VLM은 관계·라벨링만,
값은 결정적 인용 → grounding id-graph에 bbox로 무료 연결 → oracle로 캡션 검증**. 참조 파서의 §5 결함을
설계 단계에서 구조적으로 배제한다.

### 선행조건 (트랜치 2 공통): `Figure.kind` 분류 활성화

모든 도메인 검출기는 "이 figure가 chart / drawing / diagram / form / photo 중 무엇이냐"로 라우팅된다.
현재 `Figure.kind`(`contracts.py:157`)는 taxonomy 슬롯만 있고 **미할당**(ontology `figure_kinds` 선언만,
`ontology/default.md:17`). → **kind 분류기**가 트랜치 2의 gate이자 FR-2 "taxonomy 미할당" 갭의 해소.
- 결정적 신호(벡터 path 밀도·표제란 존재·격자 라벨·축 텍스트) 1차 + `_FIG_DESCRIBE_PROMPT`(이미 종류를
  열거) 재사용 2차. 산출 kind로 아래 검출기를 스위치.

### FR-4.3 폼 라벨-값(KV)

| | |
|---|---|
| **현 코드** | 폼은 "여러 개의 표"로만 파싱(`structure.py:62-66` 주석). KV 개념·AcroForm 독해 없음. node type에 form/field 없음 |
| **정확한 갭** | 라벨↔값 페어링 부재, 디지털 폼 필드(AcroForm) 미독 |
| **닫는 설계** | 신규 `pipeline/forms.py`. 두 소스: (a) **AcroForm** 필드(pypdfium2 form API) → 라벨/값 결정적; (b) **시각 폼** → ODL 블록 bbox 기하(좌/우·상/하 근접) + 콜론/괄호 라벨 패턴으로 페어링. 신규 export `FormField{id,page,order,label,value,label_bbox,value_bbox,source,confidence,pii}` (contracts.py에 Table/Figure 옆) |
| **oracle/grounding** | value는 결정적(AcroForm/텍스트레이어) → §5-C(엔티티 그대로 인용). VLM은 페어링 제안만. `pii:bool`+마스킹 훅(§5-H). label/value bbox → id-graph 무료 |
| **난이도/의존** | 중 / kind=form 분류 |
| **검증(골든셋)** | `form/`(CORD 영수증 KV), `handwriting/`(census 폼 필드), `insurance/` 약관 표지 폼 |

### FR-5.1 도면 치수·공차

| | |
|---|---|
| **현 코드** | 전무. 벡터 path는 `vecfig.py`가 figure region으로만 |
| **정확한 갭** | 치수선·치수값·공차·기준점(datum) 미인식 |
| **닫는 설계** | 결정적 1차: 텍스트레이어/OCR 토큰에서 치수 패턴 정규식(Ø·R·각도°·±공차·치수숫자) → `DimensionToken{value,kind∈{dia,rad,angle,len,tol},bbox}`. 기하 2차(선택): `vecfig` path에서 치수선(얇은 선+화살표) 근접으로 토큰↔피처 연결. 신규 `DimensionSet{figure_id,tokens[],scale,datums[]}` → Figure(kind=drawing) 부착. 축척은 FR-5.2 표제란에서 공급 |
| **oracle/grounding** | 치수 값=결정적 토큰(§5-C). 캡션 인용 치수는 `source_gate`(§5-A). **부분합=전체**(예 137+678+715 vs 1529)에 `sum_residual`(§5-B, 함수 기존 `guards.py:47`) → 참조 파서 산술 오류를 여기서 포착 |
| **난이도/의존** | 상(기하 결합) / 중(토큰만) / kind=drawing |
| **검증** | `drawing_dim/schneckenwelle`(Ø·공차·GD&T·축척·파라미터표), `drawing/patent`(치수 없음 → 음성 대조) |

### FR-5.2 표제란(title block)

| | |
|---|---|
| **현 코드** | 전무. `doc-title` 룰은 논문 제목용(`ontology/default.md:21`) |
| **정확한 갭** | 도면 우하단 표제란(제작사·축척·재질·도번·날짜) 미추출 |
| **닫는 설계** | **FR-4.3 폼 KV의 특수 케이스**(우하단 테두리 인접 격자 KV) → forms.py 재사용 + 위치 사전. 신규 `TitleBlock{fields,bbox,scale,material,drawing_no}` → Figure(drawing) 부착 |
| **oracle/grounding** | 값 결정적 인용(§5-C). 축척은 FR-5.1 치수 정규화에 공급 |
| **난이도/의존** | 중 / FR-4.3 공유 |
| **검증** | `drawing_dim/schneckenwelle` 표제란(Maßstab 2:1, Werkstoff 16MnCr5) |

### FR-5.3/5.4 도식 관계 · 분기 다이어그램

| | |
|---|---|
| **현 코드** | 관계 엣지는 reading-order/caption/xref만(`output.py:540`). `diagram`은 figure_kinds 라벨값뿐 |
| **정확한 갭** | 도식 내부 노드(박스)·엣지(화살표)·분기 조건 미추출 |
| **닫는 설계** | 노드=도식 bbox 내부 텍스트 블록(=`_chart_internal_noise`가 모으는 토큰의 도식 버전). 엣지=`vecfig` path 중 화살표/커넥터 → 노드 bbox 간 방향 연결. 분기(5.4)=조건 라벨(예/아니오·조건식)을 엣지 속성. 신규 `DiagramGraph{nodes[{id,label,bbox}],edges[{src,dst,label,kind}]}` → Figure(kind=diagram/flowchart) |
| **oracle/grounding** | 노드 라벨=결정적 토큰 인용(§5-C). VLM은 관계 라벨링만. 노드 bbox → id-graph, xref 엣지 인프라 확장(§5-G) |
| **난이도/의존** | 상(가장 높음, 마지막) / kind=diagram, vecfig |
| **검증** | `policy/`(AS-IS/TO-BE 구조도), `insurance/`(지급 분기 다이어그램) |

---

## 트랜치 3 — 저비용 마감: FR-1 · 3.1 · 3.3 · 4.2 · 6 · 7

| FR | 현 코드 | 닫는 설계 | 난이도 | §5 |
|---|---|---|:--:|:--:|
| **1** 이미지 입력 | PDF 전용(`cli.py:156`, `render.py:15` pdfium) | 진입점에서 JPG/PNG/TIFF 감지 → 1페이지 PDF 래핑(img2pdf) → 기존 **스캔 경로**(텍스트레이어 없음 → `SCAN_PROMPT`)로 흐름 | 하 | — |
| **3.1** 손글씨·주석·도장 | PaddleOCR 옵션 전부 False(`paddle_vlm.py:18`) | (a) unwarp/orientation 활성 프로파일; (b) kind=stamp/handwriting일 때 전용 프롬프트 라우팅(스캔 경로에 이미 부분 포섭) | 중 | H |
| **3.3** 양방향 검수 | deterministic→VLM 단방향(`assemble.py:5`) | 역방향 추가: 텍스트레이어에 있는데 VLM이 누락한 값 = recall 플래그(`source_gate` 대칭). 두 방향 diff를 flags로 | 중 | F |
| **4.2** HTML/TEDS view | `ir.py:43` `tables_html` 있으나 미방출, views={md,json}만(`output.py:472`) | `Table.views`에 "html" 추가(셀 grid+span → colspan/rowspan, 데이터 기존 보유). TEDS 스코어러는 `benchmarks/`에만 선택 추가 | 하 | — |
| **6** confidence 표기 | RoleAssignment.confidence·diagnosis·scorecard·flags 내부 보유, 사용자향 약함 | 요소별 confidence를 semantic view/viewer 노출 + 문서 요약("N flagged / M elements, oracle unsourced=K") 리포트. flagged 요소 배지=정확도차이 고지 | 하 | F |
| **7** 뷰어 통합 | `review.html`(원본↔추출 병렬)·`viewer.html`(캡션연동) 분리 | 원본 PNG 위 요소 bbox 오버레이(마커)+클릭 시 caption/description 하이라이트 = `review.py` 이미지 레이어 + `build_viewer.py` `caption_ref` 결합 | 중 | G |

---

## 전체 진입 순서 (합본)

1. **트랜치 1 관문**(캡션/oracle/차트 반전) — 신규 검출기 0, 배선. §5-A/B/C 방어 인프라 확보.
2. **kind 분류기**(트랜치 2 선행) — FR-2 taxonomy 갭 해소 + 검출기 라우팅.
3. **FR-4.3 폼 KV → FR-5.2 표제란**(KV 공유) → **FR-5.1 치수**(§5-B `sum_residual` 결합) → **FR-5.3/5.4 도식**(최난).
4. **트랜치 3 마감**: FR-1(하)·4.2(하)·6(하) 먼저, 3.1·3.3·7(중) 후순위.

**불변 원칙**: 모든 검출기에서 값은 결정적 소스 인용, VLM은 관계·해설만, 캡션 수치는 oracle 게이팅.
이것이 참조 파서의 §5 결함(단위·산술·엔티티)을 pa에서 구조적으로 배제하는 근거.
