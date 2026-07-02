# PDF Pipeline Requirements

> 상태: 필수 목표 계약. 현재 구현 완료 선언이 아니라, ODL-VL이 만족해야 하는 PDF 파싱 파이프라인 요구사항이다.
> 적용 범위: 복잡한 PDF를 Markdown, 구조 보존 JSON, 표/이미지 asset, 합본 출력, ledger로 변환하는 end-to-end 파이프라인.
> 운영 경계: processing tier와 domain adaptation 요구사항은 `processing-tiers-and-adaptation.md`가 규정한다.

## 1. Scope and Non-Goals

이 문서는 현재 외부 오케스트레이터 slice보다 넓은 목표 계약이다. 현재 구현은 ODL-like page JSON을 받아 provider를 라우팅하고 per-page markdown/ledger를 쓰는 scaffold다. 최종 파이프라인은 PDF 입력부터 렌더, 결정론 추출, 처리깊이 판단, VLM escalation, 사람 검토 대상 분리, 문서 레벨 병합, 검증 ledger까지 포함해야 한다.

VLM은 숫자 진실성의 source of truth가 아니다. VLM은 구조, 레이아웃, 설명, 누락된 visual context 보강을 담당하고, born-digital 숫자와 텍스트는 결정론 추출 결과가 우선한다.

## 2. Mandatory Requirements

1. 페이지 방향 인식과 보정은 필수다. 회전, skew, 다단 문서의 읽기순서가 downstream markdown/json/table assembly에 반영되어야 한다.
2. 복잡한 표, 병합셀, 중첩 헤더, 단위 row는 텍스트 휴리스틱만으로 처리하지 않는다. ODL의 의미 table 요소, 행/열/셀 bbox, 또는 동등한 구조 추출이 필요하다.
3. 처리깊이(결정론 / VLM)는 **런타임 per-page 자동 판정이 아니라 소스 단위 진단으로 정한 프로파일**을 따른다(§3.4, 처리계층 P7/§2.5). 결정론 트리거 집합은 그 진단의 입력 신호다 — fuzzy score가 아니다.
4. 페이지에 걸친 표는 하나의 logical table로 인식하고 재구성한다.
5. VLM 입력은 결정론 파싱 데이터, 페이지 이미지, 방향 보정 정보, 커스텀 프롬프트를 함께 포함한다. 페이지에 걸친 표나 이미지는 자동으로 multi-image 입력이 되어야 한다.
6. 출력은 페이지별 markdown/json과 문서 합본 markdown/json을 모두 제공한다. JSON은 표, 셀, bbox, page reference, confidence, guard flag를 보존해야 한다.
7. ledger는 페이지별 route, provider, 비용, 지연, guard flag, confidence, escalation reason을 기록한다.

## 3. Input and Rendering Pipeline

1. PDF 입력은 페이지 이미지로 렌더한다. 기본 렌더러는 라이선스가 clean한 pypdfium2 계열을 우선하며, 고DPI 렌더를 지원해야 한다.
2. 결정론 추출은 텍스트, bbox, reading order 후보, 표 영역, 의미 table 요소를 만든다. born-digital 문서의 정확한 숫자와 구조는 이 단계가 보존한다.
3. scan vs born-digital 판정은 pdf-inspector classify 결과와 텍스트 char 수를 함께 사용한다.
4. **처리깊이는 런타임에 페이지마다 자동 판정하지 않는다** (결정론 구조검출기가 문서종류마다 다르게 오탐하므로 — `measurement-findings.md` F16). 대신 아래 신호는 **소스 진단**(`processing-tiers-and-adaptation.md` §2.5)의 입력으로 쓰여, 그 소스의 **실행 모드·위험 핫스팟·적용 가드**를 정한다.
   - 스캔 또는 text layer 부재
   - 그림, 차트, diagram 의미 설명 필요
   - 인코딩 깨짐, CID/ToUnicode 문제, 비정상 글리프
   - 산술 불변식 실패
   - 결정론 table/reading-order/bbox 불완전
   - 낮은 품질, 회전, skew, orientation 불확실
5. **실행은 소스 프로파일이 지정한 모드대로 한다** (예측가능, 런타임 라우팅 없음). 모드는 두 가지(처리계층 §2.6): **결정론 모드**(ODL+pypdfium2 병용) 또는 **결정론-powered VLM 모드**(ODL+pypdfium2+VLM을 *둘 다/셋 다* 돌려 정합 — 라우팅 누락 없음). 모드·임계·가드는 실제 코퍼스/골든셋에서 진단으로 보정한다. DET/VLM/HUM 계층 경계와 도메인 보정 도구는 `processing-tiers-and-adaptation.md`를 따른다.

## 4. Table Policy

복잡한 표는 두 단계로 처리한다.

