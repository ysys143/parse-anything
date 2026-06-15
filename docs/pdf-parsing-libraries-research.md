# PDF 파싱 / 문서 변환 라이브러리 조사 보고서

> 대상: OpenDataLoader PDF · Docling · MinerU 에 비견할 만한 PDF 파싱·문서 변환 라이브러리
> 작성일: 2026-06-15 · 범위: 오픈소스 중심(상용 API·벤치마크 포함)
> 방법: 공식 저장소(GitHub) · 문서 · 논문(arXiv) · HuggingFace 카드 · 벤더 블로그를 다중 출처로 교차검증.
> 주의: arxiv.org / huggingface.co / 일부 벤더 페이지가 조사 환경에서 HTTP 403을 반환해, 해당 항목은
> `raw.githubusercontent.com` · 공식 블로그 · 검색 스니펫으로 보강했으며 본문에 *벤더 보고/미검증* 표시를 달았습니다.
> 벤치마크 수치와 GitHub 스타 수는 빠르게 바뀌므로 시점 스냅샷으로 보십시오.

---

## 0. 30초 요약 (TL;DR)

- **세 가지 갈래**로 나뉩니다.
  1. **파이프라인형(전통+딥러닝 모듈 조합)**: Docling, MinerU(파이프라인 백엔드), OpenDataLoader(로컬 모드), Unstructured, PaddleOCR/PP-StructureV3, Marker, GROBID.
  2. **VLM 엔드투엔드(단일 비전-언어 모델이 페이지 → 구조화 출력)**: MinerU2.5, PaddleOCR-VL, dots.ocr, MonkeyOCR, olmOCR, DeepSeek-OCR, GOT-OCR 2.0, Nougat, SmolDocling/Granite-Docling, (상용) Mistral OCR.
  3. **상용/클라우드 API**: LlamaParse, Reducto, Azure AI Document Intelligence, AWS Textract, Google Document AI, Mathpix, Upstage, Adobe PDF Extract.
- **정확도 최상위(2026년 중반, OmniDocBench v1.6 기준)**: MinerU2.5-Pro · GLM-OCR · PaddleOCR-VL-1.5 가 95% 안팎으로 선두이며, 전용 VLM이 Gemini 3 Pro 같은 범용 프런티어 VLM을 앞섭니다.
- **라이선스가 의사결정의 핵심**: 코드와 **모델 가중치 라이선스가 다른** 경우가 많습니다. 상업적 사용에 안전한 순수 오픈은 **OpenDataLoader(Apache-2.0)·Docling(MIT+가중치 Apache-2.0)·PaddleOCR-VL(Apache-2.0)·olmOCR(Apache-2.0)·DeepSeek-OCR(MIT)**. 제약이 있는 것은 **Nougat(가중치 CC-BY-NC)·Marker(가중치 RAIL-M, 매출 $2M 상한)·MonkeyOCR(가중치 비상업)·GOT-OCR(데이터 CC-BY-NC, 저장소 "research only" 문구)·MinerU(커스텀 라이선스, MAU 1억/매출 $20M 상한)**.
- **OpenDataLoader의 차별점**: CPU 전용·결정론적(룰 기반)·요소 단위 bounding box·태그드(접근성) PDF 자동 생성·프롬프트 인젝션 필터 — "로컬/온프레미스·저자원·deterministic" 축에서 독보적.

---

## 1. 기준 3종 (Baseline)

### 1.1 OpenDataLoader PDF
- **정체/운영**: 한국 **한컴(Hancom)**이 `opendataloader-project` GitHub 조직으로 공개. veraPDF 개발사 **Dual Lab** 및 **PDF Association**과 협업. 주 언어는 **Java(~86%)**, Python/Node.js/Java SDK 및 LangChain·LlamaIndex 연동 제공.
- **버전/라이선스**: v2.4.7(2026-05). **Apache-2.0** (v2.0 이전은 MPL-2.0) — AGPL인 MinerU 대비 permissive를 강조.
- **구조**: 하이브리드. ① **로컬 모드** = ML 없이 네이티브/태그드 PDF에서 결정론적 휴리스틱 추출, **GPU 불필요·~0.015–0.02초/페이지**, XY-Cut++ 읽기순서, 모든 요소에 bounding box. ② **하이브리드 모드** = 복잡한 페이지만 AI 백엔드로 라우팅(OCR 80+ 언어, 표/수식, 차트 설명에 경량 **SmolVLM 256M**), ~0.46초/페이지. 처리는 전부 로컬.
- **출력**: JSON(bbox+의미 요소), Markdown, HTML, 주석 PDF, 텍스트, **태그드 PDF(접근성)**.
- **차별점**: 요소별 bbox 기본 제공(Docling은 미흡), CPU 전용, **프롬프트 인젝션/숨김텍스트 필터(safe-by-design)**, 완전 로컬, **미태그 PDF → 스크린리더용 태그드 PDF 자동 변환**(PDF/UA·유럽 접근성법 대응).
- **벤치(벤더 자체 200개 PDF)**: 하이브리드 종합 ~0.907(읽기순서 0.934, 표 0.928) — *벤더 보고, 독립 OmniDocBench 등재 아님*.

