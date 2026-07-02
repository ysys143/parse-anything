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
- 현 버전: `odl-vl.structure` = **1.1**, `odl-vl.chunks` = **1.1**, `odl-vl.semantic` = **1.0**,
  `odl-vl.provenance` = **1.0**.
  - **v1.1 델타**(PR #3×#4 통합): `StructureExport`에 `@context`·`zones[]` 추가(additive→MINOR);
    `ChunkRecord`를 small-to-big parent/child 모델로 확장(`level/children/prev/next/is_continuation/
    display_text/embedding_text/tokenizer/node_types/zone` 추가, `text`는 legacy alias로 optional 유지).
    Layer 2 clean 투영과 그 geometry 사이드카를 위해 `SemanticView`·`Provenance`를 신규 추가.

```python
from odl_vl.export import STRUCTURE_CONTRACT, check_compatible
assert check_compatible(payload["contract"], STRUCTURE_CONTRACT)  # 같은 name + 같은 major
```

## Structure export (Layer 0+1)

`build_graph`(`pipeline/structure.py`) + `DocumentMeta.to_dict()`(`pipeline/docmeta.py`) 출력에 정합.
즉 이 계약은 새 포맷을 발명하지 않고 **현재 출력을 문서화**한다. 파이프라인은 이를
**`document.structure.json`**으로 emit한다(`StructureExport.from_dict(document.json_dict).to_dict()`).
이는 loss-aware `document.json`의 **타입드 뷰**다 — dataclass 밖 키는 여기서 드롭되지만(lossy-by-design)
원본 `document.json`에는 보존된다. 식별자는 `SemanticView`/`document.json`과 동일하게 **top-level에 평면**으로
펼친다(v1.1, `document` 래핑 아님).

최상위:

| 필드 | 타입 | 설명 |
|---|---|---|
| `contract` | `{name, version}` | `odl-vl.structure` / `1.1` |
| `@context` | object \| null | JSON-LD `@context`(portable IR, v1.1). 없으면 생략 |
| `document_id`, `content_sha256`, `n_pages`, `mode`, … | — | flat identity(`DocumentMeta.to_dict()`를 top-level로 펼침) |
| `ontology` | `{profile, version}` \| null | 주입된 온톨로지(§2.4). 미분류면 null |
| `pages` | `PageEntry[]` | 페이지별 reading-order id 스트림 |
| `sections` | `Section[]` | 장/절 트리(parent-child) |
| `blocks` | `Block[]` | 텍스트 노드 레지스트리 |
| `tables` | `Table[]` | 표 노드(페이지걸친 표는 1노드, `pages[]`) |
| `figures` | `Figure[]` | 그림 노드 |
| `roles` | `{node_id: RoleAssignment}` | **Layer 1 오버레이**. 비파괴(노드에 role 안 박음). 미분류면 `{}` |
| `zones` | `{zone, pages[]}[]` | zone→pages 요약(존을 top-level 축으로 승격, v1.1) |

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
> 않는 오버레이라는 §1 원칙을 계약 수준에서 강제한다. `document.json`(Layer 0)은 byte-compat을 유지하고
> (`role/zone/heading_level/odl_role` 부재), `roles`/`zones`/`@context`는 top-level에 additive로 올린다.

## Semantic view (Layer 2) + Provenance 사이드카

`document.semantic.json` — agent-clean 투영. role은 노드에 인라인되고(투영이므로 §1 위반 아님),
geometry(bbox/order/font_size/regions/cell bbox)는 제거되어 동반 `document.provenance.json`으로 강등된다.
파이프라인은 이 두 파일을 각각 `SemanticView`·`Provenance`의 `.to_dict()`로 직렬화한다(§5 producer-backed).

**`SemanticView`** (`odl-vl.semantic` / `1.0`) — 최상위는 flat identity(Layer 0과 정렬)를 펼치고 봉투 필드를 싣는다:

| 필드 | 타입 | 설명 |
|---|---|---|
| `contract` | `{name, version}` | `odl-vl.semantic` / `1.0` |
| `document_id`, `content_sha256`, `n_pages`, `mode`, … | — | flat identity(`document`에서 펼침) |
| `@context` | object \| null | JSON-LD `@context` |
| `profile` | object \| null | 주입된 온톨로지 프로파일 스탬프 |
| `metadata` | `{title, …}` | 문서 메타(제목 등) |
| `zones` | `{zone, pages[]}[]` | zone 요약 |
| `nodes` | object[] | **geometry 없는** 클린 노드(`id/type(=role)/zone/text\|latex/label/caption_ref?/…`) |
| `sections` | object[] | heading 트리(`id/heading/level/zone/heading_ref/parent/children/content`) |
| `reading_order` | id[] | 평면 reading-order 노드 id 스트림 |

**`Provenance`** (`odl-vl.provenance` / `1.0`) — geometry 사이드카. `SemanticView`/`StructureExport`와 **노드 id로 조인**:

| 필드 | 타입 | 설명 |
|---|---|---|
| `contract` | `{name, version}` | `odl-vl.provenance` / `1.0` |
| `profile` | object \| null | 온톨로지 프로파일 스탬프 |
| `prov` | `{node_id: {page?, order?, bbox?, font_size?, regions?, cell_boxes?}}` | 노드별 geometry |

## Chunk export (Layer 2)

`chunks.jsonl` — 한 줄당 하나의 `ChunkRecord`(`ChunkRecord.to_dict()` 직렬화). small-to-big: **PARENT**
청크(섹션 또는 페이지 그룹)를 인덱싱 대상 **CHILD**(token-pack, atomic은 통째)들이 채운다. child를 임베딩·검색하고
parent 섹션을 반환한다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | str | 청크 id |
| `level` | `parent\|child` | small-to-big 계층(v1.1) |
| `parent_id` | str \| null | child→부모 청크 id |
| `children` | str[] | parent→자식 청크 id들(v1.1) |
| `doc_id` | str | content-hash 문서 id |
| `structural_type` | str | `section/page`(parent) · `text/table/figure/equation`(child) |
| `zone` | str \| null | 청크 소속 zone(v1.1) |
| `role` | str \| null | 의미 역할(§2.2). `drop` 정책 role은 레코드 자체가 없음 |
| `heading_path` | str[] | 상위 heading breadcrumb |
| `display_text` | str | 화면 표시 텍스트(표=md-stub, 수식=LaTeX)(v1.1) |
| `embedding_text` | str \| null | breadcrumb 접두(§9.3)한 임베딩용 텍스트(child)(v1.1) |
| `text` | str \| null | **legacy v1.0 alias**(optional). 신규 소비자는 `display_text` 사용 |
| `token_count` | int | 모델-무관 **추정치**. fit 보장은 소비자 설정 토크나이저 기준(§9.5) |
| `tokenizer` | str \| null | 카운트에 쓴 토크나이저 이름(카운트는 토크나이저-specific)(v1.1) |
| `atomic` | bool | 표/그림/수식 = 분할 금지 단위 |
| `is_continuation` | bool | 직전 텍스트 child의 연속(오버버짓 분할)(v1.1) |
| `prev` / `next` | str \| null | reading-order leaf 링크(v1.1) |
| `source_refs` | `{nodes[], pages[]}` | **Layer 0 왕복**: 인용·bbox 그라운딩(`pages`=page span). atomic child는 `nodes[0]`가 곧 표/그림/수식 ref |
| `node_types` | str[] | 이 청크에 담긴 semantic 노드 타입들(v1.1) |
| `refs` | str[] | cross-ref로 연결된 노드 id |
| `meta` | object | 부가 메타(role별) |

## 소비자 매핑 (요약)

- **Mode 1** → Chunk export. LightRAG `ainsert`(1a/1c: 텍스트 뷰) 또는 델리미터 직렬화(1b). `role`/`bbox`는
  chunks.jsonl 사이드카로 조인(고정 청크 스키마가 이들을 strip하므로, §9.3).
- **Mode 2** → Structure export. Extractor 포트가 blocks/sections/cross-ref를 결정론 구조 엣지로 쓰고
  (fusion, §9.6), 산문 엔티티는 pluggable 엔진이 채운다. `source_refs`/노드 bbox로 KG grounding.

## 비목표

- 계약은 **직렬화 형태**를 정의하지, 생산 순서/스테이지를 정의하지 않는다(그건 §6).
- **v1.1부터 네 표면 모두 producer가 붙었다**: `output.py`가 `document.structure.json`/
  `document.semantic.json`/`document.provenance.json`/`document.chunks.jsonl`을 각각 `StructureExport`/
  `SemanticView`/`Provenance`/`ChunkRecord`의 `.to_dict()`로 직렬화한다(§5). 따라서 계약 라운드트립 테스트
  (`Contract.from_dict(read).to_dict() == read`)가 곧 emission 스키마 회귀 테스트다
  (`tests/test_export_emission.py`). `document.json`(Layer 0)은 loss-aware source of truth이므로 고정 타입
  게이트를 통과시키지 않고 hand-built로 남기며, `document.structure.json`이 그 **타입드·버전드 뷰**를 제공한다
  (원본은 무손실, 뷰는 계약-정합).
- JSON Schema 별도 배포는 후속(현재는 dataclass가 source of truth, 테스트가 스펙-코드 동기화 보증).
