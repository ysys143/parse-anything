# Semantic Captioning — 데이터 확보 계획

> [semantic-captioning-plan.md](./semantic-captioning-plan.md)의 역설계 계획(Phase 0~9)을 위한
> 개발/검증용 문서 데이터 조사·확보 전략. 라이선스·URL은 드리프트 가능 → 실사용 전 원본 약관 재확인.
> 실제 코퍼스·재현 스크립트는 `benchmarks/semantic-captioning/`, 원본 바이너리는 로컬 전용(`.local/`).

## 0. 핵심 결론

1. **한국어 실전 벤치마크는 사실상 부재.** 표준 학술셋(FUNSD·XFUND·PubTabNet·ChartQA 등) 중
   한국어 커버 전무(XFUND도 한국어 미포함). 한국어 폼/표/차트 검증셋은 자체 구축 불가피.
2. **상업 배포 안전 + PDF 원본**을 동시 만족하는 코어: PubLayNet·DocLayNet(레이아웃),
   FinTabNet·SciTSR(표), DeepForm(폼).
3. **재배포까지 자유로운 한국 실문서**: 공공누리 제1유형 자료 + 법령 본문.
4. **AI Hub**는 한국어 라벨 최상이나 재배포 금지·국외반출 금지·내국인 계정 → 국내 학습 전용.
5. **엔지니어링 도면이 최난.** 기계 CAD 공개본 희소. 특허 도면(KIPRIS/DeepPatent2)이 현실적 경로.
   단 특허 도면은 규정상 치수 기입이 드물어, 치수 도면은 공개 기술도면(Wikimedia 등)이나 자체 확보 필요.

## 1. 도메인별 데이터 매핑

### 공통 — 레이아웃/표/폼 (FR-2, FR-4)
| 소스 | 용도 | 라이선스 | 형태 |
|---|---|---|---|
| PubLayNet / DocLayNet | 레이아웃 검출 | CDLA-Permissive | PDF+이미지 |
| PubTables-1M | 표 검출+구조 | CDLA-Permissive-2.0 | 이미지+XML |
| FinTabNet / SciTSR | 금융/과학 복잡표 | CDLA-Permissive / MIT | PDF 원본 |
| ICDAR 2013 표 | 골드 벤치 | 공공도메인 | PDF+XML |
| CORD | 영수증 KV | CC BY 4.0 | 이미지 |
| DeepForm | 실 PDF 폼 | MIT | PDF 원본 |
| DART / OpenDART | 한국 재무제표 표 | 회색지대 | PDF/XBRL |

### 도메인별 (FR-5)
| 도메인 | 소스 | 라이선스 | 비고 |
|---|---|---|---|
| 도면(치수) | Wikimedia 기술도면(치수 기입본) / DeepPatent2 / KIPRIS | CC BY-SA·PD / CC BY 4.0 / 약관확인 | 특허 도면은 치수 희소 → 치수 도면 별도 |
| 정책 도식 | 공공데이터포털(공공누리1) / 나라장터 RFP OpenAPI / DocLayNet | 공공누리 / 준용 | 나라장터 2025.1 차세대 오픈 |
| 약관 | 금감원 표준약관 / 법제처 OPEN API / 협회 공시 | 공공성 / 개별사 저작물 | 조·별표·표 구조 |
| 폼/손글씨 | AI Hub 605(국내) / CORD / 공개 필기 폼(인구조사 등, PD) | AI Hub 비배포 / CC BY / PD | 한국어 손글씨는 자체 구축 |
| 통계 | 통계청 KOSIS / ChartInfo / PlotQA | 텍스트 공공누리·이미지 개별 / CC BY | 인포그래픽 삽화 재배포 주의 |

## 2. 라이선스 신호등 (상용 학습·배포 관점)

- **초록(안전)**: PubLayNet, DocLayNet, DocBank, PubTables-1M, FinTabNet, SciTSR, ICDAR2013/2019,
  TableBank, CORD, DeepForm, RIMES-2011-line, PlotQA, ChartInfo, CGHD, PID2Graph, DeepPatent2,
  공공누리1 한국 문서, 법령/표준약관, Wikimedia PD/CC-BY 기술도면.
- **노랑(조건부)**: ChartQA·Chart-to-Text·ROBIN(GPL) / DART(회색지대) / KIPRIS·KOSIS 이미지 / CC BY-SA(share-alike).
- **빨강(비상업 — 상용 금지)**: WTW, FUNSD, XFUND, EPHOIE, IAM, CVL, DVQA, FigureQA,
  FloorPlanCAD, CubiCasa5K, AI Hub(재배포·국외반출 금지).

## 3. PDF 원본 vs 이미지 전용
- **PDF/벡터 원본**: PubLayNet, DocLayNet, FinTabNet, SciTSR, ICDAR2013, DeepForm, 한국 공공 PDF.
- **이미지 전용**: 표 인식셋 다수, CORD·FUNSD·SROIE, 손글씨 전체, 차트 전체, 도면 대부분.

## 4. 확보 실행 계획 (Phase 0 골든셋 우선)

시드 규모: **도메인당 2~3장이면 충분**(스켈레톤 개발·회귀 검증 목적, 대량셋은 정확도 튜닝 단계).

1. **코어셋(해외 공개, 재배포 안전 + PDF)**: DocLayNet·FinTabNet·SciTSR·DeepForm·PubTables-1M.
2. **한국 실문서 API**: OpenDART(표), KOSIS(통계), 금감원 표준약관+법제처(약관), 나라장터(정책), KIPRIS(도면).
   — 전 소스가 OpenAPI 제공 → 사이트 크롤링보다 API 우선.
3. **AI Hub(제약 하)**: 88/605/632, 국내 학습 전용·비배포·참조 링크만.
4. **합성 보강(한국어 갭)**: 한국어 폼/표/차트/도면 캡션 골든셋은 자체 합성으로 부트스트랩.
   §5-A(단위)·B(산술)·G(grounding) 정답을 합성 단계에서 함께 생성.

현재 확보한 최소 시드 상세는 `benchmarks/semantic-captioning/SOURCES.md`.

## 부록 — 주요 출처
- 코어: DocLayNet(HF ds4sd/DocLayNet), FinTabNet(developer.ibm.com/exchanges/data/all/fintabnet),
  SciTSR(github.com/Academic-Hammer/SciTSR), DeepForm(github.com/project-deepform/deepform),
  PubTables-1M(HF bsmock/pubtables-1m).
- 차트/도면: ChartInfo, PlotQA, DeepPatent2(Harvard Dataverse), CGHD(DFKI), PID2Graph(Zenodo).
- 한국: OpenDART, KOSIS·지표누리, 금감원 표준약관, 법제처 OPEN API, 나라장터 OpenAPI, KIPRIS Plus,
  AI Hub. 공공누리 제1유형: kogl.or.kr/info/licenseType1.do.
