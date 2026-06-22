# 스파이크 계획: 파싱 엔진 두 트랙 비교 (ODL 튜닝 vs 외부 오케스트레이터)

> 상태: 실험 계획 (bake-off)
> 작성일: 2026-06-16
> 선행: `docs/odl-engine-rust-python-integration.md`, `docs/pdf-parsing-libraries-research.md`(부록 D)
> 결정할 것: 문서 인식 엔진을 **(A) ODL 내부에 VLM을 주입·튜닝** vs **(B) ODL을 결정론 프런트로 두고 외부 오케스트레이터가 VLM 2-패스** — 둘 중 무엇으로 갈지, 같은 테스트셋·같은 평가표로 비교해 결정한다.

---

## 1. 두 트랙 정의

### Track A — ODL 튜닝 (VLM을 ODL 안으로)
ODL의 triage·결정론 파싱·bbox·md/json을 그대로 쓰고, 빠진 **컨텍스트 인지형 VLM 2-패스**를 ODL 하이브리드 백엔드로 주입.
- ODL이 오케스트레이션 주체. triage가 복잡 페이지를 VLM 백엔드로 라우팅.
- 장점(가설): 컴팩트, triage/bbox/태깅 공짜.
- 미검증: VLM 커스텀 깊이, page-vs-region 입자 충돌, 출력 스키마 변환 비용.

### Track B — 외부 오케스트레이터 (VLM을 ODL 밖에서)
ODL을 **결정론+triage 프런트**로만 쓰고(JSON 소비), VLM 2-패스·정책·ledger·비-PDF 처리는 외부(Python) 오케스트레이터가 담당.
- 오케스트레이터가 주체. ODL은 플러그인 중 하나.
- 장점(가설): 비-PDF 커버, 멀티 백엔드, 무 Java 2-패스, ledger 자유.
- 미검증: ODL 2회 실행(triage→재처리) 오버헤드, 결합 복잡도.

---

## 2. 공유 컴포넌트 (한 번 만들어 양쪽이 사용)

평가 공정성을 위해 아래는 트랙 무관하게 동일하게 쓴다.

1. **테스트 코퍼스** (~30~50페이지, 챌린지 슬라이드 유형 반영)
   - born-digital 단순(텍스트만) — 베이스라인
   - 다단 + 한/영 혼재
   - 병합셀/중첩헤더 표 (제조 스펙)
   - 표 위 이미지 겹침
   - text-as-image 다이어그램 (OCR 금지 케이스)
   - 수기·회전 글자
   - 스캔 PDF
   - HWP, xlsx, png (비-PDF 커버리지 — B에서만 의미)
2. **평가 스코어카드** (§6) — 동일 루브릭.
3. **VLM 2-패스 모듈** — `(1차 md + 페이지 이미지 + 유저 의도 프롬프트) → 2차 md/json`. **로직은 공유**, 호출 위치만 트랙별로 다름.
4. **출력 IR 계약** — md + json(요소 타입·bbox·표HTML·confidence). 양 트랙 출력이 비교 가능하도록. (LightRAG `BaseExternalParser` RFC IR과 정렬.)
5. **골든셋** — 페이지별 정답(읽기순서, 표 구조, 그림 설명 기대치, 핵심 필드 값).

---

## 3. Track A 작업 단계

- **A1. 무 Java 주입 검증 (최우선·최저비용)**
  더미 어댑터 서버가 `POST /v1/convert/file` → DoclingDocument-JSON 반환. `--hybrid=docling-fast --hybrid-url=<더미>`로 ODL 실행 → **triage가 복잡 페이지만 더미로 보내는지** 로그로 확인. (ODL VLM 커스텀 가능성 자체를 판정)
- **A2. 실 VLM 2-패스 어댑터**
  더미를 실제 VLM(PaddleOCR-VL / Qwen-VL)로 교체. 어댑터가 페이지 이미지+프롬프트로 2-패스 후 DoclingDocument-JSON으로 성형.
- **A3. (조건부) 경량 Java 백엔드**
  docling-fast 프로토콜로 부족하면 `HybridClient`+`SchemaTransformer`(→veraPDF IObject) 작성·등록. **IObject 변환 비용을 여기서 측정.**
- **A 측정 포인트**: triage 입자(page vs region) 적합성, 프롬프트 주입 가능성, DoclingDocument/IObject 성형 공수, Java 발자국, 출력 품질.

## 4. Track B 작업 단계

- **B1. ODL JSON 소비**
  ODL 로컬 실행 → `_content.json`(요소·bbox·triage 결정 per page) 파싱 → serde/pydantic 타입.
- **B2. 오케스트레이터 2-패스 + ledger**
  triage 결정 읽고, 복잡 페이지만 **공유 VLM 2-패스** 호출 → 병합 → md/json 정규화 → **결정·비용 ledger** 기록.
