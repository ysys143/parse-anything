# Integration Plan — PR #3 (contract) × PR #4 (implementation)

> 상태: 실행 플랜. 같은 설계(`agent-ready-schema-and-chunking.md`)에서 갈라진 두 PR을 하나로 수렴시킨다.
> - **PR #3** (`claude/document-schema-design-0a9yc8`): 버전드 계약 레이어 `src/parse_anything/export/` — producer 없음.
> - **PR #4** (`feat/agent-ready-schema-chunking`): 파이프라인 emission — `ontology.py`, `output.py` 배선,
>   `ontology/{default,paper}.md`, `document.semantic.json`/`provenance.json`/`chunks.jsonl` 산출, 434 통과.

## 0. 원칙 — 승자독식이 아니다

두 PR은 진실을 다투지 않는다. **계약(PR #3)은 seam이고, emission(PR #4)이 그 계약 타입으로 직렬화**한다
(`agent-ready-schema-and-chunking.md` §10). 두 겹의 사실:

1. **구동은 구현(PR #4)이 한다.** 검증이 탄탄하고(434 통과, 실문서 EN/KR) 통합 전략(§9.3 `embedding_text` =
   "구조를 content에 굽기")에 더 부합한다. 계약은 *구현이 실제 뽑는 것에서 추출·진화*한다.
2. **PR #3에서 살리는 것은 세 가지뿐**: (a) 원칙 — **Layer 0 byte-compat + role 비파괴 오버레이**,
   (b) 버전 태그/전방호환 규율, (c) §10의 **2-surface(Mode 1↔Layer 2, Mode 2↔Layer 0+1) 프레이밍**.
   나머지 타입은 PR #4 현실에 맞춰 진화한다. (PR #3의 약점 = producer 없음 + Phase 1 이전 스키마 기준.)

대부분의 divergence는 **레이어를 올바로 배치하면 소멸**한다(§2, §3).

## 1. Preflight — 먼저 확인할 사실 (Step 0)

플랜 실행 전 PR #4 `output.py`에서 확인:

- **[BLOCKING] `document.json`(Layer 0)에 `role`/`zone`/`odl_role`/`heading_level`이 인라인되는가?**
  PR #4 본문은 "document.json stays byte-compatible"라 주장하나 divergence 리포트는 인라인을 관찰했다. 모순.
  - 인라인이면 → **byte-compat + 비파괴 오버레이 위반.** 그 4개를 Layer 1 overlay(`roles`/`zones`) 또는
    Layer 2(`semantic.json`)로 이동한다(§3-①, §4).
  - 아니면(별도 산출) → 위반 아님, 문서만 정정.
- `semantic.json` 노드가 `role`을 인라인으로 갖는지(정상 — Layer 2는 투영), `provenance.json`가 같은 node id로
  keying되는지(정상).
- `chunks.jsonl` 실제 필드셋(§6 이름 통일표의 근거).

## 2. 목표 최종 상태 — 파일 × 레이어 맵

```
Layer 0  document.json            원본 추출. geometry 인라인. role/zone 없음(byte-compat). 소스 오브 트루스(무손실).
Layer 0+1 document.structure.json  StructureExport 타입드 뷰: roles/zones/@context 포함, 식별자 평면. lossy-by-design.
Layer 1  roles / zones (overlay)  node id → RoleAssignment / zone. 비파괴. 온톨로지 바뀌면 재계산.
Layer 2  document.semantic.json   clean 투영: role 인라인 해소, geometry 제거, 수식 latex, 표 md.
         document.provenance.json  geometry 사이드카(같은 node id). loss-aware 유지.
Chunks   document.chunks.jsonl     parent(섹션)/child(token-pack, atomic whole) + embedding_text/prev/next.
```

계약(`src/parse_anything/export/`)은 위 각 표면을 **버전드 타입으로 덮고**, emission이 그 타입을 통해 직렬화한다
(`document.json`만은 무손실 원본이라 hand-built로 두고, 타입드 뷰는 `document.structure.json`으로 병행 emit).

## 3. Divergence 판정 → 구체 목표

**① role: overlay vs inline → 레이어별로 둘 다 유지.**
- Layer 0/1: `role`은 **별도 overlay**(PR #3 `RoleAssignment`, 비파괴). document.json 노드에 인라인 금지.
- Layer 2(`semantic.json`): overlay를 **인라인 해소**(투영이므로 위반 아님). PR #4 방식 유지.
- 조치: Layer 0에 인라인돼 있으면 제거→overlay로. `StructureExport.roles`는 그대로 계약에 유지.

**② geometry: inline vs 사이드카 → 충돌 아님, Layer 2 정교화.**
- Layer 0 document.json은 geometry 인라인 유지(`StructureExport`가 미러).
- `semantic.json`(geometry 제거) + `provenance.json`(node id keying)는 §5 Layer 2의 좋은 정교화.
- 조치: 계약에 **`SemanticView`(geometry-free) + `Provenance`(사이드카)** 타입 신규 추가(§4).

**③ top-level(@context, zones, document 래핑) → additive, 계약 v1.1로 흡수.**
- `@context`(JSON-LD)는 §9.6 "portable 중립 IR"과 부합. `zones[]`는 존을 top-level 승격.
- 조치: `StructureExport`/`SemanticView`에 `context`(@context)·`zones[]` 필드 추가(MINOR bump). identity
  래핑(`document` 키)은 현재 평면 document.json에 맞춰 정렬(계약이 평면 meta를 감싸는 형태 확정).

**④ ChunkRecord ≠ chunks.jsonl → PR #4 모델로 업그레이드.**
- PR #4 모델(parent/child level + children + prev/next + is_continuation + embedding_text/display_text +
  tokenizer)이 §4의 small-to-big·breadcrumb를 더 충실히 실현. `embedding_text`=§9.3 기법, `is_continuation`/
  `page_span`=페이지걸친 표.
- 조치: 계약 `ChunkRecord`를 이 모델로 확장. `source_refs:{nodes,pages}`는 `node_ids+page_span`을 포괄하는
  더 나은 추상이라 **이름은 계약 쪽 유지**, 값은 PR #4 데이터로 채움.

## 4. 계약 v1.1 델타 (`src/parse_anything/export/contracts.py`)

- **신규 `SemanticView`** (Layer 2, `parse-anything.semantic` 1.0): `context`(@context), `metadata`(title 등),
  `zones[]`, `nodes[]`(role 인라인·geometry 없음: id/type/role/text/latex?/caption_of?/…), `sections[]`(트리),
  `reading_order[]`. `semantic.json`의 계약.
- **신규 `Provenance`** (사이드카, `parse-anything.provenance` 1.0): `{node_id: {bbox, order, font_size, regions?,
  cell_boxes?}}`. `provenance.json`의 계약. node id로 `SemanticView`/`StructureExport`와 join.
- **`StructureExport` 확장(→1.1)**: `context`, `zones[]` 추가. `roles` overlay 유지. 나머지 하위호환.
- **`ChunkRecord` 확장(→1.1)**: `level`(parent|child), `children[]`, `prev`/`next`, `is_continuation`,
  `page_span`, `display_text`/`embedding_text`, `tokenizer` 추가. `source_refs:{nodes,pages}` 유지(=PR #4
  node_ids+page_span). `atomic`/`role`/`heading_path`/`parent_id`/`meta` 유지.
- 전방호환·compact·버전 태그·`check_compatible`는 그대로(추가 필드는 MINOR).

## 5. Emission 배선 (`src/parse_anything/pipeline/output.py`)

- output.py의 ad-hoc dict 생성 대신, `export.contracts`의 타입을 만들어 `.to_dict()`로 직렬화한다:
  - 구조 그래프 → `StructureExport(...).to_dict()` → (선택) `document.structure.json` 또는 기존 document.json 정합
  - 클린 뷰 → `SemanticView(...).to_dict()` → `document.semantic.json`
  - geometry → `Provenance(...).to_dict()` → `document.provenance.json`
  - 청크 → `[ChunkRecord(...).to_dict() for c in chunks]` → `document.chunks.jsonl`
- 효과: "producer 없는 계약" 약점 소멸, 계약이 vestigial이 아니게 됨. 계약 라운드트립 테스트가 곧 emission 스키마
  회귀 테스트가 됨.

## 6. 이름 통일 (계약 기준으로 정렬)

| 개념 | PR #3 계약(채택) | PR #4 현재 | 조치 |
|---|---|---|---|
| 청크 식별자 | `id` | `chunk_id` | `id`로 통일 |
| 구조 종류 | `structural_type` | `type` | `structural_type`(role의 `type`과 충돌 방지) |
| heading 경로 | `heading_path` | `section_path` | `heading_path` |
| Layer0 역참조 | `source_refs:{nodes,pages}` | `node_ids`+`page_span` | `source_refs`(포괄 추상) |
| 온톨로지 디렉터리 | (`ontologies/` 문서) | `ontology/` | **`ontology/`로 통일**(구현이 이미 씀), 문서 정정 |

## 7. 머지/PR 전략 (병렬 머지 금지)

병렬 머지 시 "불일치하는 두 스키마 정의 공존" → 금지.

1. **PR #4를 통합 브랜치로.** `src/parse_anything/export/`(계약)를 PR #4 브랜치로 가져온다(cherry-pick 또는 병합).
2. §4 계약 v1.1 델타 적용 + §5 emission 배선(output.py가 계약 타입으로 직렬화).
3. §3-① byte-compat 위반 수정(Layer 0에서 role/zone 제거).
4. §6 이름 통일.
5. 통합 브랜치를 검증(§8) 후 main으로. **PR #3(standalone)은 계약이 통합 브랜치로 흡수되므로 close**
   (설명에 "superseded by the integrated PR" 명시). PR #3의 설계 문서 2건은 통합 브랜치로 함께 이동.

> 대안(더 작은 단계): PR #3(순수 additive, 무위험)을 **먼저 main에 머지** → PR #4를 rebase해 `export` 타입을
> import하고 v1.1 델타+배선을 PR #4에서 수행. 계약과 구현이 별도 리뷰 단위로 남는 장점. 단 v1.1 델타가 곧바로
> 뒤따라야 계약-구현 불일치 창이 짧다. **권장: 1안(통합 브랜치)** — 창을 아예 안 만든다.

## 8. 검증 체크리스트

- [ ] Layer 0 `document.json`이 원본 대비 byte-compat(role/zone/heading_level 부재).
- [ ] `SemanticView` 노드에 geometry 키 0개, node id == `Provenance` key.
- [ ] `roles` overlay가 노드에 인라인되지 않음(PR #3 `test_roles_overlay_is_separate_from_nodes` 유지).
- [ ] 계약 라운드트립/전방호환/버전 게이팅 테스트 통과 + PR #4의 434 테스트 통과.
- [ ] emission 산출(semantic/provenance/chunks)이 계약 `.to_dict()`와 동일(스키마 회귀 테스트 추가).
- [ ] 실문서 재검(csnl EN paper / labchip KR report) — 산출 형태 불변, 존 tail 확정 유지.
- [ ] `--ontology default|paper` 스왑이 코드 변경 0으로 재태깅(주입 불변).

## 9. 열린 결정 (통합 시)

1. **[해결]** Layer 0 표면: `document.json`(loss-aware raw SoT, hand-built) **유지** + `document.structure.json`
   **신설**(`StructureExport.from_dict(doc).to_dict()`, 계약 `parse-anything.structure` 1.1). raw는 무손실로 두고
   타입드·버전드 뷰를 별도 파일로 제공(옵션 C). `StructureExport`는 식별자를 top-level로 펼치는 **평면**으로
   정렬(`SemanticView`/`document.json`과 동형).
2. **[해결→독립 유지]** `SemanticView`/`Provenance`는 **독립 버전**(각 1.0), `StructureExport`/`ChunkRecord`는
   1.1. 표면별 소비자(Mode 1↔semantic/chunks, Mode 2↔structure)의 진화 속도가 달라 독립이 seam 취지에 부합.
3. **[해결→현행 유지]** tokenizer는 tokenizer-free 추정 + 이름 기록 유지(§9.5). 실측 카운트는 소비자 요구 시
   `--tokenizer` opt-in으로 후속 도입(무거운 의존성을 lean 코어에 넣지 않음).
4. **[해결]** PR #3 처리: close(1안). PR #4 통합 브랜치가 계약을 흡수, PR #3은 "superseded by #4"로 close.
