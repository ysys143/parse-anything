# 설계 노트: veraPDF/ODL 엔진을 유지하며 Rust·Python으로 개발하기

> 상태: 아이디어/설계 검토 (구현 전)
> 작성일: 2026-06-16
> 배경: `docs/pdf-parsing-libraries-research.md` 부록 D(ODL 내부 해부)의 후속.
> 동기: ODL/veraPDF의 **결정론적 구조 추출 + 접근성(태그드 PDF)** 강점은 유지하되, **개발 언어는 Java가 아닌 Rust(우선) 또는 Python**으로 가져가고 싶다.

---

## 1. 문제 정의

ODL은 두 층으로 구성된다.

- **얇은 앱 로직 (ODL 자체, ~140 클래스)**: triage(AI 필요여부 판단), XY-Cut++ 읽기순서, 태깅, JSON/MD/HTML 직렬화, 하이브리드 백엔드 클라이언트.
- **두꺼운 토대 (veraPDF, 수천 클래스, 100% Java)**: 표준급 PDF 파서 + COS/PD 모델 + `wcag.algorithms`(콘텐츠 청크·의미구조·표 검출) + PDF/A·PDF/UA 검증.

결정론 지능의 대부분이 veraPDF에 있고 강한 Java 결합이다. 따라서 **전체 포팅은 비현실적**(veraPDF 재구현 = 수년). 목표는 "포팅"이 아니라 **"엔진은 빌려 쓰고 앱은 원하는 언어로 짠다"**.

핵심 결합점은 Docling이 아니라 **veraPDF `IObject` 스키마**다(부록 D.5). 어떤 경로든 이 스키마(또는 ODL이 내보내는 JSON)와의 변환이 계약이 된다.

---

## 2. 먼저 가를 것: veraPDF에서 "무엇"을 쓸 것인가

| 쓰려는 기능 | 접근 |
|---|---|
| **검증(PDF/A·PDF/UA)** | veraPDF의 **공식 CLI/공개 API** 사용 (잘 정의됨) |
| **구조 추출**(TextChunk·SemanticTable·읽기구조 = ODL이 쓰는 부분) | veraPDF 내부 API(`wcag.algorithms`)는 추출용으로 다듬어져 있지 않음 → **이미 깔끔한 JSON으로 감싼 ODL을 호출**하는 게 실용적 |

> 결론: 실무에서 "veraPDF를 Rust/Py에서 쓴다" ≈ "ODL(=veraPDF 내장)을 Rust/Py에서 쓴다". ODL JSON(요소 타입 + bbox + PDF/UA 태그)이 사실상의 추출 API다.

---

## 3. 연동 옵션 (JVM은 어딘가엔 있어야 함 — 단 native-image로 제거 가능)

| 방식 | Python | Rust | 장점 | 단점 |
|---|---|---|---|---|
| **CLI 서브프로세스** | `subprocess` | `std::process::Command` | 단순·견고, 격리 | JRE 필요, JVM 워밍업 비용/호출 |
| **인프로세스 JVM 브리지** | **JPype**(권장)/Py4J | **j4rs**(권장)/`jni` | Java 객체·메서드 직접 호출, 메모리 공유, per-call 오버헤드 없음 | JRE 동거, 내부 API 결합(불안정) |
| **GraalVM 폴리글랏** | GraalPy | (해당 없음) | 단일 런타임 무경계 Java 호출 | 런타임 전환 비용 |
| **native-image (JVM 제거)** | `ctypes`/`cffi` → `.so` | **FFI(C ABI)** → `.so`/바이너리 | **JRE 설치 불필요**, 단일 네이티브 산출물 | veraPDF 리플렉션 → native-image 설정 필요(빌드 비용) |
| **사이드카 서비스(HTTP/gRPC)** | requests/httpx | reqwest/tonic | 언어 격리 최상, 운영 깔끔 | 서비스 1개 운영, 네트워크 경계 |

---

## 4. Rust 우선 경로 (권장)

Rust로 가는 길은 세 갈래이며, 목적에 따라 고른다.

### 4-A. 순수 Rust로 결정론 추출만 필요 → **pdf-inspector 채택/포크** (Java 완전 배제)
- firecrawl/pdf-inspector(Rust, MIT, 단일 의존성 `lopdf`)는 **ODL의 결정론 코어를 이미 Rust로 재구현**했다: XY-Cut++ 읽기순서·폰트 희소성 제목·표 이중검출. (코드 주석에 "inspired by opendataloader" 명시, opendataloader-bench 0.78 vs ODL 0.84.)
- 즉 **포팅할 필요 없음** — 이 위에 ODL식 **triage 게이트**(복잡도→백엔드)와 **VLM 라우팅**을 얹으면 "Java 제로"의 ODL스러운 파이프라인이 된다.
- **포기하는 것**: veraPDF의 PDF/A·PDF/UA 검증, **태그드(접근성) PDF 생성**, 표준급 파싱 견고성.

