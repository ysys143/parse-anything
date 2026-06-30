# 스파이크 계획: 파싱 엔진 세 트랙 비교 (외부 오케스트레이터 vs ODL 하이브리드 활용 vs ODL Java 수정)

> **재정향(superseded) — 역사적 참고.** Track A/B/C 비교와 자동 라우팅 전제는 이후 실측(`measurement-findings.md` F16/F17)으로 **소스 단위 diagnose-then-configure** 아키텍처로 대체됨(`processing-tiers-and-adaptation.md` §2.5–2.6/P7). 외부 오케스트레이터 코드는 제거됨.

> 상태: 실험 계획 (bake-off)
> 작성일: 2026-06-16
> 선행: `docs/odl-engine-rust-python-integration.md`, `docs/pdf-parsing-libraries-research.md`(부록 D)
> 결정할 것: 문서 인식 엔진을 **(A) ODL을 결정론 프런트로 두고 외부 오케스트레이터가 VLM 2-패스** vs **(B) ODL 내부에 VLM을 하이브리드 백엔드로 주입** vs **(C) ODL Java를 직접 수정해 프로토콜을 확장** — 셋 중 무엇으로 갈지, 같은 테스트셋·같은 평가표로 비교해 결정한다.

---

## 1. 세 트랙 정의

### Track A — 외부 오케스트레이터 (VLM을 ODL 밖에서)
ODL을 **결정론+triage 프런트**로만 쓰고(JSON 소비), VLM 2-패스·정책·ledger·비-PDF 처리는 외부(Python) 오케스트레이터가 담당.
- 오케스트레이터가 주체. ODL은 플러그인 중 하나.
- 장점(가설): 비-PDF 커버, 멀티 백엔드, 무 Java 2-패스, ledger 자유.
- 미검증: ODL 2회 실행(triage→재처리) 오버헤드, 결합 복잡도.

### Track B — ODL 하이브리드 활용 (VLM을 ODL 안으로)
ODL의 triage·결정론 파싱·bbox·md/json을 그대로 쓰고, 빠진 **컨텍스트 인지형 VLM 2-패스**를 ODL 하이브리드 백엔드로 주입.
- ODL이 오케스트레이션 주체. triage가 복잡 페이지를 VLM 백엔드로 라우팅.
- 장점(가설): 컴팩트, triage/bbox/태깅 공짜.
- 미검증: VLM 커스텀 깊이, page-vs-region 입자 충돌, 출력 스키마 변환 비용.

### Track C — ODL Java 수정 (프로토콜 직접 확장)
ODL Java 소스를 직접 수정해 HybridRequest 프로토콜을 확장. 1차 md/json 전달과 동적 프롬프트를 Java 레벨에서 해결.
- ODL이 오케스트레이션 주체. 프로토콜 제약을 Java 수정으로 극복.
- 장점(가설): B의 컴팩트함 + grounded 2-패스 + 동적 프롬프트 지원.
- 미검증: ODL 업스트림 추적 부담, Java 발자국, IObject 변환 비용.

---

## 2. 공유 컴포넌트 (한 번 만들어 세 트랙이 사용)

평가 공정성을 위해 아래는 트랙 무관하게 동일하게 쓴다.

1. **테스트 코퍼스** (~30~50페이지, 챌린지 슬라이드 유형 반영)
   - born-digital 단순(텍스트만) — 베이스라인
   - 다단 + 한/영 혼재
   - 병합셀/중첩헤더 표 (제조 스펙)
   - 페이지에 걸친 표
   - 표 위 이미지 겹침
   - text-as-image 다이어그램 (OCR 금지 케이스)
   - 산술 불변식이 있는 invoice/spec table
   - 수기·회전 글자
   - 스캔 PDF
   - HWP, xlsx, png (비-PDF 커버리지 — A에서만 의미)
