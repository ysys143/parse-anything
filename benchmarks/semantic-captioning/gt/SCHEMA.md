# Golden 라벨 스키마 (Phase 0)

각 도메인 대표 샘플에 대한 **기대 출력 어서션**. 전체 전사 정답이 아니라, Semantic Captioning
파이프라인이 만족해야 할 **검증 가능한 주장**의 집합. `plan §5`의 리스크(A 단위·B 산술·C 엔티티·
G grounding·H PII)를 negative/positive 어서션으로 인코딩해 참조 파서의 결함 재발을 자동 검출한다.

원본 바이너리는 `.local/semantic-captioning/corpus/raw/`(gitignore). 라벨은 그 상대경로로 샘플을 가리킨다.

## JSON 구조

```jsonc
{
  "domain": "...",                       // 8 도메인 중 하나
  "sample": "corpus/raw/<domain>/<file>",
  "page": 8,                             // 1-indexed (이미지는 생략)
  "figure_kind": "table|chart|drawing|form|diagram|handwriting_form|photo|text",
  "elements_expected": [                 // FR-2 탐지가 찾아야 할 요소
    {"kind": "table", "note": "..."}
  ],
  "structured_expected": { /* FR-4/5 도메인 페이로드 */ },
  "caption_expected": {                  // FR-3.2 description 어서션
    "must_include": ["..."],
    "must_not_include": ["..."]          // §5 negative (단위 누락·값 조작)
  },
  "risk_checks": {                       // plan §5 방어, 기계 검증
    "A_unit": {"expected_unit": "...", "assert": "..."},
    "B_arithmetic": {"relation": "...", "assert": "sum_residual==0"},
    "C_entity": {"verbatim": ["..."], "assert": "no paraphrase"},
    "G_grounding": {"assert": "each element has bbox"},
    "H_pii": {"fields": ["..."]}
  },
  "notes": "..."
}
```

## 판정 방식 (Phase 9 하네스가 소비)
- `caption_expected.must_not_include`: description에 등장하면 실패(§5-A 단위 누락 등).
- `risk_checks.A_unit`: description 수치가 단위/스케일을 동반하는지 + `chart_data.unit`과 일치.
- `risk_checks.B_arithmetic`: `sum_residual(parts, total)==0`(guards.py 기존 함수 재사용).
- `risk_checks.C_entity`: 고유명사·식별자가 소스 토큰과 문자열 일치(paraphrase 금지).
- `structured_expected`: 파이프라인 산출 JSON과 필드 대조(존재·값).

라벨은 소수 정예(도메인당 1 샘플)로 시작. 값은 육안 확인 기반이며 근사 bbox는 생략(파이프라인 산출과
대조 시 IoU가 아니라 "요소 존재 + 값 일치"를 우선).
