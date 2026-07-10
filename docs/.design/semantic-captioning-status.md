# Semantic Captioning — 기능 패리티 현황 스냅샷 (2026-07-10)

> 참조 제품소개서 기반 PRD([semantic-captioning-plan.md](./semantic-captioning-plan.md) FR-1~8)를
> **현재 parse-anything 구현**과 대조한 현황. [gap-analysis](./semantic-captioning-gap-analysis.md)는
> 트랜치-3 착수 **이전** 스냅샷이라 stale — 이 문서가 최신 대조본이다.
> 판정 범례: `[O]` 구현 · `[~]` 부분 · `[=/]` 의도적 상이(못 하는 게 아니라 안 함).
>
> 검증 근거(2026-07-10): `pytest` **601 passed**, 변경 파일 ruff clean.
> 관련 커밋: `78ce3d9`(src 잔여) · `a658e46`(value-axis 벤치) · `168dc0a`(캡션 벤치+골든).

## 1. FR별 패리티 표

| FR | 광고 기능 | 판정 | 현 구현 근거 |
|---|---|:--:|---|
| 1 | 멀티포맷 수집(이미지/PDF/스캔) | O | `imagewrap.image_to_pdf`로 JPG/PNG→1p PDF 래핑, 스캔 경로. **단서**: 원본해상도는 재렌더 DPI |
| 2.1 | 표·차트·도식·치수·폼 영역 검출 | O | 검출기 6종 wire: `forms`/`dimensions`/`title_block`/`diagram`/`vecpaths`/`imagewrap` |
| 2.2/2.3 | 마커·bbox 오버레이 + 캡션 연동 | O | `review.py` 인터랙티브 오버레이(bbox 마커 + 노드 카드 + 클릭 하이라이트) |
| 3.1 | OCR: 인쇄·**손글씨·주석·도장** | ~ | 인쇄/스캔 O. 손글씨/도장/주석은 `routing_hints`로 **"특수 OCR 필요" 표시만, 실제 전사 미실행** |
| 3.2 | VLM 해설 생성(의미·관계·추세 자연어) | =/ | 캡션 생성은 하되 **value oracle로 검증불가 서술을 `unsourced/unverifiable` flag·억제**. 아래 §2-A |
| 3.3 | 두 경로 상호 검수 | O | fabrication(날조) + `recall_missing_number`(누락) 양방향 flag |
| 4.1 | 구조화 JSON | O | 버전드 계약·bbox·캡션·provenance |
| 4.2 | 표 셀구조(행·열·병합) | O | 셀/span/bbox + HTML view 방출 |
| 4.3 | 폼 라벨-값(KV) | O | `forms.detect_form_fields_gated` → `document.json.extractions` |
| 5.1 | 도면 치수·공차 | O | `dimensions.detect_dimensions_gated` (Ø/R/각도/공차/길이) |
| 5.2 | 표제란(title block) | O | `title_block.detect_title_block_gated` (다국어 키 사전) |
| 5.3/5.4 | 도식 관계·분기 | O | `diagram_graph`(nodes+커넥터 edges) — diagram-kind 벡터 figure |
| 5.5 | 차트 축·계열·수치·추세 정량요약 | ~ | `chart_data` 있음, 서술 게이팅 / 축·범례 내부텍스트 방향반전 부분 |
| 6 | 신뢰도 표기·정확도차이 고지 | O | `document.json.quality` 블록(요소/페이지 flag 집계) |
| 7 | 비교 뷰어 | O | §2.2와 동일(review.html) |
| 8 | RAG/Agent export | O | 성숙·강점 — LightRAG 3방식 e2e |

롤업: **O 12 · ~ 2(FR-3.1, 5.5) · 의도적 상이 1(FR-3.2)**. gap-analysis 시점(O 4·~ 8·X 5) 대비 대부분 폐쇄.

## 2. "그대로"가 아닌 3지점 (의사결정 필요)

### A. FR-3.2 의미 캡셔닝 — 철학적 분기 (의도적 상이)
참조 제품은 요소를 보고 자유롭게 해설 산문을 생성한다. parse-anything은 캡션을 만들되
**원본 텍스트레이어에 근거 없는 수치·서술을 flag하고 억제**한다. 기술적으로 "자유 서술"은 가능하나
**의도적으로 안 한다** — 환각 방지(검증가능성)가 제품 차별점. 소개서 문구를 "그대로" 따라가면
이 핵심 가치를 버리는 셈. → 유지가 기본, 변경 시 명시적 의사결정 필요.

### B. FR-3.1 손글씨·도장·주석 OCR — 절반 (실행 미연결)
C4(`_special_ocr_routing_hints`)는 "이 영역에 특수 OCR 필요"라는 **라우팅 힌트 메타데이터만** 방출.
**실제 PaddleOCR 전용 전사 연결은 미구현**. 현재는 "손글씨 위치를 짚어주는" 단계.

### C. 품질 동등은 미입증 (기능 존재 ≠ 정확도 동등)
- 검출기 전부 **결정적 정규식/기하 + 보수적 게이팅** → 전면 VLM 참조 제품보다 recall 낮을 수 있음
  (대신 오탐/날조 적음).
- value-axis 벤치는 **스코어러(`score_value_axis.py`)만 존재, upstream GT 팩트(SEC XBRL 등) 미확보로
  실측 수치 0건**. "된다"는 기능 존재 증명이지 정확도 동등 증명 아님.

## 3. 다음 후보 (택1로 이어서)
- **B 닫기**: PaddleOCR 전용 전사를 `routing_hints` 소비 경로에 연결(FR-3.1 완성).
- **C 실측**: value-axis GT 팩트(SEC XBRL JSONL) 확보 → 참조 대비 수치 산출.