2. **평가 스코어카드** (§7) — 동일 루브릭.
3. **Processing-depth router** — 기본은 결정론 처리. scan/text-layer 부재, 그림·차트, 인코딩 깨짐, 산술 불변식 실패, 결정론 불완전, 방향 불확실 같은 명시 트리거가 있을 때만 VLM/OCR로 escalation.
4. **VLM 2-패스 모듈** — `(결정론 md/json + 페이지 이미지 또는 multi-image + 방향보정 + 유저 의도 프롬프트 + guard policy) → 2차 md/json/table/image_desc/guard_flags`. **로직은 공유**, 호출 위치만 트랙별로 다름.
5. **출력 IR 계약** — page md/json + document md/json + logical tables + asset pointers + bbox/provenance/confidence/guard flags. 세 트랙 출력이 비교 가능하도록. (LightRAG `BaseExternalParser` RFC IR과 정렬.)
6. **페이지 걸친 표 assembler** — bbox 열 좌표, column signature, header/caption continuation 신호로 logical table을 병합. 3쪽 이상 표는 overlap chunk로 처리.
7. **숫자 guard** — born-digital은 텍스트 레이어 값을 oracle로 주입하고, source gate와 산술 불변식으로 hallucination을 차단/flag.
8. **Processing tier / domain adaptation** — DET/VLM/HUM 경계, 잔여 사람검토량, 도메인 적응 전후 오류율·비용 변화를 측정한다.
9. **골든셋** — 페이지별 정답뿐 아니라 문서 레벨 continuation, 표 병합, 숫자 정확성, guard flag 기대치를 포함.

---

## 3. Track B 작업 단계

- **B1. 무 Java 주입 검증 (최우선·최저비용)**
  더미 어댑터 서버가 `POST /v1/convert/file` → DoclingDocument-JSON 반환. `--hybrid=docling-fast --hybrid-url=<더미>`로 ODL 실행 → **triage가 복잡 페이지만 더미로 보내는지** 로그로 확인. (ODL VLM 커스텀 가능성 자체를 판정)
- **B2. 실 VLM 2-패스 어댑터**
  더미를 실제 VLM(PaddleOCR-VL / Qwen-VL)로 교체. 어댑터가 페이지 이미지+프롬프트로 2-패스 후 DoclingDocument-JSON으로 성형.
- **B3. (조건부) 경량 Java 백엔드**
  docling-fast 프로토콜로 부족하면 `HybridClient`+`SchemaTransformer`(→veraPDF IObject) 작성·등록. **IObject 변환 비용을 여기서 측정.**
- **B 측정 포인트**: triage 입자(page vs region) 적합성, 프롬프트 주입 가능성, DoclingDocument/IObject 성형 공수, Java 발자국, 출력 품질.

> 위 단계는 방법론이고, 실제 구현은 4개 변종(B-1~B-4)으로 분기해 전부 동작 검증됐다 — **§12 Track B 변종 실측** 참조.

## 4. Track A 작업 단계

- **A1. ODL JSON 소비**
  ODL 로컬 실행 → `_content.json`(요소·bbox·triage 결정 per page) 파싱 → serde/pydantic 타입.
- **A2. 오케스트레이터 2-패스 + ledger**
  triage 결정 읽고, 복잡 페이지만 **공유 VLM 2-패스** 호출 → 병합 → md/json 정규화 → **결정·비용 ledger** 기록.
- **A3. 비-PDF 경로**
  xlsx/png/HWP/Slack 샘플을 다른 플러그인(Docling/Paddle/자체)으로 라우팅 — **ODL-내부가 못 하는 부분**을 A가 커버하는지 확인.
- **A 측정 포인트**: 비-PDF 커버리지, 멀티 백엔드 라우팅, ledger 풍부도, ODL 2회 처리 오버헤드(지연/비용), 코드 복잡도, 무 Java 여부.

---

## 5. Track C 작업 단계

- **C1. HybridRequest 프로토콜 확장**
  ODL Java 소스에서 `HybridRequest`에 1차 md/json 전달 필드와 `prompt` 필드를 추가. 빌드 후 기존 B1 더미 어댑터와 동작 비교 — **grounded 2-패스가 프로토콜 레벨에서 가능한지** 확인.
- **C2. SchemaTransformer 직접 구현**
  백엔드 응답을 `veraPDF IObject`로 변환하는 Java 클래스를 작성·등록. B3의 추측 기반 구현과 달리 HybridRequest 확장 필드를 직접 소비. **IObject 변환 비용과 정밀도를 B3와 비교.**
- **C3. (조건부) triage 로그 노출**
  ODL 로컬 모드 JSON에 triage 결정을 포함하도록 수정 — A가 pdf-inspector 없이도 triage 신호를 확보할 수 있는지 검증.
- **C 측정 포인트**: Java 발자국(LOC/런타임), 업스트림 ODL 버전 추적 부담, HybridRequest 확장 공수, 동적 프롬프트·grounded 2-패스 품질(B2/B3 대비).