### 1.2 Docling
- **정체/운영**: IBM Research Zurich에서 시작 → 현재 **LF AI & Data 재단** 프로젝트. **파이프라인 파서**이며 선택적으로 VLM 모드 제공.
- **버전/라이선스**: v2.x(2026, 100+ 릴리스). **코드 MIT**, 모델 가중치(Granite-Docling)는 **Apache-2.0**.
- **구조**: ① 표준 파이프라인 = DocLayNet 학습 레이아웃 검출(RT-DETR 계열) + **TableFormer**(표 구조) + OCR(EasyOCR/Tesseract/RapidOCR/ocrmac 선택) + 수식·코드 enrich. ② **VLM 파이프라인** = 단일 모델 **Granite-Docling-258M**(이전 실험판 SmolDocling-256M)로 **DocTags** 생성.
- **입력**: PDF/DOCX/PPTX/XLSX/HTML/EPUB/이미지/오디오/EML 등 광범위. **출력**: Markdown/HTML/JSON(무손실 DoclingDocument)/DocTags/WebVTT.
- **특징**: 입력 포맷 폭이 가장 넓고 RAG 생태계(LangChain·LlamaIndex·Haystack·MCP) 통합이 강함. **GPU 불필요**(노트북 실행 가능), 완전 로컬/에어갭 지원.

### 1.3 MinerU
- **정체/운영**: **OpenDataLab(상하이 AI 연구소)**. PDF-Extract-Kit 기반이며 **OmniDocBench 벤치마크의 운영 주체**(자체 평가 편향 주의).
- **버전/라이선스**: v3.3.1(2026-06). **MinerU Open Source License**(Apache-2.0 기반 커스텀; **AGPL-3.0에서 전환**). 상업적 사용 허용하되 **MAU 1억 초과 또는 월매출 $20M 초과 시 별도 상업 라이선스**·출처 표기 의무.
- **구조**: 듀얼 백엔드. ① **파이프라인**(CPU 호환, 모듈식) ② **VLM**(MinerU2.5 / 2.5-Pro, **1.2B** 디커플드 VLM — 다운샘플 레이아웃 분석 후 원해상도 크롭 인식). vLLM 등으로 가속.
- **기능**: 레이아웃·읽기순서·헤더/푸터 제거, 표 → **HTML**, 수식 → LaTeX, **OCR 109개 언어**, 스캔/필기/다단.
- **출력**: Markdown, JSON(읽기순서 정렬).
- **벤치**: 파이프라인 ~85.75, VLM/하이브리드 ~95.26–95.39, **MinerU2.5-Pro ~95.69–95.75**(OmniDocBench v1.6) — *동일 조직 운영 벤치임에 유의*.

| | OpenDataLoader PDF | Docling | MinerU |
|---|---|---|---|
| 운영 | 한컴 / PDF Assoc. / Dual Lab | IBM → LF AI & Data | OpenDataLab(상하이 AI랩) |
| 최신 | v2.4.7 (2026-05) | v2.x (2026) | v3.3.1 (2026-06) |
| 라이선스 | **Apache-2.0**(전 MPL-2.0) | **MIT**(가중치 Apache-2.0) | **커스텀**(Apache 기반, 전 AGPL) |
| 접근 | 하이브리드: 결정론적 Java + AI | 하이브리드: 파이프라인 + VLM | 듀얼: 파이프라인 + 1.2B VLM |
| 강점 | 태그드 PDF·CPU 전용·bbox·safe | 입력 포맷 폭·RAG 생태계·DocTags | 최상위 정확도·소형 SOTA VLM |
| GPU | 불필요(하이브리드만 선택) | 불필요(VLM은 권장) | 파이프라인 CPU / VLM은 GPU |
| GitHub★ | ~25k | ~62k | ~68k |

---

## 2. VLM 엔드투엔드 모델군 (핵심 비교군)

> "odl-vl"(vision-language)의 맥락에서 가장 직접적인 비교 대상. 페이지 이미지를 단일 모델이 구조화 출력으로 변환.

