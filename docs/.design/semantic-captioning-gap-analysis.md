# Semantic Captioning — 갭 분석 (PRD ↔ parse-anything 현 구현)

> [semantic-captioning-plan.md](./semantic-captioning-plan.md)의 기능 요구사항(FR-1~8)을 현재
> parse-anything 구현과 대조한 갭 분석. 코드 근거는 조사 시점 기준(`src/parse_anything/`), file:line은
> 변동 가능하므로 사용 전 재확인. 참조 상용 파서 관련 구체 분석은 커밋하지 않는다(로컬 전용).
>
> 판정 범례: `[O]` 구현(강점) · `[~]` 부분구현 · `[X]` 미구현

## 1. 판정 요약 (롤업)

| 판정 | 개수 | 항목 |
|---|---|---|
| [O] 구현 (강점) | 4 | FR-2 grounding, FR-4.1 구조화JSON, FR-4.2 표셀구조, FR-8 RAG/Agent |
| [~] 부분 | 8 | FR-1, FR-2 탐지, FR-3.1, FR-3.3, FR-5.5, FR-6, FR-7 (+FR-3.2 극히제한) |
| [X] 미구현 | 5 | FR-4.3 폼KV, FR-5.1 치수, FR-5.2 표제란, FR-5.3 도식관계, FR-5.4 분기도 |

## 2. 메인 갭 표

| FR | 요구 | 판정 | pa 현황 | 갭 성격 | 근거(file) |
|---|---|:--:|---|---|---|
| 1 | 멀티포맷 수집 | [~] | 페이지·스캔·렌더 O / **PDF 전용**, 이미지 직접입력 불가, 원본해상도=재렌더DPI | 기능 제약 | `cli.py:156`, `render.py:22` |
| 2-탐지 | 요소(표·차트·도식·치수·폼) 검출 | [~] | 텍스트블록·표(셀/span/bbox)·raster figure O / 벡터차트 휴리스틱 △ / **차트내부·치수·폼필드 없음, taxonomy 미할당** | 부분+미구현 혼재 | `odl_extract.py:265`, `vecfig.py:67` |
| 2-grounding | 요소↔출력 좌표 연결 | [O] | id-graph: 요소↔bbox↔order↔크롭↔캡션↔xref | **강점** | `structure.py:104`, `output.py:750` |
| 3.1 | OCR(인쇄·손글씨·주석·도장) | [~] | 인쇄·스캔 O / **손글씨·주석·도장 전용경로 없음** | 부분 | `paddle_vlm.py:45`, `run.py:35` |
| 3.2 | **의미 캡셔닝(해설 생성)** | [X] | 메인 프롬프트가 서술 **금지**(`[figure]`만) / 예외 `describe_figure` 벡터차트 한정 자유텍스트 | **의도적 반대** | `run.py:16-22`, `cli.py:22` |
| 3.3 | OCR↔VLM 상호 검수 | [~] | deterministic→VLM **단방향** 게이팅(상호 아님) | 방향성 차이 | `assemble.py:5`, `grounding.py:39` |
| 4.1 | 구조화 JSON | [O] | 버전드 계약·bbox·캡션필드·provenance | **강점** | `contracts.py:255` |
| 4.2 | 표 셀구조(행·열·병합) | [O] | 셀·row/col span·bbox·스패닝 O / **HTML·TEDS 미방출** | 강점(포맷 갭) | `contracts.py:120`, `structure.py:88` |
| 4.3 | 폼 라벨-값(KV) | [X] | 전무 | 그린필드 | — |
| 5.1 | 도면 치수·공차 | [X] | 전무 | 그린필드 | — |
| 5.2 | 표제란(title block) | [X] | 전무 | 그린필드 | — |
| 5.3 | 도식 관계 | [X] | reading-order/caption/xref 엣지뿐 | 그린필드 | `output.py:540` |
| 5.4 | 분기 다이어그램 | [X] | `diagram`은 라벨값뿐, 파싱 없음 | 그린필드 | `ontology/default.md:17` |
| 5.5 | 차트 축/수치/추세 | [~] | 벡터차트 한정 **비구조 산문**만 / 내부 축·범례 텍스트는 **삭제** | 방향 반전 필요 | `output.py:530/685` |
| 6 | 품질 신뢰도 | [~] | 노드·문서 confidence·scorecard·flag **풍부** / 사용자향 표기·정확도차이 고지 약함 | 부분(UI 갭) | `contracts.py:231`, `scorecard.py:54` |
| 7 | 비교 뷰어 | [~] | `review.html`(원본↔추출 병렬) + `viewer.html`(캡션연동) / 통합 인터랙티브 오버레이 없음 | 부분 | `review.py:21`, `scripts/build_viewer.py` |
| 8 | RAG/Agent 연동 | [O] | 버전드 계약+small-to-big chunks+semantic/provenance+LightRAG 3방식 e2e | **성숙·강점** | `contracts.py:310`, `demo/docker/ingest_query.py` |