---

## 6. 공통 사항
- 동일 VLM·동일 프롬프트·동일 임베딩 설정으로 고정(변수 통제).
- 모든 실행에 **per-page 비용/지연/경로결정 로깅**(B는 ODL TriageLogger+어댑터 로그, A는 ledger, C는 Java 로그+어댑터).
- 출력은 IR 계약(§2-4)으로 통일해 diff.

---

## 7. 평가 스코어카드 (세 트랙 공통)

| 범주 | 지표 | 측정법 |
|---|---|---|
| 인식 품질 | 읽기순서 정확도 | 골든셋 대비 NID |
| | 페이지 방향/다단 보정 | orientation/skew + column order 정답률 |
| | 표 충실도(병합셀/중첩헤더) | TEDS / 수동 채점 |
| | 페이지 걸친 표 재구성 | logical table id + continuation 병합 정확도 |
| | 그림/다이어그램 서술 품질 | 수동 1~5 + 쿼리 재현 |
| | text-as-image 처리(OCR 오염 없음) | 수동 |
| 숫자 안전 | 숫자 정확도 | source text oracle 대비 cell value 정확도 |
| | hallucination rate | source에 없는 숫자 생성률 |
| | source gate 오거부 | source에 있는 숫자를 잘못 flag한 비율 |
| | 산술 불변식 | 소계/세금/수량×단가 pass rate |
| triage | 라우팅 정확도(복잡 페이지만 VLM) | 혼동행렬 |
| | processing depth 정확도 | 결정론/VLM/OCR/human-review route 정답률 |
| | 비용 절감(VLM 스킵 비율) | % pages skipped |
| 사람검토 | 검토량 | flag된 셀/표/페이지 수 |
| | 검토 정밀도 | flag된 항목 중 실제 오류 비율 |
| 적응 | 도메인 보정 효과 | 보정 전후 오류율·비용·검토량 delta |
| 커스텀 | 유저 의도 프롬프트 반영 | 데모 가능/불가 |
| | VLM 교체 용이성 | 교체 공수 |
| provenance | bbox 보존(엔드투엔드) | 존재율 % |
| 출력 | md/json 정확성 | 스키마 검증 |
| | 합본 산출 | document.md/document.json + page pointers 존재 |
| 운영 | per-page 비용/$·지연 | ledger 집계 |
| | ledger 완전성(결정·비용·guard) | 필드 충족 |
| 커버리지 | 비-PDF 입력 처리 | 성공/실패 |
| 엔지니어링 | Java 발자국 | LOC/런타임 |
| | 개발·유지보수 공수 | 정성 |

---

## 8. 결정 게이트

| 조건 | 선택 |
|---|---|
| 비-PDF 비중 큼 OR 무 Java OR 멀티백엔드/ledger 자유 필요 | **Track A** (외부 오케스트레이터) |
| PDF/HWP 비중 압도 + Java 불필요 + B의 컴팩트함이 품질/비용 우위 | **Track B** (ODL 하이브리드 활용) |
| Java 수정 허용 + grounded 2-패스·동적 프롬프트가 필수 + 업스트림 추적 감당 가능 | **Track C** (ODL Java 수정) |
| PDF는 B가, 비-PDF는 A가 우위 (현실 예상) | **하이브리드**: PDF/HWP는 ODL+무Java VLM 주입(B1/B2), 그 외는 A 오케스트레이터. 공유 IR로 통합 |

> 핵심 판별 질문: (1) ODL triage 입자가 페이지 2-패스와 맞는가? (2) DoclingDocument/IObject 성형 비용이 감당 가능한가? (3) ODL 2회 처리 오버헤드 vs 단일 패스 컴팩트함, 어느 쪽이 큰가? (4) 비-PDF 비중이 ODL-only를 무력화하는가? (5) Java 수정 허용 여부와 업스트림 추적 비용이 C의 이득을 정당화하는가?

---

## 9. 일정 (제안)

| 주차 | 작업 |
|---|---|
| W1 | 공유: 코퍼스 큐레이션 + 골든셋 + 스코어카드 + VLM 2-패스 모듈 + IR 계약 |
| W2 | Track B: B1(무Java 검증) → B2(실 VLM). 병렬로 Track A: A1→A2 |
| W3 | A3(비-PDF) + B3(조건부 Java) + C1-C3(Track C) + 스코어카드 채점 + 결정 게이트 적용 |

