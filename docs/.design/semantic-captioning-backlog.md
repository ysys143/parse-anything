# Semantic Captioning — 잔여 사안 백로그

> [plan](./semantic-captioning-plan.md) · [gap-analysis](./semantic-captioning-gap-analysis.md) ·
> [design](./semantic-captioning-design.md) 기준. 우선순위: P0=관문/선행, P1=핵심, P2=마감, P3=인프라.
> 참조 상용 파서 구체 분석은 `.local/`(미커밋). 코퍼스 66MB도 `.local/` 격리.

## 다음 우선순위 (D4 실채점 근거 재정렬, 2026-07-06)

첫 실채점(골든 10건, 결정적 + live Paddle전사/Gemini캡션)이 드러낸 사실: **구조 그라운딩·캡션 생성은 작동**
(G_grounding 9/10, must_not 10/10, 캡션 고품질). 실패(적용 42체크 중 18)는 **소수 근본원인에 집중** — verbatim
값 recall(C_entity 9)과 전면 래스터 이미지(drawing_dim 4체크=원인 1개). 이에 맞춰 다음 착수 순서:

- **T1a — verbatim 값 recall** (실패의 절반): B 검출기(dimensions/title_block/forms)가 좁게 게이트돼 ID·코드·
  치수 토큰(SFR-000·16MnCr5·BLEU값·15일)을 채점 필드로 못 올림. 결정적 whole-doc에서도 FAIL → 페이지 스코프
  탓 아님. 값 추출 레이어 확장(게이트 완화 or 표/키-값 recall)이 가장 큰 레버. → B1/B2/B3 잔여와 접점.
- **T1b (=D5) — 전면 래스터 도면 캡셔닝**: 텍스트레이어 없는 전면 이미지를 통째 describable figure로. C1 접점.
- **T1c (=D4 잔여) — 공정 비교**: 결정적도 라벨 페이지만 슬라이스(현재 whole-doc↔page 비대칭). run_bench 옵션화.
- **T2 (=D3) — 채점 신뢰도**: A_unit 구조 매칭, B_arithmetic line_items/totals, G_grounding IoU.
- **T3 — 남은 기능(C 중난도)**: C4 손글씨/도장 라우팅 · C5 양방향 recall 검수 · C6 뷰어 통합.
- **T4 — 데이터·위생**: D1 순수 도식 골든 · D2 한국어 필기 골든 · E1~E3 코퍼스 · **F2 worktree가 full-suite
  pytest 수집 깨뜨림**.

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
| B4 | ~~FR-5.3/5.4 도식·분기 관계 그래프 (코어+wire)~~ **[완료]** | P2 | `diagram.py` nodes(클러스터링)+edges(커넥터 endpoint→nearest, 경계거리·유한반경)+분기라벨(1:1). **B4b wire 완료**: `vecpaths.detect_connectors`(pypdfium2 raw ctypes로 stroked·open 폴리라인 추출, closed 박스·filled 화살촉 제외)→`output._attach_diagram_graphs`가 diagram-kind 벡터 figure에 `diagram_graph`(nodes=chart_data, edges=커넥터) 방출, `Figure.diagram_graph` 계약(+STRUCTURE 1.3). 적대적 리뷰 반박: **①L/직교 커넥터는 실제 폴리라인 끝점(`points`)으로 링크**(bbox 대각 코너는 anti-diagonal에서 팬텀점→오링크/드롭), **②`kind_confidence:"low"` 게이트**(오분류 차트 plot선 팬텀 그래프 차단), **③doc/page 오픈 가드+page_index 범위검증**(export 중단 불가). **잔여(리뷰 LOW)**: per-figure PdfDocument 재오픈 O(N), filled-thin-rect·bezier 커넥터 recall 갭 |

| Bwire | ~~B1/B2/B3 파이프라인 wiring~~ **[완료]** | — | `_extract_document_fields`가 게이트 발동분만 `document.json.extractions`(form_fields/dimensions/title_block)로 방출. 적대적 리뷰 반박: B2를 **도면맥락 게이트**(diameter/°각도, R²·±·철자deg 제외)로 강화(통계 산문 phantom 차단), title-block은 dimensions 발동 페이지에만, extractions는 structure.json 계약에서 제외. **잔여**: 없음(B4 diagram wiring 완료 — B4행 참조) |

## C. 구현 — 트랜치 3 (저비용 마감, 미착수)

