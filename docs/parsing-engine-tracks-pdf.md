# PDF 집중: Track A(ODL 내부 VLM) / Track B(외부 오케스트레이터) 구체 설계

> **재정향(superseded) — 역사적 참고.** Track A/B 설계와 자동 라우팅 전제는 이후 실측(`measurement-findings.md` F16/F17)으로 **소스 단위 diagnose-then-configure** 아키텍처로 대체됨(`processing-tiers-and-adaptation.md` §2.5–2.6/P7). 외부 오케스트레이터 코드는 제거됨.

> 상태: 구체 설계 (PDF 전용, 비-PDF는 후순위)
> 작성일: 2026-06-16
> 선행: `docs/parsing-engine-spike-plan.md`, `docs/pdf-parsing-libraries-research.md` 부록 D
> 범위: 입력은 PDF만. 두 방향을 코드로 확인된 사실 위에 구체화한다.

---

## 0. 코드로 확인된 사실 (설계 전제 — 추측 아님)

JAR 디컴파일 + 로컬 실행으로 확인:

1. **ODL → 하이브리드 백엔드 요청** = `HybridRequest{ pdfBytes, pageNumbers, outputFormats }`.
   - multipart로 `files=document.pdf`(**원본 PDF 전체**) + `page_ranges`(triage가 고른 페이지) 를 `POST /v1/convert/file` 로 보내고, 응답의 `document`(DoclingDocument JSON)를 기대.
   - **함의 (중요):** 백엔드는 **원본 PDF + 처리할 페이지 번호**만 받는다. **ODL의 1차 결정론 마크다운은 백엔드로 안 넘어간다.** **요청에 프롬프트 필드가 없다.**
2. **ODL 로컬 모드 JSON에는 triage 결정이 노출되지 않는다** (`slice.json`에 triage/decision/backend 흔적 0). triage는 **하이브리드 모드에서만** 동작하고 내부 라우팅에만 쓰인다.

이 두 사실이 A/B의 능력 경계를 결정한다.

---

## 1. 공유 컴포넌트 (PDF 한정)

- **페이지 렌더 유틸**: PDF page → PNG. 기본 후보는 라이선스 clean path인 pypdfium2 계열이며, 고DPI 렌더와 orientation/skew metadata를 남겨야 한다.
- **결정론 추출기**: ODL 또는 동등 엔진으로 텍스트, bbox, reading-order 후보, table region, semantic table(row/column/cell/bbox)을 뽑는다. born-digital 숫자와 텍스트는 이 결과를 source of truth로 둔다.
- **Processing-depth router**: 기본은 결정론 처리. scan/text-layer 부재, 그림·차트, 인코딩 깨짐, 산술 불변식 실패, 결정론 table/reading-order 불완전, orientation 불확실 같은 명시 트리거가 있을 때만 OCR/VLM으로 escalation한다.
- **페이지 방향 인식/보정**: 회전, skew, 다단 reading order를 VLM 입력과 최종 md/json 모두에 반영한다.
- **페이지 걸친 표 assembler**: 연속 페이지의 table bbox 열 좌표, column signature, header/continuation 신호를 비교해 logical table을 하나로 병합한다.
- **VLM 2-패스 모듈 (공유, 위치만 다름)**: 계약
  ```
  vlm_pass(
    deterministic_md | None,
    deterministic_json | None,
    page_images | multi_page_images,
    orientation_metadata,
    intent_prompt | None,
    guard_policy
  )
    -> { md, json_elements, tables_html, image_desc, confidence, guard_flags }
  ```
- **숫자 guard**: born-digital은 결정론 source text를 oracle로 주입한다. VLM 출력 숫자가 source에 없거나 산술 불변식을 깨면 거부/flag한다.
- **출력 IR**: page md/json + document md/json + logical tables + asset pointers + bbox/provenance/confidence/guard flags + **ledger**(per-page: 경로결정·엔진·토큰·$·지연·guard).
- **Processing tier / domain adaptation**: DET/VLM/HUM 경계, 사람검토 대상 분리, 도메인별 보정 도구는 `docs/processing-tiers-and-adaptation.md`를 따른다.
- **골든셋 + 스코어카드** (spike-plan §6).

이 요구사항의 상세 계약은 `docs/pdf-pipeline-requirements.md`와 `docs/processing-tiers-and-adaptation.md`가 기준이다. 이 문서는 Track A/B 중 어디서 그 계약을 만족할지 비교한다.