- **B3. 비-PDF 경로**
  xlsx/png/HWP/Slack 샘플을 다른 플러그인(Docling/Paddle/자체)으로 라우팅 — **ODL-내부가 못 하는 부분**을 B가 커버하는지 확인.
- **B 측정 포인트**: 비-PDF 커버리지, 멀티 백엔드 라우팅, ledger 풍부도, ODL 2회 처리 오버헤드(지연/비용), 코드 복잡도, 무 Java 여부.

---

## 5. 공통 사항
- 동일 VLM·동일 프롬프트·동일 임베딩 설정으로 고정(변수 통제).
- 모든 실행에 **per-page 비용/지연/경로결정 로깅**(A는 ODL TriageLogger+어댑터 로그, B는 ledger).
- 출력은 IR 계약(§2-4)으로 통일해 diff.

---

## 6. 평가 스코어카드 (양 트랙 공통)

| 범주 | 지표 | 측정법 |
|---|---|---|
| 인식 품질 | 읽기순서 정확도 | 골든셋 대비 NID |
| | 표 충실도(병합셀/중첩헤더) | TEDS / 수동 채점 |
| | 그림/다이어그램 서술 품질 | 수동 1~5 + 쿼리 재현 |
| | text-as-image 처리(OCR 오염 없음) | 수동 |
| triage | 라우팅 정확도(복잡 페이지만 VLM) | 혼동행렬 |
| | 비용 절감(VLM 스킵 비율) | % pages skipped |
| 커스텀 | 유저 의도 프롬프트 반영 | 데모 가능/불가 |
| | VLM 교체 용이성 | 교체 공수 |
| provenance | bbox 보존(엔드투엔드) | 존재율 % |
| 출력 | md/json 정확성 | 스키마 검증 |
| 운영 | per-page 비용/$·지연 | ledger 집계 |
| | ledger 완전성(결정·비용) | 필드 충족 |
| 커버리지 | 비-PDF 입력 처리 | 성공/실패 |
| 엔지니어링 | Java 발자국 | LOC/런타임 |
| | 개발·유지보수 공수 | 정성 |

---

## 7. 결정 게이트

| 조건 | 선택 |
|---|---|
| PDF/HWP 비중 압도 + Java 허용 + A의 컴팩트함이 품질/비용 우위 | **Track A** (ODL 내부 VLM) |
| 비-PDF 비중 큼 OR 무 Java OR 멀티백엔드/ledger 자유 필요 | **Track B** (외부 오케스트레이터) |
| PDF는 A가, 비-PDF는 B가 우위 (현실 예상) | **하이브리드**: PDF/HWP는 ODL+무Java VLM 주입(A1/A2), 그 외는 B 오케스트레이터. 공유 IR로 통합 |

> 핵심 판별 질문: (1) ODL triage 입자가 페이지 2-패스와 맞는가? (2) DoclingDocument/IObject 성형 비용이 감당 가능한가? (3) ODL 2회 처리 오버헤드 vs 단일 패스 컴팩트함, 어느 쪽이 큰가? (4) 비-PDF 비중이 ODL-only를 무력화하는가?

---

## 8. 일정 (제안)

| 주차 | 작업 |
|---|---|
| W1 | 공유: 코퍼스 큐레이션 + 골든셋 + 스코어카드 + VLM 2-패스 모듈 + IR 계약 |
| W2 | Track A: A1(무Java 검증) → A2(실 VLM). 병렬로 Track B: B1→B2 |
| W3 | B3(비-PDF) + A3(조건부 Java) + 스코어카드 채점 + 결정 게이트 적용 |

---

## 9. 리스크
- **A**: ODL triage가 region 단위라 page-2패스와 충돌 → `hybrid_mode=full` 또는 triage-판정만 사용으로 회피. DoclingDocument/IObject 성형이 예상보다 큼.
- **B**: ODL을 triage용으로 한 번 + 재처리로 두 번 도는 오버헤드. ODL JSON에 2-패스 그라운딩에 필요한 1차 md/이미지 접근이 충분한지 확인 필요.
- **공통**: VLM 비용이 코퍼스 규모에서 폭발 → triage 스킵률이 ROI를 좌우(스코어카드에 포함).

## 10. 예상 수렴 (정직한 가설)
PDF/HWP 슬라이스에선 A(특히 A1 무Java 주입)가 컴팩트하게 이기고, 비-PDF·ledger·멀티백엔드에선 B가 필요 → **하이브리드로 수렴할 가능성이 높음**. 그래도 bake-off로 "PDF 2-패스를 ODL 안/밖 어디서 돌릴지"를 데이터로 확정하는 게 목적.

## 11. 참고
- ODL 내부(triage/하이브리드/백엔드): `docs/pdf-parsing-libraries-research.md` 부록 D
- 연동 옵션/무Java 주입: `docs/odl-engine-rust-python-integration.md`
- LightRAG `BaseExternalParser` RFC (IR 계약 정렬 대상): https://github.com/HKUDS/LightRAG/issues/3197