| # | 사안 | 우선 |
|---|---|:--:|
| C1 | ~~FR-1 이미지 직접 입력(JPG/PNG → PDF 래핑)~~ **[완료]** — `imagewrap.image_to_pdf`(Pillow, 코어 dep)가 이미지를 1페이지 PDF로 래핑, cli 진입점(`_wrap_image_input`)에서 감지→래핑→기존 결정적/스캔 경로. 적대적 리뷰 반박: 래핑 PDF **바이트 결정성**(Pillow가 temp 파일명을 `/Title`·wall-clock을 date로 embed→고정값 pin, 안 하면 document_id 드리프트로 재처리 skip 무력화), 손상 이미지 graceful(임시파일 정리+exit 2), `original_filename` 원본 스레딩(temp명 아님), 멀티프레임 페이지 손실 경고. TIFF 멀티페이지는 1프레임만(v1) | P2 하 |
| C2 | ~~FR-4.2 표 HTML view 방출~~ **[완료]** — `_table_html(cells)`가 span 보존 `<table>` 방출(md는 span 소실), `tables/<id>.html` + `views.html`. 적대적 리뷰 반박: 헤더 rowspan이 `<thead>` 경계에서 clamp되던 것을 단일 `<tbody>`(행0=`<th>`)로 수정(다단 헤더 손상 방지, ODL 직렬화기 대조로 span-생략 규약 확증). TEDS 스코어러는 미착수(benchmarks 선택) | P2 하 |
| C3 | ~~FR-6 사용자향 confidence 표기 + 정확도차이 고지~~ **[완료]** — `_quality_summary`가 document.json 최상위 `quality` 블록 방출(structure.json 계약에서는 strip): elements/flagged_elements, 요소레벨 `flag_counts`(unsourced/unverifiable/unit_unstated), low_confidence_figures, pages_flagged, 페이지레벨 `page_flag_counts`. 적대적 리뷰 반박(HIGH): oracle의 **주경로인 페이지 전사 fabrication**(`unsourced_number`)과 완전성 갭(`odl_dropped_number`)이 pages_flagged 카운트에만 묻혀 "oracle unsourced=K"가 과소보고되던 것을 `page_flag_counts` prefix 집계로 보강. 요소별 confidence(description_flags·kind_confidence)는 기존 semantic 노드에 이미 노출 | P2 하 |
| C4 | FR-3.1 손글씨·주석·도장 라우팅(PaddleOCR 옵션 활성) | P2 중 |
| C5 | FR-3.3 양방향 검수(텍스트레이어에 있는데 VLM 누락 = recall flag) | P2 중 |
| C6 | FR-7 뷰어 통합(원본 bbox 오버레이 + 마커-캡션) | P2 중 |

## D. 골든셋 / 평가 커버리지 갭

| # | 사안 | 근거 |
|---|---|---|
| D1 | **순수 관계형 도식**(AS-IS/TO-BE 구조도) 라벨 — 현 policy 소스는 표·콜아웃 위주 | gt/README 잔존 |
| D2 | **한국어 필기** 골든 — census는 영문. AI Hub 605 필요 | gt/README 잔존 |
| D3 | score.py 강화: `A_unit`은 substring 휴리스틱, `B_arithmetic`은 form 구조 한정, `G_grounding`은 존재만(IoU 아님). **[부분]** `check_must_not`을 SCHEMA대로 caption만 스캔(structured verbatim 데이터 오탐 제거) | score.py 스캐폴드 |
| D4 | ~~실제 파이프라인 산출을 `--out`으로 채점~~ **[결정적+live 완료]** `run_bench.py` 어댑터(document.json→{caption,structured,elements}, 무날조)로 골든 10건 실채점. **결정적**(무API): G_grounding 9/10, caption_must_not 10/10, 캡션 체크는 VLM 의존. **live**(det_vlm, Paddle 전사+Gemini 캡션, 라벨 페이지만 슬라이스해 1439p→~10p): 18 fail(det 19). **캡션 실제 작동 확인** — form/statistics must_include·handwriting C_entity가 결정적 FAIL→live PASS, 캡션 고품질(영수증 sub-total, 한국어 고령자 통계 원형/막대 차트, 1900 US Census). **잔여**: (1)결정적은 whole-doc·live는 target page라 비교 비대칭(결정적도 슬라이스 필요), (2)D3 A_unit/C_entity/G_grounding IoU 정밀화 | — |
| D5 | **전면 래스터 도면 미서빙(신규 갭)**: `drawing_dim`(전면 래스터 기계도면)은 det_vlm에서도 caption='' elements=0 — figure-describe가 ODL-검출 figure **크롭**만 서술, 래스터 전면 이미지는 ODL figure/텍스트 없어 미크롭. 텍스트레이어 없는 전면 이미지 페이지를 통째 describable figure로 취급 필요(C1 이미지 입력과 접점) | run_bench live 채점 |

## E. 데이터 / 코퍼스

| # | 사안 |
|---|---|
| E1 | 한국어 dimensioned 도면(한국어 표제란) — KIPRIS 기계 특허 |
| E2 | 정확도 튜닝용 대량셋(DocLayNet·FinTabNet·SciTSR 등) — 현재 시드만, fetch 확장 |
| E3 | fetch.py 한국 공공 URL 드리프트 위험(policy seq/파일명) — 실패 시 SOURCES 수동 확인 |

## F. 인프라 / 하우스키핑

| # | 사안 | 메모 |
|---|---|---|
| F1 | ~~`test_config` 2건 실패~~ **[완료 a1aa014]** | 근본원인: `import lightrag`가 python-dotenv로 repo `.env`를 os.environ에 자동 로드 → 전체 스위트에서만 오염. autouse 픽스처로 설정 키 초기화. **전체 528 passed** |
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
