# PDF 집중: Track A(ODL 내부 VLM) / Track B(외부 오케스트레이터) 구체 설계

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

- **페이지 렌더 유틸**: PDF page → PNG (pymupdf/pdfium).
- **VLM 2-패스 모듈 (공유, 위치만 다름)**: 계약
  ```
  vlm_pass(page_image, first_pass_md | None, intent_prompt | None)
    -> { md, json, tables_html, image_desc, confidence }
  ```
- **출력 IR**: md + json(요소 타입·bbox·표 HTML·confidence) + **ledger**(per-page: 경로결정·엔진·토큰·$·지연).
- **골든셋 + 스코어카드** (spike-plan §6).

---

## 2. Track A — ODL 내부 (VLM을 하이브리드 백엔드로)

### 시퀀스
```
opendataloader-pdf --hybrid=docling-fast --hybrid-url=<adapter>
  1) ODL: veraPDF 결정론 파싱 + triage → 복잡 페이지 집합 산출
  2) ODL → adapter: POST /v1/convert/file  (원본 PDF + page_ranges=복잡페이지)
  3) adapter: 해당 페이지 렌더 → [1차 md 필요시 자체 재파싱] → VLM 2-패스
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
        페이지 렌더 + ODL 1차 md + 동적 프롬프트 → VLM 2-패스
  4) 병합 → md/json 정규화 + ledger(결정·엔진·토큰·$·지연)
```

### 구성요소
- ODL 러너(서브프로세스, 로컬 모드)
- triage 신호원(pdf-inspector 우선)
- 오케스트레이터 + VLM 클라이언트(공유) + 정규화기 + ledger

### 장점 (코드로 확인)
- **1차 md 보유 → 진짜 grounded 2-패스** ✓
- **동적 프롬프트 자유** ✓ (문서/쿼리별 의도)
- **ledger 완전 자유** ✓
- **무 Java** ✓

### 비용
- ODL 1회 + (triage) + VLM = 다단 처리.
- ODL 로컬 JSON의 **페이지별 1차 md/bbox가 2-패스 grounding에 충분한지** 확인 필요(대체로 충분 예상).

### B가 답해야 할 질문
1. pdf-inspector triage 정확도가 ODL triage를 대체할 만한가? (아니면 캡처-어댑터로 ODL triage 차용)
2. ODL JSON의 페이지별 1차 md/bbox 입자가 VLM grounding에 충분한가?

---

## 4. 구체 비교 (PDF 한정, 코드 확인 반영)

| 항목 | Track A | Track B |
|---|---|---|
| triage | **ODL 내장(공짜, page_ranges)** | 직접 추가(pdf-inspector 등) |
| 1차 grounding → VLM | ✗ (원본만 전달, adapter 재파싱 필요) | **✓ (ODL 1차 md 보유)** |
| 동적 프롬프트 | ✗ (요청에 없음, 어댑터 고정) | **✓** |
| ledger | 제한(ODL 로그 + 어댑터) | **완전(자체)** |
| Java | A1/A2 없음, A3 필요 | **없음** |
| 처리 패스 | **1 (ODL 주도)** | 2 (ODL → VLM) |
| 출력 성형 | DoclingDocument JSON 맞춤 | 자체 IR |
| 대용량 | 매 콜 전체 PDF 재전송 | 1차 1회 |
| 컴팩트함 | **높음** | 중간 |

---

## 5. 핵심 통찰 (이게 결정의 축)

당신들의 핵심 요구인 **"Enhans식 2-패스 = 1차 결정론 grounding + 동적 의도 프롬프트"** 는 **코드상 Track A 프로토콜 경로(A1/A2)로는 충족 불가**다 — ODL이 백엔드에 1차 md도 프롬프트도 안 넘기기 때문. A에서 그걸 원하면 **A3(Java)로 HybridRequest를 확장**하거나 **adapter가 자체 재파싱**해야 한다.

반면 **Track B는 그 요구를 자연스럽게 충족**한다(ODL 1차 보유 + 자유 프롬프트 + ledger). 대신 B는 **triage를 직접 붙여야** 한다(pdf-inspector).

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