---

## 2. Track A — ODL 내부 (VLM을 하이브리드 백엔드로)

### 시퀀스
```
opendataloader-pdf --hybrid=docling-fast --hybrid-url=<adapter>
  1) ODL: veraPDF 결정론 파싱 + triage → 복잡 페이지 집합 산출
  2) ODL → adapter: POST /v1/convert/file  (원본 PDF + page_ranges=복잡페이지)
  3) adapter: 해당 페이지 렌더/방향보정 → [1차 md/json 필요시 자체 재파싱] → VLM 2-패스
              → DoclingDocument JSON 으로 성형하여 반환
  4) ODL: 백엔드 결과를 IObject로 흡수 → 최종 md/json + bbox + 태그
```

### 구성요소
- adapter 서버(FastAPI, `/v1/convert/file`)
- DoclingDocument JSON 성형기
- VLM 클라이언트(공유 모듈)

### 코드로 확인된 제약
- **(a) 1차 grounding 미전달**: 백엔드는 원본 PDF만 받음 → 진짜 2-패스(1차 md 기반)를 하려면 **adapter가 그 페이지를 자체 재파싱**해야 함. 아니면 순수(grounding 없는) VLM.
- **(b) 동적 프롬프트 불가**: 요청에 prompt 없음 → **adapter 레벨 고정 프롬프트(코퍼스 단위 의도)**만 가능. 문서/쿼리별 동적 의도 ✗.
- **(c) 출력 성형**: 결과를 **DoclingDocument 스키마**로 맞춰야 ODL이 흡수.
- **(d) 대용량 오버헤드**: 매 백엔드 콜에 **전체 PDF 재전송**.
- **(e) 페이지 걸친 표/멀티이미지 입력**: no-fork Track A는 backend protocol이 page range와 원본 PDF 중심이라, multi-image VLM 요청과 logical table 병합 책임이 adapter에 몰린다.
- **(f) 숫자 guard**: VLM 숫자 출력을 신뢰하지 않으려면 adapter가 결정론 source text oracle과 산술 불변식 검증을 별도 구현해야 한다.

### 단계
- **A1** 더미 어댑터: page_ranges 수신 로그만 → "triage가 어떤 입자(페이지 단위?)로, 어떤 페이지를 보내는가" 실측 + ODL VLM 주입 가능성 확정.
- **A2** 실 VLM: 어댑터가 페이지 렌더 + 자체 1차 파싱(grounding 보강) + VLM → DoclingDocument JSON.
- **A3 (조건부)** 경량 Java: `HybridRequest` 확장(1차 md/prompt 전달) + `SchemaTransformer`로 IObject 직접 매핑. ← (a)(b) 한계를 풀려면 필요.

### A가 답해야 할 질문
1. page_ranges가 정말 페이지 단위로 오는가(입자)?
2. 응답에 필요한 **DoclingDocument 최소 스키마**는?
3. grounding 없는 순수 VLM 품질이 골든셋에서 충분한가(충분하면 (a) 회피)?

---

## 3. Track B — 외부 오케스트레이터 (VLM을 ODL 밖에서)

### 시퀀스
```
  1) ODL 로컬 실행 → JSON (요소 + bbox + 페이지별 1차 md)   # triage 없음
  2) triage 신호 확보 (택1):
        - pdf-inspector --analyze  (권장: 독립, 무 JVM)
        - ODL 캡처-어댑터로 page_ranges 관측 (하이브리드 1회)
        - ODL TriageLogger 로그 파싱
  3) 오케스트레이터(Python): 복잡 페이지만
        페이지 렌더 + 방향보정 + ODL 1차 md/json + 동적 프롬프트
        + 필요 시 multi-image 묶음 → VLM 2-패스
  4) 숫자/source guard + 표 병합 → md/json 정규화 + ledger(결정·엔진·토큰·$·지연·guard)
```

### 구성요소
- ODL 러너(서브프로세스, 로컬 모드)
- triage 신호원(pdf-inspector 우선)
- orientation 보정기
- processing-depth router
- page-spanning table assembler
- 숫자 oracle/source gate/arithmetic invariant guard
- 오케스트레이터 + VLM 클라이언트(공유) + 정규화기 + ledger