1. 결정론 단계에서 table region, row, column, cell, bbox, text token을 수집한다. **역할 분리**(`measurement-findings.md` F16/F17): *구조*(격자/병합/헤더)는 **ODL**(또는 pdf-inspector)의 후보 — 단 *권위가 아님*(둘 다 문서종속 오탐). *값·셀 텍스트*는 **pypdfium2**가 권위(완전성: ODL은 실숫자를 누락할 수 있어 pypdfium2로 백스톱·플래그). 즉 ODL의 표 격자에 pypdfium2 텍스트/값을 채운다.
2. VLM 단계(결정론-powered VLM 모드)는 병합셀 구조, 헤더 계층, visual grouping, continuation 여부를 보강하고, 결정론(ODL+pypdfium2)과 정합한다(처리계층 §2.6, R-M1: 구조=VLM/ODL, 값=pypdfium2+값오라클).

페이지에 걸친 표는 다음 규칙으로 인식한다.

1. 연속 페이지의 table bbox 열 좌표, column count, header 또는 continuation caption, y-position 패턴을 비교한다.
2. 연속성이 높으면 해당 페이지들을 multi-image 단일 VLM 요청으로 보낸다.
3. 병합된 logical table은 시작 페이지에 부착한다. continuation 페이지에는 folded reference를 남기고 중복 표를 만들지 않는다.
4. 3쪽 이상 표는 overlap chunk로 나눈다. 각 chunk는 인접 페이지를 겹쳐 보내고, chunk 결과는 table id와 column signature로 병합한다.
5. 병합 후 JSON은 `source_pages`, `source_regions`, `continued_from`, `continued_to`, `cells[].bbox`, `cells[].source_text` 같은 provenance를 보존해야 한다.

## 5. VLM Call Recipe

결정론-powered VLM 모드는 **ODL + pypdfium2 + VLM 세 소스를 모두 입력으로 정합**한다(라우팅 없음). VLM 요청은 다음 입력을 포함한다.

- 결정론 텍스트/구조 후보: **ODL**(표 격자·읽기순서·청결 텍스트) + **pypdfium2**(값 완전성·char bbox)
- 결정론 JSON 후보: 텍스트 token, bbox, table regions, cell candidates, source page ids
- 방향 인식/보정 결과: rotation, skew, corrected image metadata
- 페이지 이미지: 단일 페이지 또는 자동 multi-image
- 커스텀 프롬프트: 문서/사용자 목적별 구조화 지시
- guard policy: 숫자 oracle, source gate, arithmetic invariant

VLM 출력은 구조 보강 결과로 취급한다. 숫자 값은 결정론 source text와 매칭된 경우에만 신뢰한다. VLM이 source에 없는 숫자를 생성하면 거부하거나 flag한다.

## 6. Numeric Accuracy and Hallucination Guards

Born-digital 문서는 숫자 oracle을 주입한다. 텍스트 레이어에서 추출한 값을 셀 후보에 넣고, VLM이 숫자를 새로 읽거나 추측하지 않게 한다.

필수 guard는 다음과 같다.

1. Source gate: VLM 출력 숫자가 결정론 source text에 없으면 거부하거나 flag한다.
2. Arithmetic invariant: 소계 = 라인 합, VAT = 소계 x 1.1, 수량 x 단가 = 합계 같은 문서별 불변식을 검증한다.
3. Escalation gate: 결정론 결과가 arithmetic invariant를 깨면 VLM/OCR 또는 사람 검토로 보낸다.
4. Scan guard: oracle이 없는 스캔 문서는 프롬프트 기권, 이중 provider pass, 입력 품질 게이팅을 함께 적용한다.
5. Human review: 스캔에서 잔여 위험 셀만 사람 검토 대상으로 남긴다. 완전 자동 숫자 신뢰를 약속하지 않는다.

검증 목표는 hallucinated number 차단, 낮은 오거부율, flag된 셀과 미flag 셀의 신뢰도 분리다.

## 7. Output Contract

최종 산출물은 최소 아래를 포함한다.

- `pages/`: 페이지별 markdown
- `document.md`: 문서 합본 markdown
- `document.json`: loss-aware 구조 JSON
- `tables/`: logical table별 JSON/HTML/Markdown view
- `assets/`: 추출 또는 렌더된 이미지/표 crop metadata
- `results.jsonl`: 페이지별 route/provider/status/output pointers
- `ledger.jsonl`: route, provider, cost, latency, guard flags, confidence, escalation reason

Markdown은 사람이 읽기 좋은 view다. JSON은 source of truth이며, element id, page id, bbox, table/cell hierarchy, source text, asset pointer, continuation relation을 보존해야 한다.