### 2.1 Marker (Datalab / Vik Paruchuri)
- **성격**: 엄밀히는 **파이프라인**(Datalab의 **Surya** 모델군 조합 + 선택적 LLM 보정). PDF/이미지/오피스 → Markdown/JSON/HTML/chunks.
- **버전**: marker-pdf 1.10.2(2026-01).
- **라이선스(주의·이중)**: **코드 GPL-3.0**, **가중치 modified AI Pubs Open RAIL-M**(연구·개인·**펀딩/매출 $2M 미만** 무료, 초과 시 유료). Surya는 코드 Apache-2.0·가중치 $5M 상한.
- **기능**: 레이아웃·읽기순서·표(FinTabNet 0.816, `--use_llm` 시 0.907)·수식 LaTeX·코드·폼. OCR 90+ 언어(Surya). **GPU/CPU/MPS 모두 동작**.
- **벤치**: OmniDocBench v1.6 **78.44**, olmOCR-Bench **76.1**. 자체 벤치(H100)는 높게 보고(self-reported).
- **호스팅**: 셀프호스트(`pip install marker-pdf`) + Datalab 매니지드 API(고정밀 모델 "Chandra" 별도).

### 2.2 PaddleOCR-VL (Baidu)
- **성격**: 진짜 단일 **VLM**(경량 2단계 파이프라인). NaViT식 동적해상도 비전 인코더 + **ERNIE-4.5-0.3B** LLM = **~0.9B**.
- **버전**: 0.9B(2025-10), 1.5(2026-01), 1.6.
- **라이선스**: **Apache-2.0**(코드 확인; 가중치도 Apache로 보고되나 HF 카드 직접 확인 권장).
- **기능**: 레이아웃·표·수식 LaTeX·차트·필기·**OCR 109개 언어**·읽기순서·인장/텍스트 스포팅. 출력 Markdown/JSON(좌표 포함).
- **벤치**: OmniDocBench v1.0 edit 0.115, **olmOCR-Bench 80.0**(최상위급), OmniDocBench v1.5 ~92.6(0.9B), 1.5=94.5%, 1.6=96.3%(*상위 버전·일부 2차출처*).
- **호스팅**: 셀프호스트(vLLM 공식 지원), 경량이라 저자원 GPU/일부 CPU 가능.

