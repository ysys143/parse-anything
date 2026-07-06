# gt/ — Phase 0 골든 라벨

도메인별 대표 샘플의 **기대 출력 어서션**(전체 정답 아님). 스키마·판정 방식은 [SCHEMA.md](./SCHEMA.md).
`plan §5` 리스크(A 단위·B 산술·C 엔티티·G grounding·H PII)를 검증 가능한 형태로 인코딩.

## 라벨 현황 (10 라벨 / 8 도메인)

| 파일 | 도메인 | 주 검증 대상 | 핵심 리스크 |
|---|---|---|---|
| `statistics.json` | 통계 인포그래픽 | 차트 단위(시:분·분·%) | **A**(단위 오독) |
| `drawing_dim.json` | 치수 기계도면 | 치수·공차·표제란 | **B**(산술)·C·A |
| `table.json` | 표 | 그룹헤더 colspan·스패닝셀 | C·G |
| `form.json` | 폼(영수증) | 라인아이템 KV·산술(실값) | **B**(합계검산)·C |
| `handwriting.json` | 필기 폼 | 폼 구조+필기 전사 | C·H |
| `drawing.json` | 특허 도식 | **음성대조**(치수 없음) | A(치수 미조작) |
| `policy.json` | 정책 문서 | 요소 역할(콜아웃·법령박스) | C |
| `policy_table.json` | 정책 표 | 요구사항 ID 레지스터+합계 | C(ID)·B·G |
| `insurance.json` | 약관 | 다컬럼·콜아웃 | C·G |
| `insurance_diagram.json` | 약관 도식 | 지급 타임라인+조건 분기 | **FR-5.4**·A·C |

## 알려진 TODO (커버리지 갭)
- **[해소]** FR-5.4 분기 다이어그램 → `insurance_diagram.json`(계약취소 타임라인·청약철회 15/30/45일).
- **[해소]** 요구사항 추적성 표 → `policy_table.json`(SFR-000 등 ID 레지스터+합계행).
- **[해소]** form 실값·산술 → `form.json`(합=1,346,000; Grand Total=1,591,600 실측 검증).
- **[잔존]** 순수 관계형 도식(AS-IS/TO-BE 구조도): 현 policy 소스(swit 가이드)는 표·콜아웃 위주.
  참조 파서의 재난안전 플랫폼 구조도 같은 관계도는 별도 소스 필요(공공 정책 인포그래픽).
- **[잔존]** 한국어 필기: handwriting은 영문(census). 한국어 필기 정확도는 AI Hub 605 등 별도 소스.

## 사용
Phase 9 평가 하네스가 파이프라인 산출 JSON을 이 라벨과 대조. 자세한 판정 규칙은 SCHEMA.md.
