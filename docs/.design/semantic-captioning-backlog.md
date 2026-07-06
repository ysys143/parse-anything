# Semantic Captioning — 잔여 사안 백로그

> [plan](./semantic-captioning-plan.md) · [gap-analysis](./semantic-captioning-gap-analysis.md) ·
> [design](./semantic-captioning-design.md) 기준. 우선순위: P0=관문/선행, P1=핵심, P2=마감, P3=인프라.
> 참조 상용 파서 구체 분석은 `.local/`(미커밋). 코퍼스 66MB도 `.local/` 격리.

## A. 구현 — 트랜치 1 잔여

| # | 사안 | 우선 | 근거/메모 |
|---|---|:--:|---|
| A1 | ~~FR-3.2 Slice 2: describe를 raster content figure로 확장~~ **[완료 6fe3a49]** | — | raster content figure도 description 보유. **불변식 유지**: chart_data 없으면 페이지 텍스트레이어로 게이팅, 검증 불가 수치는 flag. F14(전사 프롬프트)는 불변 |
| A2 | ~~Slice 3: chart_data/description_flags를 Figure export 계약으로 승격~~ **[완료 6fe3a49]** | — | STRUCTURE 계약 1.1→1.2(additive). structure.json까지 보존 |
| A3 | ~~§5-A 단위 토큰 게이팅~~ **[완료]** | — | 차트가 명시 선언한 단위(`단위: 천 명` / `(단위: %)`)를 description이 누락하면 `unit_unstated:<u>` flag. 참조 파서의 "천→명" 오독 대응. bare 한국어 단위(만/천)는 오탐 위험이라 명시 선언만 대상 |
| A4 | ~~grafted(raster) description 미게이팅~~ **[완료]** | — | dropped VLM 중복 figure의 description을 survivor에 graft할 때 gate flags도 함께 이관 → 어떤 경로로도 description이 ungated로 방출되지 않음. (A1이 own description은 게이팅했고, A4가 graft 경로의 잔여 갭을 마감) |
| A5 | ~~raster description flag 노이즈~~ **[완료 리뷰 fix-forward]** | — | flag prefix 분리: `unsourced_number`(chart 자기토큰에 없음=위조의심) vs `unverifiable_number`(raster, born-digital 검증불가=저정보). 소비자가 raster 차트를 hallucination으로 오인하지 않도록 |

## B. 구현 — 트랜치 2 (그린필드 검출기, 미착수)

| # | 사안 | 우선 | 메모 |
|---|---|:--:|---|
| B0 | ~~`Figure.kind` 분류기~~ **[완료]** | — | 벡터 figure를 수치밀도로 chart/diagram 분류(>=2 numeric→chart), 경계는 `kind_confidence:"low"`로 라우터가 게이팅. raster/VLM은 producer kind 유지. **잔여**: kind가 이중 어휘(producer-role "image" vs ontology "chart")—raster normalize는 VLM 신호 필요(B0b) |
| B1 | ~~FR-4.3 폼 KV 검출기 (코어)~~ **[완료·미wire]** | P1 | `forms.py` 결정적 시각 페어링(콜론 라벨 + 기하). 적대적 리뷰 반박(V1-V5) 반영: 라벨 정밀도·V2d 라벨컷오프·V3 거리상한·V4a 빈값·V5 밀도게이트(`detect_form_fields_gated`). **잔여(B1b)**: 파이프라인 wire(form-kind 게이트 필수), AcroForm 소스, 멀티라인 값(V2c) |
| B2 | ~~FR-5.1 도면 치수·공차 검출기 (코어)~~ **[완료·미wire]** | P1 | `dimensions.py` 결정적 정규식(Ø/R/각도/공차/길이). 적대적 리뷰 반박(REQUEST CHANGES) 반영: V4 맥락게이트(shaped≥2), V4b 콤마천단위·시각·전화 분할차단, V2 온도/좌표 제외(°(?![CFNSEW])), V5 `detect_dimensions_gated`. **잔여(B2b)**: wire(drawing-kind 게이트), 표제란 phone/date 잔여 FP, §5-B sum_residual 결합 |
| B3 | ~~FR-5.2 표제란 검출기 (코어)~~ **[완료·미wire]** | P2 | `title_block.py` 다국어 키 사전(Maßstab/Werkstoff/축척/재질/도번) + B1 기하 재사용. 적대적 리뷰 반박(REQUEST CHANGES) 반영: V1 generic 별칭 region 게이팅·V2d 키컷오프·V3 거리상한·V4 `detect_title_block_gated`(자동 우하단 region+밀도게이트). **잔여(B3b)**: wire, 멀티토큰 값 병합·우측정렬(좌측값) 레이아웃(V5) |
| B4 | ~~FR-5.3/5.4 도식·분기 관계 그래프 (코어)~~ **[완료·미wire]** | P2 | `diagram.py` nodes(클러스터링)+edges(커넥터 endpoint→nearest, 경계거리·유한반경)+분기라벨(1:1). 적대적 리뷰 반박(REQUEST CHANGES) 반영: V1 노드클러스터링·V2 bbox방향 ambiguous·V3 경계거리+유한 기본반경·V4 라벨소비·V5 dedup. **잔여(B4b)**: 커넥터/화살촉을 vecfig 벡터경로에서 추출·wire(현재 커넥터 공급원 없음), 방향 검증 |

