# parse-anything — 프로젝트 성과 개요 (내부 노트)

관통 한 줄기: **결정적 구조 + 게이트된 VLM 콘텐츠 → 버전 계약된 레이어드 substrate → 온톨로지 태깅 → agent/RAG-ready 청크**. "또 하나의 PDF 파서"가 아니라 재사용 가능한 문서-이해 기반이 차별점.

## 핵심 성과

1. **결정적 구조 / VLM 콘텐츠 분리 (설계 원칙)**: reading order·섹션·표·그림 기하는 ODL/pypdfium2로 run-invariant 추출(할루시네이션 없음), 전사·그림 판단만 VLM.
2. **Born-digital value oracle (수치 무결성)**: pypdfium2가 VLM 수치를 게이트(`unsourced_number`), 결정적 모드는 ODL 누락 숫자 백스톱(`odl_dropped_number`). VLM이 숫자를 못 지어냄 — 가장 위험한 실패 모드를 구조적 차단.
3. **Loss-aware 레이어드 아티팩트 + 버전 계약**: `document.json`(Layer 0 무손실 진실) → structure(0+1) → semantic/provenance(2) → chunks.jsonl(small-to-big). `StructureExport/SemanticView/Provenance/ChunkRecord` 계약, emission 라운드트립 = 회귀 테스트. 소비자는 계약에 바인딩(내부 구현 아님).
4. **온톨로지 기반 태깅(데이터, 코드 아님)**: `ontology/<family>.md`(default/paper) + `eval` 없는 predicate 레지스트리 + first-match 규칙 엔진. 새 문서 유형 = 마크다운 하나. EN·KR 검증. furniture zone-out, reference per-entry, caption/수식 1급 노드.
5. **Diagnose-then-configure**: 페이지 런타임 라우팅 폐기 → 소스 단위 D-1 진단 → 모드·가드 고정 → 재사용 `SourceProfile`(F16/F17 근거).
6. **Agent/RAG + LightRAG 통합**: 검증된 2경로 정본(delimiter / `custom_kg` + concept fusion) + 재현 테스트 + 격리 도커 데모. 상세는 [LightRAG 통합 가이드](../lightrag-integration-guide.md).
7. **배포/검증**: curl|sh 셀프컨테인 인스톤러, `parse-anything`/`parse`/`pa` CLI, 릴리스 번들(PyInstaller + jlink), 테스트 335+ 통과, 실문서 검증. 벤치 하네스(three-way, ocr-sweep 8모델).
8. **업스트림 기여**: ODL triage 스캔 버그 PR.

## 솔직한 경계선 (아직 아닌 것)

- README상 "production-ready 아님, 인터페이스 변경 가능".
- **Mode 2(우리 KG 산출) 코드는 유예** — retrieval 지표로 default를 고른 뒤 구축.
- LightRAG 인제스트도 정본 레시피·데모까지이고 `src` 런타임 어댑터는 없음(중립 substrate 유지).
- 벤치마크는 소표본 프로토타입 증거.

## 최대 차별점 2가지

(2) 수치 무결성 오라클, (3) 계약 기반 substrate.

교훈: "돌려봐야 안다" — 설계·계약·유닛테스트가 다 맞아도 실제 의존성에 실문서를 통과시켜야 함정(sanitize 구분자 삭제, gemini-embedding-2 배치 붕괴, `ainsert_custom_chunks` merge 버그, flash-lite JSON 2개)이 드러난다.