## 3. 대응 전략 표 (미구현·부분 항목)

| FR | 대응 전략 | 난이도 | pa 강점 재사용 | 리스크(plan §5) 연계 |
|---|---|:--:|---|---|
| 3.2 | F14 "서술 금지" 정책 **명시적 반전** + oracle를 캡션 수치까지 확장(조건부) | 상(정책결정) | value oracle, grounding | A·B·C 방어의 전제 |
| 5.5 | `_chart_internal_noise` **삭제→추출**로 전환(축·범례·수치 구조화) | 중 | 벡터차트 검출(`vecfig`) | A(단위), G(grounding) |
| 4.3 | 폼 KV 검출기 신규(AcroForm + 라벨-값 페어링) | 중 | 표 셀 그리드, bbox | C(엔티티), H(PII) |
| 5.1 | 치수군 검출기 신규(치수선·기호·기준점) | 상 | grounding id-graph | A·B(산술) |
| 5.2 | 표제란 영역 검출 + KV 추출 | 중 | 폼 KV와 공유 | C |
| 5.3/5.4 | 도식·분기 관계 그래프 추출 | 상 | 크로스레퍼런스 엣지 기반 | G |
| 1 | 이미지 입력 → PDF 얇은 래핑 | 하 | 렌더 파이프라인 | — |
| 3.1 | 손글씨·주석·도장 라우팅(PaddleOCR 옵션 활성) | 중 | 스캔 경로 | H |
| 3.3 | 단방향→양방향(VLM 산출을 결정적 소스로 재검수) | 중 | oracle, grounding | F |
| 6 | 사용자향 confidence 표기 + 정확도차이 고지 | 하 | RoleAssignment.confidence, scorecard | F |
| 7 | review+viewer 통합, 원본 bbox 오버레이 | 중 | 두 뷰어, caption_id | G |
| 4.2 | HTML/TEDS view 방출 추가 | 하 | 셀 그리드 이미 보유 | — |

## 4. 핵심 통찰

**갭의 성격은 "덜 만든" 게 아니라 "철학적으로 반대".** PRD 핵심(FR-3.2 의미 캡셔닝, FR-5.* 도메인 해설)을
pa는 의도적으로 거부한다 — `run.py:20-22`(F14): "figure interpretation is the oracle's/human's job."
참조 파서는 VLM-first로 "의미 설명"이 가치의 전부이나 리스크(단위·산술·엔티티 오류)로 대가를 치르고,
pa는 deterministic-first로 "값을 지어내지 않음"이 가치의 전부다. 둘은 같은 축의 양 극단.

**그러나 pa는 참조 파서가 못 가진 하드 기반을 이미 보유:** value oracle(§5-A/B), grounding id-graph(§5-G),
결정적 값 권위(§5-C), 표 구조, 버전드 RAG 계약. 참조 파서의 결함 목록 = pa의 강점 목록.

**따라서 전략은 "역설계 모방"이 아니라 "pa 위에 안전한 캡셔닝 계층 얹기".** 미구현 5개를 pa의
oracle/grounding에 물리면 참조 파서가 못 하는 "지어내지 않는 의미 캡셔닝"이 된다 -> 차별화 포인트.

**진입 순서:** (1) FR-3.2 정책 반전이 관문 — oracle 캡션 확장 조건부. (2) 최저비용 고효과는
FR-5.5 차트 노이즈 삭제->추출 반전. (3) 그린필드 4개(폼·치수·표제란·도식)는 골든셋 기반 Phase 2 확장.
