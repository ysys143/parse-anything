# Golden Seed — 소스 매니페스트

Semantic Captioning 역설계용 최소 시드(도메인당 2~3장). 전부 **무계정 공개 소스**.
원본 바이너리는 커밋하지 않는다(`fetch.py`로 재현, 로컬 `.local/semantic-captioning/corpus/raw/` 상주).
취득 기준일 2026-07-06.

## 구성 (8 도메인 / 19 파일)

| 도메인 | 파일 | 출처 | 라이선스 |
|---|---|---|---|
| drawing | patent_US6285999B1.pdf (12p) | Google Patents (patentimages) | US 특허 공보(공공) |
| drawing | patent_US7663607B2.pdf (33p) | Google Patents | US 특허 공보. 번호 콜아웃 도식(치수 없음) |
| drawing_dim | wikimedia_schneckenwelle_worm_shaft.png | Wikimedia Commons | CC BY-SA 3.0. 완전 치수 기계도면(Ø치수·공차·GD&T·표제란·파라미터표) |
| drawing_dim | wikimedia_boundy_diameter_dimensioning.png | Wikimedia Commons | Public Domain. 직경 치수기입 규약 예시 |
| table | arxiv_1706.03762_attention.pdf | arXiv | arXiv 비독점. 표·수식 다수 |
| table | arxiv_2005.14165_gpt3.pdf | arXiv | 표 대량 |
| form | cord_receipt_1~3.jpg | HF naver-clova-ix/cord-v2 | CC BY 4.0. 영수증 KV |
| statistics | kostat_고령자통계_2025.pdf | 통계청 kostat.go.kr | 텍스트 공공누리 / 삽화 개별. 차트·표 |
| statistics | kostat_사회조사_2024.pdf | 통계청 | 동일. 그래프 다수 |
| insurance | samsungfire_개인용자동차보험_약관_2023.pdf | samsungfire.com | 개별사 저작물. 조·별표·표 |
| insurance | hyundai_실손의료비_약관_2026.pdf | hi.co.kr | 시각화 요약+보통/특별약관 |
| insurance | insure_or_kr_생명보험표준약관_및해설.pdf | 보험연수원 | 표준약관+해설 |
| insurance | kiri_표준약관개정안_주요내용.pdf | 보험연구원 | 개정안 요약 |
| policy | swit_요구사항상세화_실무가이드라인.pdf | swit.or.kr | 공공SW RFP 가이드. 도식·표 다수 |
| policy | swit_공공정보화_제안요청서_작성가이드.pdf | swit.or.kr | RFP 다이어그램·표 |
| policy | knowhow_참여정부_정책보고서.pdf | knowhow.or.kr | 정책 도식·표 |
| handwriting | census_1900_population_schedule.jpg | Wikimedia Commons | Public Domain. 인쇄 폼 + 전면 필기 기입 |
| handwriting | census_1950_us.jpg | Wikimedia Commons | Public Domain. 필기 인구조사 명부 |

## 알려진 갭 / 주의

1. **도면 치수**: 특허(drawing/)는 규정상 치수 희소 → drawing_dim/(Wikimedia 치수 도면)으로 보완.
   한국어 표제란 치수 도면이 필요하면 KIPRIS 기계 특허 중 치수 포함본 추가.
2. **손글씨(한국어 갭)**: handwriting/census는 "필기+폼 구조" 능력 검증용이나 **영문**.
   한국어 필기 인식 검증은 AI Hub 605(내국인·비배포) 또는 자체 스캔 필요. form/(CORD)은 인쇄.
3. **통계 인포그래픽 삽화 저작권**: 입력용 자유, 결과 재배포 시 이미지 주의.
4. **약관 개별사 저작물**: samsungfire/hyundai는 각 사 저작물. 재배포·공개엔 표준약관(insure/kiri) 우선.
5. **CC BY-SA 3.0(schneckenwelle)**: 재배포·파생 시 출처표시 + 동일조건 유지.

## fetch.py 재현성 노트

- 대부분 안정 직링크. **CORD**는 HF datasets-server의 서명 URL이 만료되므로 fetch 시점에 API 재질의.
- **patent**은 Google Patents 페이지에서 patentimages PDF 링크를 재추출(해시 URL 변동 대비).
- 일부 한국 공공(policy) 링크는 게시물 seq/파일명 변동 가능 → 실패 시 SOURCES 표의 출처에서 수동 확인.
