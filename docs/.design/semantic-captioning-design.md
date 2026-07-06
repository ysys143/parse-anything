# Semantic Captioning — 상세 설계 (드릴다운)

> [gap-analysis](./semantic-captioning-gap-analysis.md)의 각 FR 갭을 코드 근거 위에서 닫는 설계.
> 레버리지 순 트랜치로 진행. file:line은 조사 시점 기준(`src/parse_anything/`), 사용 전 재확인.
> 트랜치 1 = 관문(캡셔닝 정책 + value oracle 캡션 확장 + 차트 반전).

---

## 트랜치 1 — 관문: FR-3.2 · value oracle 캡션 확장 · FR-5.5

세 항목은 물려 있어 하나의 설계다. 결론: **신규 "검출기"는 없다.** pa가 이미 가진
(캡션 프롬프트 + oracle 함수 + 차트값 수집)을 **연결(wiring)**하는 작업이며, 완성되면
참조 파서가 못 하는 "**oracle로 검증된 의미 캡셔닝**"이 된다.

### 이미 존재하는 조각 (재프레이밍)

| 조각 | 위치 | 무엇을 하나 |
|---|---|---|
| 캡셔닝 프롬프트 | `cli.py:22` `_FIG_DESCRIBE_PROMPT` | "축·단위·주요 추세·핵심 값을 2~4문장으로, figure 언어로" = FR-3.2/5.5 그 자체 |
| 값 게이트 | `guards.py:38` `source_gate` | 전사 숫자 중 소스에 없는 것 → fabrication-suspect (§5-A/C) |
| 산술 검산 | `guards.py:47` `sum_residual`, `:55` `ratio_holds` | 부분합≠전체, 비율 붕괴 (§5-B) |
| 차트 내부값 수집 | `output.py:685` `_chart_internal_noise` | 벡터차트 bbox 내부 축·범례·연도·값을 bbox와 함께 수집 |

### 세 개의 단절 (문제)

1. `_FIG_DESCRIBE_PROMPT`이 **벡터차트에만** 적용(`output.py:530` `source=="vector"`) →
   raster figure·도면·스캔 도식엔 캡션 안 붙음.
2. 그 description이 **value oracle을 안 거침** → pa 자신의 figure 설명이 지금 §5-A/B/C 위험에 노출.
   `fabrication_flags`는 `markdown`(전사)에만 호출되고 `Figure.description`엔 미적용.
3. `_chart_internal_noise`가 모은 값(축·범례·수치)을 **폐기**(`_suppress_chart_noise`) →
   description을 검증할 결정적 소스 값을 스스로 버림.

### 관문 결정 (FR-3.2): F14 반전이 아니라 경로 분리

`run.py:20` F14("전사 프롬프트에서 figure 서술 금지")는 **옳다**(전사에 해설 섞이면 오염). 반전 불필요.

- **전사 경로**: `[figure]` placeholder 유지 (F14 존중).
- **캡션 경로(별도)**: `_FIG_DESCRIBE_PROMPT`를 **모든 content figure로 확장**, 산출 description을
  **oracle 게이팅 후** `Figure.description`에 저장.

즉 "정책 반전"이 아니라 **"전사 ⊥ 캡션 분리 + 캡션에 oracle 부착"**. pa 철학("값 안 지어냄")을
깨지 않고 FR-3.2를 켜는 유일한 방법.

### value oracle 캡션 확장 (핵심)

`fabrication_flags(markdown, source_values, min_value=)`를 description에 재사용. 관건은 source set 구성:

```
description numbers ──source_gate──▶ flagged? ──▶ escalate/재생성
        ▲
   source set =
     [텍스트레이어 숫자  deterministic.number_tokens]
   + [_chart_internal_noise가 수집한 축·범례·값]   ← 지금 버리는 그 값
   + [단위 토큰(천/만/%/원/명 …) 정규화]           ← §5-A 전용
```

- **§5-A(단위 오독)**: source set에 축 단위 토큰 포함, description이 raw 숫자에 붙인 단위를 축 단위와 대조.
  불일치 시 flag. (참조 파서 "51,685명" 류 오류를 여기서 포착.)
- **§5-B(산술)**: 차트/표 부분값에 `sum_residual` 적용(함수 기존), description 인용 합계와 대조.
- **§5-C(엔티티)**: 고유명사·식별자는 description에서 VLM 생성 금지, `_chart_internal_noise`/OCR 토큰을
  그대로 인용하도록 프롬프트 제약 + 사후 대조.

난이도 **중**: 신규 검출기 불필요, `guards`/`oracle` 함수를 description에 호출하는 배선 + source set 구성.

### FR-5.5 반전: 폐기 → 구조화 (최저비용 고효과)

`_chart_internal_noise`(`output.py:685-699`)는 이미 벡터차트 bbox 내부 ODL paragraph를 순회하며
캡션/출처가 아닌 것(축·범례·연도·값)을 `p.bbox`+`p.text`와 함께 골라낸다. 지금은 `set[str]`로 만들어
`_suppress_chart_noise`가 prose에서 삭제만 한다. 반전:

```
_chart_internal_noise → (1) prose suppress (현행 유지)
                      → (2) 구조화 추출(신규): Figure.chart_data = {
                             axis_labels[], legend[], series/values[]  ← p.text + p.bbox
                             unit_tokens[]                             ← 정규식
                           }
                      → (3) oracle source set으로 재사용
```

- 버리는 대신 `Figure`에 구조화 필드로 부착 → FR-5.5(축·수치·추세) 달성.
- prose 억제는 유지(embedding 오염 방지) — 삭제와 구조화는 배타적이지 않음.
- 이 구조화 값이 캡션 oracle의 소스 → FR-3.2 검증과 한 몸.

난이도 **중**: 수집·bbox 로직 재사용. 의존: `Figure` 계약에 `chart_data` 필드 추가(`contracts.py:161` 근방),
grounding id-graph에 bbox 이미 있어 좌표 연결 무료.

### 트랜치 1 요약

| 항목 | 실제 작업 성격 | 난이도 | 재사용 |
|---|---|:--:|---|
| FR-3.2 | 전사/캡션 경로 분리 + describe를 content figure 전체로 확장 | 중 | `_FIG_DESCRIBE_PROMPT` |
| oracle 캡션 확장 | `source_gate`/`sum_residual`을 description에 배선 + source set | 중 | `guards.py`/`oracle.py` |
| FR-5.5 | `_chart_internal_noise` 수집물 폐기→구조화(+prose 억제 유지) | 중 | 수집·bbox 로직 |

### 검증 (골든셋 연계)
- `statistics/`(kostat 통계): 단위(천 명) source set 대조로 §5-A 재현 테스트.
- `drawing_dim/`(schneckenwelle): 치수 값 인용 정합(트랜치 2 치수 검출과 결합).
- 회귀: description numbers ⊆ source set 불변식을 Phase 9 하네스에 추가.

---

<!-- 트랜치 2 (그린필드 검출기) 이어서 추가 예정 -->