### 4-B. veraPDF/ODL 엔진을 Rust에서 호출 → **j4rs(인프로세스) 또는 CLI 서브프로세스**
- 접근성·검증·표준 견고성이 꼭 필요하면 ODL JAR을 그대로 엔진으로 둔다.
- `j4rs`로 JVM을 인프로세스 로드하거나, 간단히는 ODL CLI를 서브프로세스로 호출하고 **ODL JSON을 Rust 타입(serde)으로 역직렬화**.
- **JRE 의존성 존재**(개발 언어는 Rust지만 런타임에 JVM).

### 4-C. JVM 의존성까지 제거 → **GraalVM native-image + Rust FFI**
- ODL CLI(+veraPDF)를 **네이티브 `.so`/바이너리**로 빌드 → Rust에서 C ABI(FFI)로 호출.
- "Java 소스는 있으나 런타임에 JVM 없음" — 배포 깔끔. veraPDF 리플렉션용 native-image 설정이 선결 과제.

> Rust 권장 요약: **검증/접근성 불필요 → 4-A(pdf-inspector)**, **필요 → 4-C(native-image FFI) 지향, 빠른 시작은 4-B(j4rs/CLI)**.

---

## 5. Python 경로 (대안)

- **결과 JSON만 필요** → ODL의 **기존 Python 래퍼**(CLI 셸아웃). 가장 빠른 시작(이미 검증됨).
- **Java API를 직접 다루고 싶다** → **JPype**로 JAR 인프로세스 로드(veraPDF `IObject`/ODL `TriageProcessor`까지 호출).
- **순수 Python 동등 스택** → **Docling**(레이아웃+TableFormer+OCR+VLM, 순수 Py). PyMuPDF4LLM은 AGPL/상용 라이선스 영향을 명시적으로 수용할 때만 후보로 본다. 단 ODL의 접근성/태깅은 못 얻음.

---

## 6. 권장 아키텍처 (현 시점 결론)

가장 매력적인 조합:

```
[입력 PDF]
   │
   ▼
[결정론 추출 + triage 게이트]
   ├─ (A) 순수 Rust: pdf-inspector 포크   ← 접근성/검증 불필요 시
   └─ (B) ODL 엔진(native-image .so):     ← 접근성/태깅/표준 검증 필요 시
            veraPDF 파싱 + ODL 구조 JSON + triage 판정
   │
   ▼  (triage: 복잡/스캔 페이지만)
[VLM 라우팅]  PaddleOCR-VL 0.9B / MinerU2.5  (Rust에서 vLLM·HTTP 호출)
   │
   ▼
[병합·출력]  Rust에서 bbox 기준 재조립 → Markdown/JSON
```

- 개발 언어 = **Rust**(우선) 또는 Python.
- 엔진 = veraPDF/ODL는 **native-image 바이너리** 또는 **사이드카**로 격리(Java 비가시).
- 백엔드 = Docling 강결합 회피 — VLM은 교체 가능하게 HTTP 계약으로.
- 계약 = ODL JSON(또는 veraPDF IObject) ↔ 내부 타입 간 serde 매핑 1곳에 집중.

---

## 7. 다음 단계 (PoC 후보)

1. **(가벼움) Rust + ODL CLI 서브프로세스**: ODL JSON → serde 구조체 역직렬화 → triage 결과만 읽어 라우팅 분기. 가장 빠른 검증.
2. **(Java 제로) pdf-inspector 포크**: triage 신호(표/큰이미지) 추출 + JAVA/VLM 분기 레이어 추가.
3. **(JVM 제로) GraalVM native-image**: ODL CLI를 `.so`로 빌드, 리플렉션 설정 정리, Rust FFI 호출 PoC.
4. **(운영형) ODL 사이드카 + Rust 오케스트레이터**: HTTP 계약 고정.

---

## 8. 리스크 / 미해결

- veraPDF의 **구조 추출 내부 API는 비공개/불안정** → 직접 호출(JPype/j4rs)은 버전 결합 위험. ODL JSON 계약 경유가 안전.
- **native-image + 리플렉션**: veraPDF가 model 레이어에 리플렉션 사용 → reflect-config 작성 필요(빌드 난이도 ↑).
- **태그드 PDF/접근성**은 veraPDF 없이는 사실상 대체 불가 → 이 요구가 있으면 4-A(pdf-inspector) 단독은 부적합.
- 자동 트랜스파일(Java→Rust/JS)은 유지보수 불가 코드만 산출 → 제외.

---

## 9. 참고

- ODL 내부 분석: `docs/pdf-parsing-libraries-research.md` 부록 D
- pdf-inspector: https://github.com/firecrawl/pdf-inspector
- veraPDF: https://verapdf.org · https://github.com/veraPDF
- Docling(순수 Python 대안): https://github.com/docling-project/docling
- Rust↔JVM: j4rs https://github.com/astonbitecode/j4rs · jni https://github.com/jni-rs/jni
- Python↔JVM: JPype https://github.com/jpype-project/jpype
- GraalVM native-image: https://www.graalvm.org/reference-manual/native-image/