---

## 10. 리스크
- **B**: ODL triage가 region 단위라 page-2패스와 충돌 → `hybrid_mode=full` 또는 triage-판정만 사용으로 회피. DoclingDocument/IObject 성형이 예상보다 큼.
- **A**: ODL을 triage용으로 한 번 + 재처리로 두 번 도는 오버헤드. ODL JSON에 2-패스 그라운딩에 필요한 1차 md/이미지 접근이 충분한지 확인 필요.
- **C**: ODL Java 수정 후 업스트림 버전 업그레이드 시 재작업 필요. HybridRequest 확장이 ODL 내부 설계와 충돌할 수 있음.
- **공통**: VLM 비용이 코퍼스 규모에서 폭발 → processing-depth 스킵률이 ROI를 좌우(스코어카드에 포함).
- **공통**: 스캔 문서는 born-digital 숫자 oracle이 없으므로 완전 자동 숫자 신뢰를 약속할 수 없다. 잔여 위험 셀은 guard flag와 사람 검토 대상으로 남긴다.
- **공통**: PaddleOCR official API처럼 이미지 URL fetch만 가능한 provider는 민감 문서에 공개 호스팅을 강제할 수 있으므로, privacy route 제약을 bake-off에 포함해야 한다.

## 11. 예상 수렴 (정직한 가설)
PDF/HWP 슬라이스에선 B(특히 B1 무Java 주입)가 컴팩트하게 이기고, 비-PDF·ledger·멀티백엔드에선 A가 필요. Java 수정이 허용되고 grounded 2-패스와 동적 프롬프트가 필수라면 C가 B의 프로토콜 한계를 해소 → **하이브리드로 수렴할 가능성이 높음**. 그래도 bake-off로 "PDF 2-패스를 ODL 안/밖/Java 수정 중 어디서 돌릴지"를 데이터로 확정하는 게 목적.

## 12. Track B 변종 실측 (track-b 브랜치 구현)

§3의 B1/B2/B3는 방법론적 *단계*(무Java검증 → 실VLM → 조건부Java)다. 실제 구현은 "VLM을 어디서/어떤 입력으로 부르나"에 따라 **4개 변종**으로 분기했고, 전부 **ODL 업스트림 무수정**(Java fork 0)으로 동작 검증됐다. 코드: `src/odl_vl_track_b/` (커밋 86b8262 / 9e5ad09 / 1ded424 / 3221486).

| 변종 | upstream | VLM 범위 | grounding | 구현 |
|---|---|---|---|---|
| **B-1** | 무수정 (공식 서버 monkeypatch) | 페이지 전체 전사 | Docling 자체 | `backend_docling.py`: Docling `VlmPipeline` + `ApiVlmOptions` → Gemini OpenAI 호환 엔드포인트 |
| **B-2** | 무수정 (공식 서버 monkeypatch) | 그림 설명만 | 없음 | `backend_docling.py`: 표준 `PdfPipelineOptions`(layout+TableFormer) + `PictureDescriptionApiOptions`(Gemini) |
| **B-3** | 무수정 (독립 proxy) | 페이지 전체 전사 | 없음(순수 VLM) | `proxy.py`: stdlib `http.server`, 수동 multipart, 신규 의존성 0 |
| **B-4** | 무수정 (독립 proxy) | 페이지 전체 전사 | **det aug 풀세트** | `proxy.py` + `det_aug.py`: pypdfium2 값 + ODL 구조 grounding pre-hook, 값-oracle guard post-hook (기존 `pipeline/grounding·oracle·guards` 재사용) |

### 핵심 발견