- **소스 레벨 메타데이터(증보).** `document.json`은 페이지 메타에 더해 **소스 식별·프로파일·진단 출처**(source id, 적용된 소스 프로파일·실행 모드, 진단 등급 D-1/D-2와 시각)를 기록한다 (처리계층 §2.5). 같은 소스에서 나온 문서들이 동일 프로파일로 처리됐음을 추적할 수 있어야 한다.
- **모드 매핑.** 두 실행 모드 모두 이 계약을 산출한다 — `tables/`·`assets/`의 구조는 ODL, 값/`cells[].source_text`는 pypdfium2, 결정론-powered VLM 모드는 VLM 보강분을 정합해 넣는다(provenance에 출처 표기).
- **현 구현 갭.** `src/parse_anything/pipeline/output.py`는 현재 `pages/`·`document.md`·`ledger.jsonl`·`results.jsonl`만 쓰고, `document.json`(loss-aware)·`tables/`·`assets/`·소스 메타데이터는 미구현이다. 목표 계약과의 차이는 §10에 정리한다.

## 8. Verification Contract

검증은 실제 코퍼스 30~50페이지와 골든셋으로 한다. 현재 소수 샘플만으로 품질을 주장하지 않는다.

필수 지표:

- reading order accuracy
- page orientation correction accuracy
- complex table fidelity / TEDS
- page-spanning table reconstruction accuracy
- numeric accuracy
- hallucination rate
- source-gate false reject rate
- routing / processing-depth accuracy
- provider cost and latency
- guard flag precision/recall
- human-review volume and precision
- domain adaptation before/after error and cost deltas

코퍼스는 born-digital, scan, 다단, 회전/skew, 복잡 표, 페이지 걸친 표, 그림/차트, 산술 불변식이 있는 문서, 민감 문서 제약 케이스를 포함해야 한다.

## 9. Licensing and Privacy Constraints

라이선스 clean path를 우선한다.

- Prefer: pypdfium2, pdf-inspector, OpenDataLoader/ODL
- Avoid by default: PyMuPDF / PyMuPDF4LLM, unless AGPL or commercial-license implications are explicitly accepted

민감 문서는 provider I/O 제약을 route 결정에 반영한다. PaddleOCR official API가 이미지 URL fetch만 지원하고 base64 inline image를 지원하지 않는 경로라면, 공개 호스팅이 필요한 민감 문서에는 부적합하다. 그런 문서는 inline image 지원 provider, private network hosting, or local/self-hosted provider 경로로만 보낸다.

## 10. Implementation Status

목표 아키텍처(이 문서 + 처리계층 P7/§2.5–2.6)는 **R1–R8로 구현 완료**. 구현된 것:

- **아키텍처(R1):** 런타임 per-page 자동 라우팅 폐기 — `decide_route`는 진단 신호로 강등(런타임 호출 0). 소스 단위 **진단-설정** + mode 구동(`run.py`/`assemble.py`). mode가 레버(키 누락 시 silent downgrade 금지).
- **결정론 베이스(R1):** ODL(`odl_extract.py`, 구조·청결 텍스트·단락·표 격자·셀 bbox) + pypdfium2(값 완전성/위치) **병용**. `deterministic` 모드(ODL+pypdfium2 완전성 백스톱), `det_vlm` 모드(+ VLM 정합, R-M1).
- **det_vlm 가드/보강(R8):** ODL+pypdfium2 **이중주입 그라운딩**(`grounding.py`), 스팬 표 다중이미지 재구성(`previous_table_id` 그룹), 값 오라클(`oracle.py`)·산술 불변식(`arithmetic.py`)·스캔 **이중패스**(Gemini+Paddle, `paddle_vlm.py`)·입력품질·가독성 가드. 전부 옵트아웃.
- **진단 도구(R3–R4):** D-1 내장 VLM(`diagnose.py`, 측정 기반·구조-인지 샘플링) + D-2 에이전트 번들/스킬(`diagnose_prepare.py`, `docs/diagnostic-d2.md`) → `SourceProfile` 영속·재사용(per-source 임계값 루프 포함).
- **리치 출력(R2):** `<out>/<source_id>/<document_id>/`에 `document.json`(loss-aware: content-hash id·프로비넌스·페이지 blocks·표/그림 bbox·원본 라벨·산술)·`tables/`·`assets/`·`pages/`·`ledger.jsonl`. content-hash 멱등 + 재처리 skip. SQLite 파생 카탈로그(`catalog.py`).
- 측정 근거: F16–F21(measurement-findings). 164 테스트(격리 uv 환경).

**남은 것:**

- **§8 골든-코퍼스 정량 검증(미수행, 핵심):** 30~50페이지 골든셋으로 reading order·TEDS·numeric accuracy·hallucination rate·source-gate 오거부율·guard precision/recall·사람검토량 등 측정. 캘리브레이션(F18/F19, ~36문서)은 *mode 라벨 oracle 판정*이지 per-element 골든 채점이 아님 → **골든 라벨 생성이 선행.**
- **enhancement:** oracle bbox **값-치환**(현재 *플래그*만, 정확 위치 *치환*은 미착수); 노이즈-인지 입력품질 지표(F21); 스팬에 Paddle 더블패스.
- **의도적 보류(by design):** 서비스 레이어(FastAPI) — CLI/라이브러리가 계약 입증 후; 추가 provider(Ollama/GLM-OCR/Nemotron).