### 2.3 dots.ocr (RedNote / Xiaohongshu)
- **성격**: 단일 VLM로 레이아웃 검출+인식+읽기순서 통합. 디코더 **Qwen2.5-1.5B(~1.7B로 홍보)** + 비전 인코더 **~1.2B** = **총 ~3B**. 후속 **dots.mocr**(2026-03 리브랜딩).
- **라이선스(주의·분쟁)**: **코드 MIT** 확정. 그러나 HF에 별도 "dots.ocr LICENSE AGREEMENT" 파일이 있고 코드 LICENSE와 **상충**한다는 이슈(#141/#142) 존재 → **가중치 상업 사용 전 해당 파일 반드시 확인**.
- **기능**: 11종 레이아웃 카테고리, 표 HTML, 수식 LaTeX, 다국어("거의 모든 문자"/100+ 언어 주장). 출력 JSON/Markdown/HTML/(dots.mocr는 SVG).
- **벤치**: 원본 OmniDocBench Text edit 0.032/0.066, olmOCR-Bench **79.1**; dots.mocr olmOCR-Bench **83.9**(신 SOTA 주장, OCR Arena Elo에서는 Gemini 3 Pro에 이어 2위).

### 2.4 MonkeyOCR (HUST)
- **성격**: **SRR(Structure-Recognition-Relation) 삼원** 패러다임. 변형 1.2B/3B.
- **라이선스(주의·분리)**: **코드 Apache-2.0**, **가중치 비상업/연구 전용**(상업은 저자 문의).
- **기능**: 레이아웃(DocLayout-YOLO)·텍스트·수식 LaTeX·표·읽기순서. **영어+중국어만**(필기·번체·촬영문서 제약).
- **벤치**: OmniDocBench end-to-end MonkeyOCR-pro-3B ~0.138(EN)/0.206(ZH), OmniDocBench v1.6 **~88.57**; olmOCR-Bench pro-3B **75.8** / pro-1.2B 71.8. GPT-4o·Gemini 2.5-Pro 상회 주장.
- **호스팅**: 셀프호스트, 양자화 시 ~8GB VRAM(RTX 4060)도 가능.

### 2.5 olmOCR (AllenAI / Ai2)
- **성격**: 7B VLM(**Qwen2.5-VL-7B-Instruct** 파인튜닝 + GRPO/RLVR "유닛테스트 보상"). LLM 학습 데이터 생성용 대량 처리 지향.
- **라이선스**: **코드·가중치 모두 Apache-2.0**(베이스 Qwen2.5-VL도 Apache라 제약 전파 없음) — **완전 오픈**.
- **기능**: 수식·표·필기·다단 읽기순서·헤더/푸터 자동 제거. 출력 Markdown / Dolma JSON. 86개 언어 베이스 역량이나 평가는 영어 중심.
- **벤치**: 자체 운영 **olmOCR-Bench v0.4.0 = 82.4**(상위권).
- **호스팅**: 셀프호스트, GPU ~12GB+ 필요(4090/L40S/A100/H100).

### 2.6 DeepSeek-OCR
- **성격**: "Contexts Optical Compression" — 텍스트를 이미지로 렌더해 소수 vision token으로 압축. DeepEncoder ~380M(SAM-base 80M + CLIP-large 300M) + **DeepSeek-3B-MoE(활성 ~570M)**.
- **라이선스**: **코드·가중치 MIT**(상업 OK). *후속 DeepSeek-OCR-2는 별개로 취급*.
- **기능**: 문서→Markdown, 레이아웃 보존·그라운딩·도형 파싱, 표 HTML, ~100개 언어(학습 코퍼스). 해상도 모드 Tiny~Gundam.
- **벤치**: OmniDocBench에서 **100 vision token으로 GOT-OCR2.0(256토큰) 상회**, <800토큰으로 MinerU2.0(6000+토큰) 상회 주장. olmOCR-Bench 75.7. 압축비 <10×에서 정밀도 ~97%, 20×에서 ~60%.
- **호스팅**: GPU 필요(A100에서 ~20만 페이지/일), vLLM/Transformers 셀프호스트.

### 2.7 GOT-OCR 2.0 (UCAS / StepFun)
- **성격**: "OCR-2.0" 통합 엔드투엔드 ~**580M**(고압축 인코더 + 장문 Qwen 디코더). 텍스트·수식·분자식·표·차트·악보·도형을 단일 모델로.
- **라이선스(주의·모순)**: 코드 Apache-2.0 배지·HF 가중치 Apache-2.0이나, **데이터 CC-BY-NC 4.0**이고 저장소 고지에 "research use only / Vary 라이선스 준수" 문구 → **사실상 연구용으로 보수적 해석 권장**.
- **기능**: 영어+중국어, 영역(박스/색) 지정 OCR, 멀티페이지/멀티크롭. 출력 텍스트/Markdown/LaTeX/TikZ/SMILES/Kern/HTML.
- **벤치**: OmniDocBench 베이스라인(공식 종합치 미확정), olmOCR-Bench **48.3**(2차출처).

### 2.8 Nougat (Meta)
- **성격**: 과학논문 특화 Donut형(Swin 인코더 + mBART 디코더). small ~250M / base ~350M. 2023-08, 사실상 유지보수 중단.
- **라이선스(주의)**: **코드 MIT, 가중치 CC-BY-NC(비상업)**.
- **기능**: LaTeX 수식·표 강점, 읽기순서 암묵 처리. **영어 중심**, 중국어/러시아어/일본어 **미지원**. 출력 `.mmd`(Mathpix Markdown 호환).
- **벤치**: OmniDocBench에서 깨끗한 학술문서엔 강하나 실세계 스캔/다국어엔 취약(편집거리 ~0.452, *2차출처*).

### 2.9 SmolDocling-256M / Granite-Docling-258M (IBM + HF)
- **성격**: Docling의 전용 단일 VLM. **SmolDocling-256M**(실험판, 2025-03, SmolVLM 기반)의 후속이 **Granite-Docling-258M**(2025-09, Idefics3 구조에 비전 SigLIP2 + **Granite-165M** LLM).
- **라이선스**: **Granite-Docling 가중치 Apache-2.0**, Docling 코드 MIT. SmolDocling 가중치는 HF 메타데이터상 **CDLA-Permissive-2.0**(commercial-friendly, Apache 아님 — 2차출처의 "Apache" 표기는 오류).
- **기능**: 레이아웃·표(TEDS 0.97)·수식 LaTeX(인라인/블록)·**코드(F1 0.988)**·차트·읽기순서. 출력 **DocTags** → Markdown/HTML/JSON. 영어 중심 + 일/중/아랍어 실험적.
- **호스팅**: 매우 경량, CPU/Apple Silicon(MLX)/GGUF/Ollama/vLLM. A100 vLLM ~0.35초/페이지.

### 2.10 Mistral OCR (상용 API)
- **성격**: 프로프라이어터리 API. 25.03(2025-03) → OCR 2(2505) → **OCR 3(2512)**. 모델 크기 비공개.
- **라이선스/접근**: **API 전용**(엔터프라이즈 온프레미스만 선택 제공). Azure AI Foundry·Vertex AI 경유 가능.
- **기능**: 복잡 레이아웃·수식 LaTeX·이미지 인터리브·다국어. 출력 Markdown(표는 MD/HTML 선택)/JSON.
- **가격**: ~$1/1000페이지(배치 시 할인). OCR 3는 $2/1000(배치 $1).
- **벤치**: 자체 보고 ~94.9% 정확도, OmniDocBench v1.6 **85.66** / olmOCR-Bench **72.0**(외부 집계). *표준 공개 종합치는 벤더가 직접 공표하지 않음*.

| 모델 | 운영 | 파라미터 | 코드 LIC | 가중치 LIC | 호스팅 | 대표 벤치 |
|---|---|---|---|---|---|---|
| Marker | Datalab | 파이프라인(Surya 0.65B) | GPL-3.0 | **RAIL-M($2M)** | 셀프+API | OmniDoc 78.44 / olm 76.1 |
| PaddleOCR-VL | Baidu | 0.9B | Apache-2.0 | Apache-2.0* | 셀프 | OmniDoc ~94.9(1.5) / olm 80.0 |
| dots.ocr | RedNote | ~3B(1.7B+1.2B) | MIT | **분쟁/별도 협약** | 셀프 | OmniDoc 90.77 / olm 79.1 |
| MonkeyOCR-pro | HUST | 1.2B/3B | Apache-2.0 | **비상업** | 셀프 | OmniDoc 88.57 / olm 75.8 |
| olmOCR 2 | Ai2 | 7B | Apache-2.0 | Apache-2.0 | 셀프(≥12GB) | olm **82.4** |
| DeepSeek-OCR | DeepSeek | 3B-MoE(570M활성) | MIT | MIT | 셀프 | OmniDoc SOTA주장 / olm 75.7 |
| GOT-OCR 2.0 | UCAS/StepFun | ~580M | Apache(배지) | Apache(데이터 NC) | 셀프 | olm 48.3 |
| Nougat | Meta | ~350M | MIT | **CC-BY-NC** | 셀프 | 학술 특화 |
| Granite-Docling | IBM | 258M | MIT(Docling) | Apache-2.0 | 셀프(초경량) | 자체표 우수 |
| Mistral OCR | Mistral | 비공개 | 독점 | 독점(API) | API | OmniDoc 85.66 / olm 72.0 |

\* HF 카드 직접 확인 환경 제약으로 미검증, 생태계 기준 Apache-2.0.

---

## 3. 파이프라인 / 레이아웃 분석 라이브러리

### 3.1 Unstructured (Unstructured.io)
- **라이선스**: **Apache-2.0**(단, `ultralytics` AGPL 등 **copyleft 전이 의존성** 이슈 #3894 — 엄격 컴플라이언스 시 의존성 트리 점검 필요). OSS 라이브러리 + 유료 **Platform** SaaS 이원화.
- **기능**: 40+ 입력 포맷을 typed element로 partition, 레이아웃/표/OCR(Tesseract)/청킹. 수식은 약함. RAG 전처리에 강점.
- **출력**: element 객체 → JSON. ★ ~15k.

### 3.2 PaddleOCR / PP-StructureV3 (Baidu)
- **라이선스**: **Apache-2.0(클린)**. 버전 3.7.0(2026-06, PP-OCRv6).
- **기능**: 레이아웃(PP-DocLayout)·OCR(100+ 언어)·표(PP-TableMagic)·**수식(PP-FormulaNet)**·**차트(PP-Chart2Table)**·인장·읽기순서 — 모두 1급 기능. 출력 Markdown/JSON(+DOCX).
- **벤치**: 영문 edit distance 0.145로 MinerU 등 상회 주장(*벤더 보고*). ★ ~82k(본 조사 최다).

### 3.3 Surya (Datalab)
- **라이선스**: 코드 Apache-2.0, **가중치 modified OpenRAIL-M($5M 상한)**. Surya OCR 2 ~650M(Qwen식 VLM).
- **기능**: OCR·레이아웃·읽기순서·표 인식 **90+ 언어**. olmOCR-Bench ~83.3(3B 미만 최상위, *벤더 보고*). Marker의 엔진.

### 3.4 LayoutParser
- **라이선스**: **Apache-2.0**(독립 학술 프로젝트). Detectron2 기반 레이아웃 검출(PubLayNet 등) + OCR 연동. 레이아웃 중심이라 표/수식은 하위 모델 필요. 출력 레이아웃 객체/JSON.

---

## 4. 전통 라이브러리 (저수준·표/텍스트 추출·OCR 베이스)

| 라이브러리 | 운영 | 라이선스 | 핵심 용도 | 비고 |
|---|---|---|---|---|
| **PyMuPDF / PyMuPDF4LLM** | Artifex | **AGPL-3.0 + 상용 이중** | 고속 텍스트/표/이미지 추출, MD/JSON | 빠르지만 AGPL 주의. ★~10k |
| **pdfplumber** | jsvine | MIT | 객체 단위 텍스트/표, 디버깅 | 텍스트 PDF 전용, OCR 없음 |
| **Camelot** | camelot-dev | MIT | 표 추출(Lattice/Stream) | DataFrame/CSV/JSON/Excel |
| **Tabula(-py)** | 커뮤니티 | MIT | 표 추출(Java 백엔드) | JVM 필요 |
| **GROBID** | P. Lopez 등 | Apache-2.0 | 학술 PDF → **TEI XML** | 인용/메타데이터/구조 강점 |
| **Tesseract** | 커뮤니티(전 Google) | Apache-2.0 | **OCR 엔진 베이스** 100+ 언어 | LSTM 기본, 레이아웃/표/수식 없음. v5.5.2. ★~75k |
| **pdf.js** | Mozilla | Apache-2.0 | 브라우저 PDF 렌더/텍스트층 | 구조 추출 아님. v6.0.x. ★~54k |

---

## 5. 상용 / 클라우드 API

| 서비스 | 벤더 | 가격(개략, *확인 필요*) | 출력 | 셀프호스트 | 특징 |
|---|---|---|---|---|---|
| **LlamaParse** | LlamaIndex | 크레딧제, 1000크레딧=$1.25; 페이지당 1~90크레딧 | Markdown/JSON | ✗ | 에이전트형 LVM 파싱, 130+ 포맷 |
| **Reducto** | Reducto | ~$0.015/페이지대, 15k 무료 | JSON/MD/HTML/CSV | 일부(VPC) | "Agentic OCR" 자가보정, bbox 근거·신뢰도 |
| **Azure AI Document Intelligence** | MS | Read/Layout ~$1.5/1k, Prebuilt ~$10/1k, 무료 ~500/월 | JSON/Markdown | 컨테이너 일부 | 프리빌트+커스텀, 수식 add-on |
| **AWS Textract** | AWS | OCR ~$1.5/1k, 폼/표 가산 | JSON | ✗ | Forms/Tables/Queries/ID/Expense |
| **Google Document AI** | Google | OCR $1.5/1k(대량 $0.6), Layout $10/1k *(공식 확인됨)* | JSON | ✗ | 프로세서형(OCR/레이아웃/도메인) |
| **Mathpix** | Mathpix | 이미지 ~$0.002, PDF ~$0.005/페이지 | LaTeX/MMD/DOCX/HTML | 엔터 온프레 | **수식/STEM 최강**, 화학 SMILES |
| **Upstage Document Parse** | Upstage | Parse ~$0.01/페이지(+Extract $0.03) | HTML/MD/JSON | 엔터 온프레 | 표 TEDS 자체 93.48, 차트→HTML |
| **Adobe PDF Extract** | Adobe | Document Transaction 과금, 무료 500/월 | JSON(+CSV/XLSX) | ✗ | 레이아웃/읽기순서/표 상용 레퍼런스 |

> 비-Google 가격은 페이지가 403으로 막혀 비교 기사·문서 스니펫 기반의 개략치입니다. 조달 전 공식 페이지에서 재확인하십시오.

---

## 6. 벤치마크

### 6.1 OmniDocBench (OpenDataLab, CVPR 2025)
- **측정**: PDF→Markdown/구조화의 엔드투엔드+요소별 품질. ~1,651페이지·10문서유형·다언어.
- **지표**: 텍스트 Normalized Edit Distance, 표 **TEDS**, 수식 **CDM**, 읽기순서 Edit Distance. v1.6는 0–100 종합치 사용.
- **주의**: **운영 주체가 MinerU와 동일(OpenDataLab)** → 자체 평가 편향 가능. 다수 점수가 저자 자가보고. 상위권이 94%+로 몰려 **포화** 지적(LlamaIndex 등).

### 6.2 olmOCR-Bench (AllenAI / Ai2)
- **측정**: ~1,403 PDF·7,000+ **이진 유닛테스트**(문자열 존재/부재, 셀 상대위치, 수식 KaTeX 렌더 일치 등). 편집거리 함정을 피하도록 설계.
- **카테고리**: ArXiv(수식)/구스캔/표/다단/헤더푸터/롱타이니텍스트/Base. "구스캔"이 전 모델 공통 최약(~33–41%).

### 6.3 통합 리더보드 (2026년 중반 스냅샷, 높을수록 우수)

| 모델 | OmniDocBench v1.6 종합 ↑ | olmOCR-Bench ↑ | 비고 |
|---|---|---|---|
| MinerU2.5-Pro (1.2B) | **95.75** | 75.2 | OmniDoc 운영사 모델 |
| GLM-OCR | 95.22 | — | 전용 VLM |
| PaddleOCR-VL-1.5 | 94.93 (1.6=96.3 주장) | 80.0 | |
| PaddleOCR-VL (0.9B) | 94.18 | 80.0 | |
| Gemini 3 Pro (범용 VLM) | 92.91 | — | 전용 VLM에 뒤짐 |
| dots.ocr (3B) | 90.77 | 79.1 (dots.mocr 83.9) | |
| MinerU2.5 (base) | 90.67 | 77.5 | |
| MonkeyOCR-pro (3B) | 88.57 | 75.8 | |
| Mistral OCR | 85.66 | 72.0 | API |
| MinerU (파이프라인) | 85.75 | — | CPU 가능 |
| Marker | 78.44 | 76.1 | |
| GOT-OCR 2.0 | (종합 미등재) | 48.3 | |
| olmOCR 2 | (주벤치 아님) | **82.4** | |
| Chandra OCR / Infinity-Parser 7B | — | 83.1 / 82.5 | 신규 강자 |

> 두 벤치는 **척도·평가철학이 달라 직접 비교 불가**. OmniDocBench 고득점이 olmOCR-Bench에서 낮을 수 있음(예: MinerU2.5). 신규 벤치 **ParseBench**(LlamaIndex+Kaggle, 169,011 규칙·에이전트 지향)에서는 LlamaParse Agentic 84.88, Gemini 3 Flash 75.05, MinerU2.5-Pro 72.78 등(*운영사 자사 제품 포함 주의*).

---

## 7. 라이선스 한눈에 — 상업적 사용 안전도

| 등급 | 라이브러리/모델 |
|---|---|
| ✅ **상업 안전(permissive)** | OpenDataLoader(Apache-2.0) · Docling(MIT+Apache) · PaddleOCR/PP-StructureV3(Apache) · PaddleOCR-VL(Apache) · olmOCR(Apache) · DeepSeek-OCR(MIT) · Granite-Docling(Apache) · Tesseract/pdf.js/LayoutParser/GROBID(Apache) · pdfplumber/Camelot/Tabula(MIT) · Unstructured(Apache, 단 전이 의존성 주의) |
| ⚠️ **조건부(상한/커스텀)** | MinerU(커스텀: MAU 1억/매출 $20M 상한) · Marker 가중치(RAIL-M $2M) · Surya 가중치(RAIL-M $5M) · PyMuPDF(AGPL 또는 상용) |
| ⛔ **비상업/연구 전용 또는 분쟁** | Nougat 가중치(CC-BY-NC) · MonkeyOCR 가중치(비상업) · GOT-OCR(데이터 CC-BY-NC + "research only" 고지) · dots.ocr 가중치(MIT vs 별도 협약 상충, 확인 요) |
| 🔒 **독점/API** | Mistral OCR · Adobe Extract · LlamaParse · Reducto · Azure DI · Textract · Google Doc AI · Mathpix · Upstage |

---

## 8. 선택 가이드 (시나리오별)

- **로컬·CPU 전용·결정론·접근성(태그드 PDF)·온프레미스 규제**: **OpenDataLoader PDF**. 저자원 + bbox + safe-by-design.
- **최고 정확도(복잡 레이아웃/표/수식, CJK)**: **MinerU2.5-Pro** 또는 **PaddleOCR-VL-1.5**(후자가 라이선스 더 깔끔). GPU 보유 시.
- **광범위 입력 포맷 + RAG 생태계 + 프로덕션 안정성**: **Docling**(+Granite-Docling). MIT/Apache로 라이선스 안전.
- **완전 오픈(데이터·RL 레시피 포함) + 대량 LLM 데이터 생성**: **olmOCR**(Apache, 7B, GPU 필요).
- **초경량·엣지/Apple Silicon**: **Granite-Docling-258M** 또는 **DeepSeek-OCR**.
- **표만/수식만 특화**: 표 = Camelot/Unstructured/PaddleOCR, 수식·STEM = **Mathpix**(상용) 또는 PaddleOCR-VL/Nougat(학술).
- **운영 부담 최소(매니지드)**: 범용 = LlamaParse/Reducto, 엔터프라이즈 컴플라이언스 = Azure DI/Textract/Google Doc AI, 수식 = Mathpix.
- **상업적 제약 회피가 최우선**: Nougat·MonkeyOCR·GOT-OCR·Marker(가중치)·dots.ocr(가중치)는 피하고, 위 ✅ 등급에서 선택.

---

## 9. 주요 주의·미검증 사항

- **벤치마크 버전 혼동 주의**: OmniDocBench는 v1.0(편집거리, 낮을수록 좋음)과 v1.5/v1.6(0–100 종합, 높을수록 좋음)의 척도가 다릅니다. 본문 종합표는 v1.6 종합치로 통일했습니다.
- **자가 평가 편향**: OmniDocBench=OpenDataLab(=MinerU), ParseBench=LlamaIndex(=LlamaParse) 등 운영사가 자사 제품을 포함합니다.
- **코드 ≠ 가중치 라이선스**: 다수 모델이 코드와 가중치 라이선스가 다릅니다. 상업 도입 전 **가중치 라이선스 원문**을 반드시 확인하십시오(특히 dots.ocr, GOT-OCR, Marker, MinerU).
- **수치 출처**: arXiv/HuggingFace/일부 벤더 페이지의 403로 인해 일부 벤치·가격은 2차출처·검색 스니펫 기반입니다(본문 *표시*). 정밀 감사 시 출처 URL을 직접 확인하십시오.
- **"odl-vl" 관련**: OpenDataLoader 공식 조직에는 "vl/vision-language" 제품이 없습니다(8개 저장소 중 없음). 본 저장소 `ysys143/odl-vl`은 사용자 프로젝트로 보이며, OpenDataLoader의 하이브리드 모드(SmolVLM 활용)와 일맥상통하나 상류 제품은 아닙니다.

---

## 10. 출처 (주요)

**기준 3종**
- OpenDataLoader: https://github.com/opendataloader-project/opendataloader-pdf · https://opendataloader.org/ · https://pdfa.org/opendataloader-pdf-v20-tops-open-source-pdf-benchmarks-in-pdf-data-loading/
- Docling: https://github.com/docling-project/docling · https://arxiv.org/abs/2408.09869 · https://huggingface.co/ibm-granite/granite-docling-258M
- MinerU: https://github.com/opendatalab/MinerU · https://arxiv.org/abs/2509.22186 · https://huggingface.co/opendatalab/MinerU2.5-Pro-2604-1.2B

**VLM 모델**
- Marker: https://github.com/datalab-to/marker · Surya: https://github.com/datalab-to/surya
- PaddleOCR-VL: https://arxiv.org/abs/2510.14528 · https://huggingface.co/PaddlePaddle/PaddleOCR-VL
- dots.ocr: https://github.com/rednote-hilab/dots.ocr · https://arxiv.org/abs/2512.02498
- MonkeyOCR: https://github.com/Yuliang-Liu/MonkeyOCR · https://arxiv.org/abs/2506.05218
- olmOCR: https://github.com/allenai/olmocr · https://arxiv.org/abs/2510.19817
- DeepSeek-OCR: https://github.com/deepseek-ai/DeepSeek-OCR · https://arxiv.org/abs/2510.18234
- GOT-OCR 2.0: https://github.com/Ucas-HaoranWei/GOT-OCR2.0 · https://arxiv.org/abs/2409.01704
- Nougat: https://github.com/facebookresearch/nougat · https://arxiv.org/abs/2308.13418
- SmolDocling/Granite-Docling: https://arxiv.org/abs/2503.11576 · https://www.ibm.com/new/announcements/granite-docling-end-to-end-document-conversion
- Mistral OCR: https://mistral.ai/news/mistral-ocr/ · https://docs.mistral.ai/capabilities/OCR/basic_ocr/

**파이프라인/전통 라이브러리**
- Unstructured: https://github.com/Unstructured-IO/unstructured
- PaddleOCR/PP-StructureV3: https://github.com/PaddlePaddle/PaddleOCR · https://arxiv.org/html/2507.05595v1
- PyMuPDF: https://github.com/pymupdf/pymupdf · pdfplumber: https://github.com/jsvine/pdfplumber
- Camelot: https://github.com/camelot-dev/camelot · GROBID: https://github.com/grobidOrg/grobid
- LayoutParser: https://github.com/Layout-Parser/layout-parser · Tesseract: https://github.com/tesseract-ocr/tesseract · pdf.js: https://github.com/mozilla/pdf.js

**상용 API**
- LlamaParse: https://developers.llamaindex.ai/llamaparse/general/pricing/ · Reducto: https://reducto.ai/
- Azure DI: https://azure.microsoft.com/en-us/pricing/details/document-intelligence/ · Textract: https://aws.amazon.com/textract/pricing/
- Google Document AI: https://cloud.google.com/document-ai/pricing · Mathpix: https://mathpix.com/pricing/api · Upstage: https://www.upstage.ai/products/document-parse · Adobe: https://developer.adobe.com/document-services/docs/overview/pdf-extract-api/

**벤치마크**
- OmniDocBench: https://github.com/opendatalab/OmniDocBench · https://arxiv.org/abs/2412.07626
- olmOCR-Bench: https://github.com/allenai/olmocr · https://huggingface.co/datasets/allenai/olmOCR-bench
- ParseBench: https://github.com/run-llama/ParseBench · https://www.llamaindex.ai/blog/parsebench