- **공식 `hybrid_server.py`는 포크 불필요**: ODL 하이브리드 프로토콜(multipart in / DoclingDocument out)을 이미 말하고, VLM 구성이 모듈 전역 `create_converter` 한 곳에 모여 있어 **monkeypatch로 VLM만 교체**(1000줄 포크 회피). → B-1/B-2.
- **proxy면 Java 없이 동적 프롬프트 가능**: ODL은 프롬프트를 운반 못 하지만(원래 Track C 명분), proxy가 ODL과 VLM *사이*에서 프롬프트를 직접 주입 → C의 프롬프트 가치를 흡수. C에 남는 순수 가치는 "ODL 1차 결과 재사용(재파싱 중복 제거) + IObject 직매핑"으로 좁혀짐.
- **표 보존은 출력 성형에 달림**: ODL `DoclingSchemaTransformer`는 `data.grid`(차원, 필수) + `data.table_cells`(셀 텍스트)를 읽는다(`DoclingSchemaTransformer.java` L439/L464). proxy가 VLM Markdown을 파싱해 이 형식으로 emit하면 B-3/B-4도 표·heading 구조를 보존(초기 평탄화 → 구조화, 커밋 3221486).
- **모델 버전 드리프트 주의**: `gemini-2.0-flash`는 폐기(404)되어 live에서 적발 → `providers.DEFAULT_GEMINI_MODEL`로 레포 전체와 모델 id를 묶음.
- **B 의존성 경계**: B-1/B-2는 `docling`+`fastapi`/`uvicorn`/`python-multipart`(`[hybrid]` extra) 필요. B-3/B-4는 신규 의존성 0(stdlib + 기존 `odl_vl.pipeline`).

### 동일 입력 출력 특성 (1p born-digital, 비테두리 표)

| 변종 | heading | 표 | 값 guard |
|---|---|---|---|
| B-1 | 평문 | **Markdown 표 보존** | 없음 |
| B-2 | `#` 인식 | 평탄화(비테두리 표는 TableFormer 미검출) | 없음 |
| B-3 | `#` 인식 | **표 보존**(성형 개선 후) | 없음 |
| B-4 | `#` 인식 | **표 보존** | `unsourced_number` flag |

> "어느 변종이 이긴다"가 아니라 "무엇에 강하냐"가 다르다. 도메인별 정량 비교(§7 스코어카드)와 재파싱 중복 비용(§5 C 정당화) 측정이 다음 단계.

### 스코어카드 실측 (oracle/golden 기반, `scripts/track_b_scorecard.py`)

라벨 골든셋이 없어 **born-digital은 pypdfium2 텍스트 레이어를 값 oracle**(F8)로, **스캔은 원본 숫자 골든셋**(`--golden`)으로 채점. 지표: number recall(누락), precision(환각/OCR 오류), 표 보존. 동일 콘텐츠(16행×7열 밀집 표, 93개 숫자, 병합 헤더, 6pt)를 born-digital과 스캔(텍스트 레이어 제거)으로 비교:

| 변종 | born-digital recall | 스캔 recall | 스캔 precision | 스캔 표 |
|---|---|---|---|---|
| A (det_vlm) | 0.989 | 0.989 | 0.989 | O |
| B-1 (VlmPipeline) | 0.989 | 0.989 | 0.989 | O |
| B-2 (picture-desc) | 0.989 | **0.0** | — | **X** |
| B-3 (gemini) | 0.989 | 0.989 | 0.989 | O |
| B-3 (paddle) | 0.989 | 0.989 | 0.989 | O |

**발견 (spike-plan 핵심 질문에 데이터 답)**:
- **born-digital은 변종 무관**: 텍스트 레이어가 정답이라 5변종 전부 동률(0.989). "VLM을 어디서 부르나"가 무의미 — 결정론만으로 충분하다는 가설(measurement-findings) 재확인.
- **스캔이 변별점**: 텍스트 레이어가 없으면 "VLM이 페이지 전체를 전사하나"가 결정적. A/B-1/B-3(전체 전사)는 0.989 강건, **B-2(그림 설명만)는 0.0 붕괴** — OCR 소스가 없고 picture-description VLM은 텍스트를 전사하지 않음(이 환경 OCR 엔진 PP-OCRv6 고장으로 B-2 OCR 경로 측정 불가; 단 구조적으로 그림설명만으론 스캔 텍스트를 못 뽑음).
- **VLM 변종 간(A/B-1/B-3)은 아직 동률**: 깨끗한 렌더 스캔에선 Gemini/Paddle 모두 정확. 더 깊은 변별은 저해상도·노이즈·회전 스캔(VLM OCR 품질차) 또는 셀 위치 정확도(TEDS, 골든 라벨 필요)에서 날 것.
- number recall의 한계: VLM이 `1,234`↔`1,243`을 *틀린 셀*에 넣어도 둘 다 골든에 있어 recall은 안 떨어진다 → 셀 단위 정확도는 별도 지표(TEDS) 필요.

#### 현실적 스캔 (mild) — provider 품질이 변별점 (살짝 흐림+0.8° skew+약노이즈+JPEG q65, 사람 판독 가능)