## C. 구현 — 트랜치 3 (저비용 마감, 미착수)

| # | 사안 | 우선 |
|---|---|:--:|
| C1 | FR-1 이미지 직접 입력(JPG/PNG → PDF 래핑) | P2 하 |
| C2 | FR-4.2 표 HTML/TEDS view 방출(`ir.py:tables_html` 이미 존재) | P2 하 |
| C3 | FR-6 사용자향 confidence 표기 + 정확도차이 고지 | P2 하 |
| C4 | FR-3.1 손글씨·주석·도장 라우팅(PaddleOCR 옵션 활성) | P2 중 |
| C5 | FR-3.3 양방향 검수(텍스트레이어에 있는데 VLM 누락 = recall flag) | P2 중 |
| C6 | FR-7 뷰어 통합(원본 bbox 오버레이 + 마커-캡션) | P2 중 |

## D. 골든셋 / 평가 커버리지 갭

| # | 사안 | 근거 |
|---|---|---|
| D1 | **순수 관계형 도식**(AS-IS/TO-BE 구조도) 라벨 — 현 policy 소스는 표·콜아웃 위주 | gt/README 잔존 |
| D2 | **한국어 필기** 골든 — census는 영문. AI Hub 605 필요 | gt/README 잔존 |
| D3 | score.py 강화: `A_unit`은 substring 휴리스틱, `B_arithmetic`은 form 구조 한정, `G_grounding`은 존재만(IoU 아님) | score.py 스캐폴드 |
| D4 | 실제 파이프라인 산출을 `--out`으로 채점(현재 셀프테스트만) — 트랜치 1 산출로 첫 실채점 가능 | — |

## E. 데이터 / 코퍼스

| # | 사안 |
|---|---|
| E1 | 한국어 dimensioned 도면(한국어 표제란) — KIPRIS 기계 특허 |
| E2 | 정확도 튜닝용 대량셋(DocLayNet·FinTabNet·SciTSR 등) — 현재 시드만, fetch 확장 |
| E3 | fetch.py 한국 공공 URL 드리프트 위험(policy seq/파일명) — 실패 시 SOURCES 수동 확인 |

## F. 인프라 / 하우스키핑

| # | 사안 | 메모 |
|---|---|---|
| F1 | `test_config` 2건 실패 = repo `.env`의 실제 `PADDLE_BASE_URL`이 테스트 placeholder 오염 | 테스트 격리(monkeypatch env) 필요, 사전존재 |
| F2 | `worktree-b`/`worktree-c`(구 `src/odl_vl` 네임스페이스)가 full-suite `pytest` 수집을 깨뜨림 | `pytest tests/` 스코핑 or worktree 정리 |
| F3 | ruff가 셸 PATH에 없음(`.venv/bin/ruff` 부재) | 린트는 Pyright 진단으로 대체 중 |

## G. 결정 대기 (사용자 판단)

- **G1 (=A1)**: F14 정책 반전(캡션을 raster까지) — capability vs cost/philosophy 트레이드오프.
- **G2**: chart_data를 export 계약에 넣을지(스키마 버전 bump) vs semantic view 한정 유지.
- **G3**: 역설계 심화 범위 — 트랜치 2 그린필드 검출기는 pa 본체의 상당한 신규 확장.

---

## 진행 완료 (참고)
- 계획·데이터전략·갭분석·상세설계(트랜치 1~3) 문서화 → `docs/.design/semantic-captioning-*.md`
- 역설계 하네스: `benchmarks/semantic-captioning/`(fetch.py·SOURCES·score.py) + 골든 10라벨·SCHEMA
- 트랜치 1 Slice 1 구현: `output.py` chart_data 구조화 + description oracle 게이팅(테스트 477 passed, 리뷰 APPROVE)