### 장점 (코드로 확인)
- **1차 md 보유 → 진짜 grounded 2-패스** ✓
- **1차 JSON/bbox/table 후보 보유 → 숫자 oracle과 source gate 구현 용이** ✓
- **동적 프롬프트 자유** ✓ (문서/쿼리별 의도)
- **페이지 걸친 표를 multi-image VLM 요청으로 묶기 쉬움** ✓
- **ledger 완전 자유** ✓
- **무 Java** ✓

### 비용
- ODL 1회 + (triage) + VLM = 다단 처리.
- ODL 로컬 JSON의 **페이지별 1차 md/bbox가 2-패스 grounding에 충분한지** 확인 필요(대체로 충분 예상).

### B가 답해야 할 질문
1. pdf-inspector triage 정확도가 ODL triage를 대체할 만한가? (아니면 캡처-어댑터로 ODL triage 차용)
2. ODL JSON의 페이지별 1차 md/bbox/table 입자가 VLM grounding과 숫자 guard에 충분한가?
3. 페이지 걸친 표 continuation 판정 기준(bbox 열좌표, header/caption, column signature)의 false positive/negative는 허용 가능한가?

---

## 4. 구체 비교 (PDF 한정, 코드 확인 반영)

| 항목 | Track A | Track B |
|---|---|---|
| triage | **ODL 내장(공짜, page_ranges)** | 직접 추가(pdf-inspector 등) |
| 1차 grounding → VLM | ✗ (원본만 전달, adapter 재파싱 필요) | **✓ (ODL 1차 md 보유)** |
| 동적 프롬프트 | ✗ (요청에 없음, 어댑터 고정) | **✓** |
| ledger | 제한(ODL 로그 + 어댑터) | **완전(자체)** |
| 숫자 guard | adapter 별도 구현 필요 | **결정론 JSON 기반 구현 용이** |
| 페이지 걸친 표 | adapter 책임 큼 | **orchestrator가 병합 소유** |
| privacy/provider 제약 | backend별 별도 처리 | route policy에 통합 가능 |
| Java | A1/A2 없음, A3 필요 | **없음** |
| 처리 패스 | **1 (ODL 주도)** | 2 (ODL → VLM) |
| 출력 성형 | DoclingDocument JSON 맞춤 | 자체 IR |
| 대용량 | 매 콜 전체 PDF 재전송 | 1차 1회 |
| 컴팩트함 | **높음** | 중간 |

---

## 5. 핵심 통찰 (이게 결정의 축)

당신들의 핵심 요구인 **"결정론 grounding + 이미지/multi-image + 방향보정 + 동적 의도 프롬프트 + 숫자 guard"** 는 **코드상 Track A 프로토콜 경로(A1/A2)로는 충족 불가**다 — ODL이 백엔드에 1차 md/json도 프롬프트도 안 넘기기 때문이다. A에서 그걸 원하면 **A3(Java)로 HybridRequest를 확장**하거나 **adapter가 자체 재파싱, 표 병합, 숫자 guard**를 맡아야 한다.

반면 **Track B는 그 요구를 자연스럽게 충족**한다(ODL 1차 md/json 보유 + multi-image 구성 + 자유 프롬프트 + ledger + guard). 대신 B는 **triage/processing-depth와 page-spanning assembler를 직접 붙여야** 한다.

> 정리: PDF만 봐도 갈림이 분명하다.
> - **grounded·프롬프트형 2-패스가 핵심 → Track B** (또는 A3-Java).
> - **ODL triage를 그대로 + 순수/고정프롬프트 VLM이면 충분 → Track A1/A2** (가장 컴팩트).

---

## 6. 최소 PoC 순서 (PDF 한정)

1. **A1** — 더미 어댑터로 ODL triage의 page_ranges 입자·라우팅 실측 (+ grounding/prompt 한계 체감). *ODL VLM 주입 가능성 자체 판정.*
2. **B1** — ODL 로컬 JSON의 페이지별 1차 md/bbox 충분성 확인 + pdf-inspector triage 정확도 측정.
3. **공유 VLM 2-패스 모듈** 작성.
4. **A2 / B2** 실 VLM 연결 → 동일 코퍼스로 스코어카드 채점 → spike-plan §7 결정 게이트 적용.

---

## 7. 참고
- ODL 하이브리드/triage 내부: `docs/pdf-parsing-libraries-research.md` 부록 D
- bake-off 전체 계획·스코어카드·결정 게이트: `docs/parsing-engine-spike-plan.md`
- IR 계약 정렬 대상(LightRAG): https://github.com/HKUDS/LightRAG/issues/3197