| 변종 | recall | precision | fabricated |
|---|---|---|---|
| A (det_vlm) | 0.989 | 0.989 | 1 |
| B-1 (VlmPipeline) | 0.989 | 0.989 | 1 |
| B-3 (gemini) | 0.989 | 0.989 | 1 |
| B-3 (paddle), 전처리 OFF | 0.946 | 0.926 | 7 |
| B-3 (paddle), 전처리 ON | **0.968** | **0.978** | **2** |

**발견**: 사람이 읽히는 현실적 스캔에서 **VLM provider가 갈린다 — 단 공정 비교가 전제**. 첫 측정에서 Paddle이 0.946으로 처져 보였으나, 이는 `paddle_vlm`이 `useDocUnwarping`/`useDocOrientationClassify`를 **꺼둔 측정 아티팩트**였다(born-digital 가정 R8.5). 스캔용 전처리를 켜면(`--paddle-preprocess`) **0.968/0.978로 Gemini(0.989)에 근접**하고 콤마-소수점 오독·근접 숫자 혼동이 대부분 사라진다(fabricated 7→2). 교훈: provider 비교는 각자 최적 설정으로 해야 공정하다. **단 전처리는 만병통치가 아니다** — 아래 dirty 스캔에선 노이즈가 orientation/unwarp을 망가뜨려 ON이 오히려 역효과(0.011→0.0). 최적 설정 자체가 입력 품질에 의존한다.

#### 저품질 스캔 — 환각 안전성이 변별점 (저해상도+skew+노이즈+블러+JPEG q32, 사람도 판독 곤란)

동일 콘텐츠를 심하게 열화시킨 스캔(텍스트 레이어 0)으로 4 VLM 변종 비교:

| 변종 | recall | precision | fabricated | 동작 |
|---|---|---|---|---|
| A (det_vlm) | 0.011 | **1.0** | 0 | abstain — `![figure]`만, 전사 포기 |
| B-1 (VlmPipeline) | 0.097 | 0.29 | 22 | 그럴듯한 표 환각 |
| B-3 (gemini) | 0.097 | 0.22 | 32 | 원본과 무관한 표 통째 환각 |
| B-3 (paddle) | 0.011 | 0.5 | 1 | 노이즈를 거대 숫자로 폭주(4171자 쓰레기) |

**발견**:
- **모든 변종이 붕괴**(recall ≤ 0.097): 저품질 스캔은 자동 처리의 한계 영역.
- **환각 안전성이 갈린다**: A(det_vlm)는 스캔-품질 게이트로 **abstain**(precision 1.0, 환각 0) — 안전하지만 거의 무용. 순수 VLM(B-1/B-3)은 항상 전사를 시도해 **그럴듯한 환각을 다발 생성**(precision 0.22~0.29, fabricated 22~32) — 신뢰 불가. Paddle은 노이즈에 폭주.
- **det aug guard의 사각**: B-4의 값-oracle guard는 born-digital 텍스트 레이어에 의존하는데 스캔엔 레이어가 없어 **스캔 환각은 guard로 못 막는다**. det_vlm의 우위는 guard가 아니라 "스캔이면 보수적으로 abstain"하는 프롬프트/품질-게이트 전략에서 온다.
- **정책 결론**: 저품질 스캔 → **사람 검토(T-HUM) 필수**(processing-tiers 경계를 데이터로 입증). precision/fabricated가 이 영역의 핵심 변별 지표 — recall만으론 "안전한 무응답(A)"과 "위험한 환각(B)"을 구분 못 한다.

#### 광폭 표 (18열 이미지-only) + Paddle 측정 공정성 — F22 재현 시도

F22(OmniDocBench, 표 TEDS)는 "이미지에선 PaddleOCR-VL ≫ Gemini, 광폭 표는 Paddle 완전·Gemini 포기"라 결론냈다. 이를 우리 환경에서 재현하려 18열 매트릭스(371 숫자)를 이미지-only로 만들어 측정한 결과, **Paddle을 불리하게 잡는 측정 결함 3종을 연달아 발견**했다:

