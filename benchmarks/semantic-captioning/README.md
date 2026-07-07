# benchmarks/semantic-captioning

Semantic Captioning 계층(OCR + Captioning 융합, 요소 grounding)의 역설계 개발·검증 하네스.
설계 배경은 [`docs/.design/semantic-captioning-plan.md`](../../docs/.design/semantic-captioning-plan.md),
데이터 전략은 [`docs/.design/semantic-captioning-corpus-plan.md`](../../docs/.design/semantic-captioning-corpus-plan.md).

## 레이아웃

```
benchmarks/semantic-captioning/
  README.md          이 문서
  SOURCES.md         골든 시드 매니페스트(공개 소스·라이선스·도메인)
  fetch.py           공개 소스에서 시드 코퍼스를 재다운로드
  gt/                Phase 0 기대 출력 라벨(소형, 커밋)
  corpus/raw/        시드 원본 (gitignore — 로컬 전용, .local 미러)
  results/           평가 출력 (gitignore)
```

## 코퍼스 확보

원본 바이너리는 커밋하지 않는다(레포 정책: artifacts never committed). 재현:

```bash
python benchmarks/semantic-captioning/fetch.py --out .local/semantic-captioning/corpus/raw
python benchmarks/semantic-captioning/fetch.py --check
```

- 대용량·비공개 성격의 원본은 `.local/semantic-captioning/`(gitignore)에 상주.
- `fetch.py`는 공개 데이터셋만 받는다(라이선스는 `SOURCES.md` 참조).
- 한국어 손글씨는 공개 도메인 원고 seed를 포함한다. 현대식 한국어 필기 폼은 AI Hub 승인 또는 자체 수집 필요.
- `--check`는 원본을 쓰지 않고 PDF/이미지 매직바이트를 검증해 HTML 리다이렉트·소스 URL drift를 실패로 잡는다.

## 시드 규모 원칙

도메인당 2~3장(스켈레톤 개발·회귀 검증용 소수 정예). 대량셋은 정확도 튜닝 단계에서만.

## 도메인 (8)

`drawing`(기술 도식) · `drawing_dim`(치수 기입 도면) · `table` · `form` ·
`statistics` · `insurance`(약관) · `policy`(정책·RFP 도식) · `handwriting`(필기 폼).

상세·라이선스·알려진 갭은 `SOURCES.md`.
