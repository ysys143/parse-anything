# Export Contracts (Layer 2 chunks · Layer 0+1 structure)

> 상태: 계약 스펙. `agent-ready-schema-and-chunking.md` §10의 "두 export surface를 public·버전링으로
> 못 박기"를 구현한다. 코드의 authoritative 정의는 `src/odl_vl/export/contracts.py`이고, 이 문서는 그
> 필드/버전/안정성 정책을 기술한다. `tests/test_export_contracts.py`가 둘의 동기화를 강제한다.

## 왜 계약인가

파싱/청킹 코어와 다운스트림 소비자 사이에 **두 개의 안정·독립 버전링 surface**를 둔다. 그러면 미래의
리포 분리(`odl-vl` core ↔ `odl-vl[kg]`)가 **리라이트가 아니라 packaging 작업**이 된다(§10).

- **Structure export (Layer 0+1)** — grounded 구조 그래프. **Mode 2(우리 KG 빌더)** 와 그래프 툴이 소비.
  기존 `document.json` + Layer 1 `roles` 오버레이의 상위집합.
- **Chunk export (Layer 2)** — agent/RAG-ready 청크 레코드. **Mode 1(text/chunks)** RAG 인제스트가 소비.

## 버전·안정성 정책

- 버전은 `"MAJOR.MINOR"`. **MINOR** = 필드 추가(하위호환). **MAJOR** = 필드 제거/개명/의미 변경.
- **소비자는 미지의 필드를 무시해야 한다**(forward-compat). `from_dict`가 이를 강제한다(unknown key drop).
- **생산자는 `None` optional을 생략**한다(`document.json`의 compact 스타일과 일치).
- 모든 payload는 `contract` 태그(`{name, version}`)를 싣는다. 소비자는 `check_compatible`로 **MAJOR** 게이팅.
- 현 버전: `odl-vl.structure` = **1.0**, `odl-vl.chunks` = **1.0**.

```python
from odl_vl.export import STRUCTURE_CONTRACT, check_compatible
assert check_compatible(payload["contract"], STRUCTURE_CONTRACT)  # 같은 name + 같은 major
```

## Structure export (Layer 0+1)

`build_graph`(`pipeline/structure.py`) + `DocumentMeta.to_dict()`(`pipeline/docmeta.py`) 출력에 정합.
즉 이 계약은 새 포맷을 발명하지 않고 **현재 출력을 문서화**한다.

최상위:

| 필드 | 타입 | 설명 |
|---|---|---|
| `contract` | `{name, version}` | `odl-vl.structure` / `1.0` |
| `document` | object | `DocumentMeta.to_dict()` (identity·provenance·mode·diagnostic) |
| `ontology` | `{profile, version}` \| null | 주입된 온톨로지(§2.4). 미분류면 null |
| `pages` | `PageEntry[]` | 페이지별 reading-order id 스트림 |
| `sections` | `Section[]` | 장/절 트리(parent-child) |
| `blocks` | `Block[]` | 텍스트 노드 레지스트리 |
| `tables` | `Table[]` | 표 노드(페이지걸친 표는 1노드, `pages[]`) |
| `figures` | `Figure[]` | 그림 노드 |
| `roles` | `{node_id: RoleAssignment}` | **Layer 1 오버레이**. 비파괴(노드에 role 안 박음). 미분류면 `{}` |

노드 필수/선택 필드는 `contracts.py`의 dataclass가 authoritative:

- **Block**: `id, type, page, order, bbox, text` + 선택 `font_size, section, refs, figure`.
- **Table**: `id, type=table, pages, order, n_rows, n_cols, cells[][], regions[]` + 선택 `label, caption,
  caption_id, continued, arithmetic, views, section`. **Cell**: `text` + 선택 `bbox, row_span, col_span`.
- **Figure**: `id, type=figure, page, order, kind` + 선택 `label, caption, caption_id, bbox, file, source,
  description, section`.
- **Section**: `id, heading, level, block_id, children[], content[]` + 선택 `page, parent`.
- **PageEntry**: `page_index, page_number, mode, used_vlm, flags[]` + 선택 `page_label, markdown_file,
  content[], blocks[], tables[], figures[]`.
- **RoleAssignment**: `role, confidence, by`(`signal:… | vlm | default`).

> **주의:** `roles`는 별도 맵이다 — 노드 dict에 `role`을 인라인하지 않는다. Layer 1은 Layer 0을 수정하지
> 않는 오버레이라는 §1 원칙을 계약 수준에서 강제한다.

## Chunk export (Layer 2)

`chunks.jsonl` — 한 줄당 하나의 `ChunkRecord`. 산출물은 첫 줄에 매니페스트(계약 태그 + doc_id + ontology)를
두거나 동반 `chunks.manifest.json`으로 버전을 싣는다(구현 시 확정, §열린결정).

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | str | 청크 id |
| `parent_id` | str \| null | 부모 청크(섹션) id |
| `doc_id` | str | content-hash 문서 id |
| `structural_type` | str | `block/heading/list/table/figure/caption/equation/code` |
| `role` | str \| null | 의미 역할(§2.2). `drop` 정책 role은 레코드 자체가 없음 |
| `heading_path` | str[] | 상위 heading breadcrumb |
| `text` | str | clean 텍스트(표=md, 수식=LaTeX, furniture 제거) |
| `token_count` | int | 모델-무관 **추정치 + 토크나이저 이름 기록**. fit 보장은 소비자 설정 토크나이저 기준(§9.5). tiktoken은 목표 아님(LightRAG 기본일 뿐) |
| `atomic` | bool | 표/그림/수식 = 분할 금지 단위 |
| `source_refs` | `{nodes[], pages[]}` | **Layer 0 왕복**: 인용·bbox 그라운딩 |
| `refs` | str[] | cross-ref로 연결된 노드 id |
| `meta` | object | role별 부가(예: 표 `n_rows/continued/arithmetic_ok`) |

## 소비자 매핑 (요약)

- **Mode 1** → Chunk export. LightRAG `ainsert`(1a/1c: 텍스트 뷰) 또는 델리미터 직렬화(1b). `role`/`bbox`는
  chunks.jsonl 사이드카로 조인(고정 청크 스키마가 이들을 strip하므로, §9.3).
- **Mode 2** → Structure export. Extractor 포트가 blocks/sections/cross-ref를 결정론 구조 엣지로 쓰고
  (fusion, §9.6), 산문 엔티티는 pluggable 엔진이 채운다. `source_refs`/노드 bbox로 KG grounding.

## 비목표

- 계약은 **직렬화 형태**를 정의하지, 생산 순서/스테이지를 정의하지 않는다(그건 §6).
- 청커·role 분류기 미구현 단계에서도 계약은 유효 — `StructureExport`는 지금 출력으로 즉시 생성 가능,
  `ChunkRecord`는 타입만 확정(생산자는 후속).
- JSON Schema 별도 배포는 후속(현재는 dataclass가 source of truth, 테스트가 스펙-코드 동기화 보증).