1. **Paddle 전처리 OFF**: `useDocUnwarping`/`useDocOrientationClassify`를 꺼서 스캔에서 불리(`--paddle-preprocess`로 교정).
2. **recall이 TEDS를 못 잼**: number_recall은 숫자가 *어디든* 등장하면 hit — 표 구조/셀 위치/완전성을 못 본다(F22가 측정한 축).
3. **천단위 구분자 미정규화**: Paddle은 천단위를 점(`5.405`)으로 표기하는데 스코어카드가 콤마만 제거해 소수로 오인 → **Paddle의 완벽한 광폭 표 전사를 recall 0.127로 오채점**. 정규화 수정 후 **1.0**.

4. **골든셋 불완전**: 자작 golden_wide.txt가 데이터 값만 담고 SKU 식별자·제목 숫자를 빠뜨려, VLM이 정확히 읽은 `SKU-1000`의 `1000`을 환각으로 오카운트 → precision이 0.937에 가짜로 묶임. **born-digital 원본 텍스트 레이어를 완전 oracle**로 쓰면(자작 골든 대신) precision 1.0, fabricated 0.

**교정 후 결과(광폭 이미지 표, 완전 oracle)**: A / B-1 / B-3(gemini) / B-3(paddle) 모두 **recall 1.0, precision 1.0, fabricated 0, tbl_cells 414** — 4변종 전부 완벽 전사. number-recall/precision 축에선 Paddle = Gemini, **값 정확도로는 광폭 표에서 우열을 못 가린다.** F22의 Paddle 우위는 **표 TEDS(셀 구조 정확도)** 척도에서 나오며, 우리 oracle 카드는 `tbl_cells`(완전성=양)까지만 — **셀 구조 정확도(TEDS)는 여전히 미측정**(골든 표 구조 라벨 + apted 필요, §8).

> **교훈(중요)**: 합성 PDF + 단일 지표로 provider 우열을 단정하지 말 것. Paddle을 네 번 연속 과소평가한 건 전부 우리 측정 쪽 결함이었다. provider 비교는 ① 각자 최적 설정 ② 형식차(천단위 점/콤마, HTML/MD 표) 정규화 ③ 적합한 지표(값=recall/precision, 구조=TEDS) ④ 완전한 골든이 전제되어야 한다. 신뢰할 결론은 실제 코퍼스(OmniDocBench 류) + TEDS에서 온다(F22).

#### 실측: Track B 변종 × OmniDocBench TEDS (`scripts/track_b_teds.py`)

위 교훈대로 실제 GT로 채점했다. OmniDocBench 로컬 가용분(표 포함 2쪽/7표, 소표본)을 각 변종으로 ODL hybrid 왕복 → apted 표 TEDS + 텍스트 1-NED:

| 변종 | 표 TEDS | 텍스트 1-NED |
|---|---|---|
| B-1 (VlmPipeline, gemini) | 0.789 | 0.634 |
| B-3 (proxy, gemini) | 0.582 | 0.309 |
| B-3 (proxy, paddle) | **0.766** | 0.636 |
| *F22 참고 (직접 VLM): paddle* | *0.910* | *0.873* |
| *F22 참고 (직접 VLM): gemini* | *0.696* | *0.842* |

**발견**:
- **실제 GT TEDS에서 Paddle(0.766) > proxy Gemini(0.582)** — F22의 Paddle 표 우위가 우리 환경에서도 재현. **number_recall(합성)으론 둘 다 1.0이라 안 보이던 차이를 TEDS가 잡는다.** 적합 지표의 결정적 중요성.
- 표본에 중국어 교과서가 포함 — Paddle의 문서특화/다국어 OCR 강점이 발휘되는 곳(F22의 "이미지에선 PaddleOCR-VL ≫ Gemini" 일관).
- **proxy 성형 손실**: 같은 Gemini인데 B-1(docling VlmPipeline) 0.789 > B-3(우리 proxy) 0.582 — 우리 `docling_out` 표/텍스트 성형이 docling 본가보다 더 잃는다(개선 여지).
- **한계**: n=2쪽(로컬 OmniDocBench 이미지 28장 중 표 포함 2장)이라 통계적으로 약함 — 전체 1651쪽 이미지 확보 후 재측정 필요. 단 방향은 F22(층화 ~40쪽)와 일치.

## 13. 참고
- ODL 내부(triage/하이브리드/백엔드): `docs/pdf-parsing-libraries-research.md` 부록 D
- 연동 옵션/무Java 주입: `docs/odl-engine-rust-python-integration.md`
- LightRAG `BaseExternalParser` RFC (IR 계약 정렬 대상): https://github.com/HKUDS/LightRAG/issues/3197
