# Agent-Ready Schema, Semantic Ontology, and In-Module Chunking

> 상태: 설계 제안(계약 아님). ODL-VL 파이프라인이 현재 뱉는 loss-aware `document.json` 위에,
> **바로 에이전트/RAG에 먹일 수 있는 파생 레이어**와 **런타임 주입형 문서 온톨로지**, 그리고
> **구조·의미 인지 계층 청킹**을 이 모듈 안에서 함께 산출하기 위한 설계.
> 적용 범위: `src/odl_vl/pipeline/output.py`, `structure.py`, `sections.py`, `docmeta.py`, `profile.py`가
> 이미 만든 구조 그래프를 입력으로 하는 후속 스테이지, 그리고 그 산출을 LightRAG 등 RAG/그래프 툴에
> 연결하는 통합 전략(§9)과 리포/패키지 경계(§10).
>
> 문서 지도: §1–§6 스키마·온톨로지·청킹 설계 · §7–§8 비목표/열린결정 · §9 RAG/그래프 통합 전략 ·
> §10 리포/패키지 경계 · §11 최종 스탠스 요약.

## 0. 문제 정의

현재 `document.json`은 `_write_document_json`(`output.py`)이 뱉는 **loss-aware source of truth**다.
관측된 세 가지 갭:

1. **의미 역할 태깅 부재.** `blocks[].type`은 ODL 원시 kind(`"paragraph"`, `"text block"`,
   `"list item"`, `"caption"`)를 그대로 담는다. 이는 *구조 프리미티브*지 *의미 역할*이 아니다.
   제목/소제목은 `sections[]`의 heading level로만 존재하고, **수식(formula)은 1급 타입이 없으며**,
   표지(cover)·목차(TOC)·본문(body)·참고문헌(references)·내지/판권지(colophon)·메타데이터(metadata)
   같은 **문서 역할 구분이 없다**. `frontmatter.py`는 "여백 사이드바 메타 칼럼"이라는 특수 기하 케이스만 잡는다.
2. **에이전트가 바로 못 먹는 형태.** `bbox`, `order`, `font_size`, `regions`, `caption_id` 등이 노드마다
   인라인으로 박혀 있다. LLM 컨텍스트에 그대로 넣기엔 노이즈다.
3. **문서종류 고착 위험.** 역할·구조 판단이 코드에 박히면 논문/슬라이드/계약서마다 코드를 고쳐야 한다.

### 0.1 관점 전환: bbox는 "찌꺼기"가 아니다

`bbox`/`order`/`regions`/`caption_id`는 노이즈가 아니라 **의도된 provenance**다. 재크롭(`_write_assets`),
숫자 그라운딩(`oracle.py`), 인용 하이라이트, 감사에 필요해서 소스 오브 트루스에 있는 것이다. 따라서 목표는
**"이 JSON을 청소한다"가 아니라 "이 JSON을 그대로 두고 그 위에 깨끗한 파생 레이어를 얹는다"**이다.
에이전트-레디 뷰는 소스 오브 트루스의 **projection**이며, 각 청크는 노드 id로 Layer 0에 왕복(round-trip)한다.

## 1. 3레이어 아키텍처

```
Layer 0  document.json          현재 것. loss-aware IR. bbox/order/regions 여기 삼. 소스 오브 트루스.
Layer 1  semantic overlay        신규. 모든 노드/섹션/페이지영역에 role + confidence + 판단근거 부여.
                                 온톨로지가 소유. Layer 0을 변형하지 않고 id로 참조하는 사이드카.
Layer 2  document.agent.json      신규. Layer 0의 projection. bbox 없음, role 해소됨, furniture 제거,
         + chunks.jsonl            수식 LaTeX, 표 markdown/row-serialized, 계층(parent-child) 청크.
```

원칙:

- **레이어 간 비파괴.** Layer 1/2는 Layer 0을 절대 수정하지 않는다. 노드 `id`(예: `p5_t2`)로 참조만 한다.
- **재생성 가능.** Layer 1/2는 온톨로지 + Layer 0에서 결정론적으로 재생성된다. 온톨로지 버전이 산출물에 박힌다.
- **projection == 손실 없음.** Layer 2에서 bbox를 뺀 건 "버린" 게 아니라 "안 먹인" 것. `source_refs`로 복원.

## 2. 온톨로지: 두 축을 직교시킨다

현재는 `type` 한 필드에 구조와 의미가 섞여 있다. 이를 두 직교 축으로 분리한다.

### 2.1 structural type (닫힌 집합, 코드 소유)

작고 안정적인 프리미티브. 코드가 소유하며 문서종류와 무관하다.

```
block | heading | list | list_item | table | figure | caption | equation | code
```

ODL kind → structural type 매핑은 코드 상수 하나로 관리한다(예: `"paragraph"|"text block" → block`).

### 2.2 semantic role (열린 집합, 온톨로지 소유, 런타임 주입)

역할 자체가 taxonomy(부모 role를 가짐)라서 특정 문서종류에 고착되지 않는다. 예:

```
front_matter            (부모)
  front_matter.cover            표지
  front_matter.title_block      표제부(제목/저자/소속)
  front_matter.toc              목차
  front_matter.abstract         초록
  front_matter.metadata         서지/판권 메타데이터
body                    (부모)
  body.section                  절 제목
  body.paragraph                본문 단락
  body.result_table             결과 표
  body.figure                   본문 그림
  body.equation                 수식
back_matter             (부모)
  back_matter.references         참고문헌
  back_matter.appendix           부록
  back_matter.colophon           내지/판권지
문서종류별 확장:
  slide.title_slide, slide.content, slide.speaker_notes
  paper.methods, paper.results, paper.discussion
  contract.clause, contract.signature_block, contract.schedule
```

**핵심:** 새 문서종류 지원 = 온톨로지 파일 하나 추가. **코드 변경 0.** 이것이 "실제 문서의 온톨로지를
반영하고 논문/슬라이드에 고착화되지 않는다"의 실체다.

### 2.3 온톨로지 저장 포맷: Markdown + frontmatter

`ontologies/` 레지스트리 디렉터리에 문서종류별 프로파일을 두고 버전관리한다. 사람이 읽고 문서화하기 좋으며,
각 role 아래 산문으로 정의/예외/판단근거를 남길 수 있다.

```markdown
---
profile: paper
version: 1
extends: base            # base.md의 공통 role를 상속, override 가능
roles:
  - role: back_matter.references
    parent: back_matter
    structural_type: [heading, list, list_item]
    signals:
      heading_regex: '^(references|참고문헌|bibliography|引用文献|reference list)\b'
      page_zone: last_third          # 문서 위치: first_pages | last_third | any
      after_role: body.section        # 순서 제약(선택)
    chunk_policy:
      mode: atomic_per_entry          # 참고문헌 1건 = 1청크
    confidence_floor: 0.6
  - role: front_matter.toc
    parent: front_matter
    structural_type: [heading, list, list_item]
    signals:
      heading_regex: '^(contents|table of contents|목차|目次)\b'
      page_zone: first_pages
      leader_dots: true               # '...... 12' 리더 점선 패턴
    chunk_policy: { mode: drop }       # RAG 인덱스에서 제외(항법용, 검색 대상 아님)
---

# paper 온톨로지

## back_matter.references
참고문헌 섹션. `page_zone: last_third`로 본문 내 "see References" 언급과 구분한다.
결정론 신호(heading 정규식 + 위치)로 먼저 잡고, 애매하면 VLM로 disambiguation.
...
```

### 2.4 런타임 주입 메커니즘 — 기존 SourceProfile seam 재사용

새 주입 경로를 만들지 않는다. 이미 소스별 설정을 런타임 주입하는 `SourceProfile`
(`profile.py`, `processing-tiers-and-adaptation.md` §2.5)에 필드 하나를 얹는다:

```
SourceProfile.ontology_profile: "paper" | "slide" | "contract" | ...   # 기본 "base"
```

D-1/D-2 진단이 문서종류를 추정해 프로파일을 고르거나, CLI 플래그(`--ontology paper`)로 강제한다.
온톨로지 로더는 `extends` 체인을 병합해 최종 role 집합을 만들고, 그 **버전을 산출물 메타에 박는다**
(`document.agent.json.ontology = {profile, version}`).

## 3. Role 분류 파이프라인 (Layer 1)

`build_graph`(`structure.py`) 산출 직후, `sections`/`figures`/`tables`가 확정된 뒤 실행하는 새 스테이지.

판단 순서(sections.py의 abstain-safe 패턴을 그대로 따른다):

1. **결정론 신호 우선.** 위치(page_zone), numbering class(`numbering.classify_numbering`),
   caption 정규식(`_CAP_LABEL_TITLE`), heading 텍스트 정규식, 기하(사이드바=frontmatter.metadata),
   structural type 제약. 온톨로지의 `signals`가 곧 규칙이다.
2. **VLM은 disambiguation만.** 결정론 신호가 경합하거나 confidence가 `confidence_floor` 미만일 때만
   VLM에 "이 블록의 역할은?"을 role 후보 리스트와 함께 묻는다. det_vlm 모드에서만.
3. **Unknown은 abstain.** 매칭 실패 시 structural type의 기본 role(예: block→`body.paragraph`,
   table→`body.result_table`)로 떨어뜨린다. **역할을 날조하지 않는다.**

산출(사이드카, Layer 0 비수정):

```json
// document.roles.json
{
  "ontology": { "profile": "paper", "version": 1 },
  "roles": {
    "p1_b0":  { "role": "front_matter.title_block", "confidence": 0.95, "by": "signal:page_zone+font" },
    "p5_t2":  { "role": "body.result_table",         "confidence": 0.80, "by": "signal:structural_type" },
    "sec12":  { "role": "back_matter.references",     "confidence": 0.90, "by": "signal:heading_regex" }
  }
}
```

## 4. 청킹은 이 모듈 안에서 한다

### 4.1 왜 여기서 하나

청킹 품질은 **이 모듈만 가진 신호**에 달려 있다. 다운스트림 RAG 청커가 markdown만 받으면 아래를 전부
버리고 다시 추측한다:

- reading order (`pages[].content` 스트림)
- 섹션 계층 (`build_sections`의 parent-child 트리)
- 표/그림/수식의 atomic 경계, 페이지 걸친 표 stitching (`table_chains`)
- cross-refs (`_resolve_cross_references`의 `refs` 엣지)
- furniture 제거 (`strip_page_furniture`), chart-내부 노이즈 (`_chart_internal_noise`)

특히 `build_sections`가 이미 parent-child 트리를 만들므로 **계층/부모-자식 청킹이 거의 공짜**다.

### 4.2 별도 opt-in 스테이지

`write_outputs`에 새 산출을 붙인다. 기본 off, `--chunks` 또는 프로파일 지정 시 on.

- **부모 청크 = 섹션.** heading breadcrumb(`heading_path`) 보유.
- **자식 청크 = 섹션 prose의 토큰 상한 분할** + **표/그림/수식은 1청크 1원자**(절대 분할 금지).
- **청크 정책은 코드가 아니라 온톨로지가 결정.** role → `{atomic | prose_split | drop}` + `target_tokens`
  + `overlap`. 슬라이드는 페이지당, 논문은 소절당, 계약서는 조항당 — 주입된 온톨로지가 결정한다.
- prose 분할은 문장 경계 존중, overlap은 prose에만(표/그림/수식은 원자라 overlap 없음).

### 4.3 chunks.jsonl 스키마

```json
{
  "id": "c0007",
  "parent_id": "c0003",
  "doc_id": "a1b2c3d4e5f60718",
  "structural_type": "table",
  "role": "body.result_table",
  "heading_path": ["3. Results", "3.2 Ablation"],
  "text": "| model | acc |\n|---|---|\n| base | 0.71 |\n…",
  "token_count": 180,
  "atomic": true,
  "source_refs": { "nodes": ["p5_t2"], "pages": [5, 6] },
  "refs": ["p4_b3"],
  "meta": { "n_rows": 12, "n_cols": 3, "continued": true, "arithmetic_ok": true }
}
```

- `source_refs`가 Layer 0으로의 왕복 경로다: 인용 하이라이트·재크롭·bbox 그라운딩에 사용.
- `role`/`heading_path`가 구조·의미 인지 검색(메타데이터 필터, 계층 확장 검색)을 가능케 한다.
- `drop` 정책 role(TOC, running header)은 chunks.jsonl에 아예 안 나온다 → 인덱스 오염 방지.

## 5. Layer 2 문서 뷰 (document.agent.json)

청크와 별개로, 문서 전체를 깨끗한 트리로 원하는 소비자를 위한 뷰. bbox 없음, role 해소됨,
수식 LaTeX, 표 markdown, furniture 제거. 섹션 트리를 그대로 따르되 각 노드에 clean text + role만 남긴다.
청크가 필요 없는 요약/전체읽기 에이전트용.

## 6. 스테이지 배치 (구현 시)

```
build_graph (기존)
  → classify_roles(graph, ontology)        # 신규: Layer 1 → document.roles.json
  → project_agent_view(graph, roles)       # 신규: Layer 2 → document.agent.json
  → chunk(graph, roles, ontology)          # 신규: chunks.jsonl (opt-in)
```

- 전부 Layer 0(`document.json`) 산출 이후. 기존 markdown/ledger/tables 경로 무변경.
- 온톨로지 로더(`ontology.py`) + 분류기(`roles.py`) + 청커(`chunking.py`)는 순수 함수, 결정론.
  VLM disambiguation은 주입 콜백으로만(테스트에서 stub).

## 7. 비목표 / 유의

- Layer 0 스키마는 **바꾸지 않는다.** 하위호환 유지. 신규 산출만 추가.
- 온톨로지가 없거나(`base`만) role 신호가 약하면 **generic role로 abstain** — 품질 저하 없이 동작.
- 청킹 임계(target_tokens 등)는 골든셋으로 보정 대상(`pdf-pipeline-requirements.md` §8과 동일 원칙).
- 문서종류 자동 추정 정확도는 별도 검증 항목(D-1 확장).

## 8. 열린 결정 사항

1. ~~토크나이저 기준~~ → **해소(§9.5).** 청크 `token_count`는 **소비자 토크나이저에 정렬**한다(LightRAG 기본 tiktoken/`cl100k_base`). 온톨로지 프로파일의 `tokenizer` 필드로 명시. 불일치 시 소비자 재카운트에 맡긴다.
2. `document.agent.json`(문서 뷰)과 `chunks.jsonl`(검색 단위) 중 우선 구현 순서.
3. VLM disambiguation을 role 분류에 어느 선까지 허용할지(비용 vs 정확도) — 기본은 결정론-only.
4. 온톨로지 `base.md`의 공통 role 최소 집합 확정.
5. **(§9.6)** LightRAG에 "extract-only 반환" 공개 API가 실제로 없는지 구현 시 실측. 있으면 정식 extractor-plug로 승격 가능(현 공개 표면 기준으론 없음, delegate/read-back만).
6. **(§9.5)** Mode 1 기본 옵션을 `1c(hint)`로 둘지 확정 — degrade-safe하나 원자성 미보장.

## 9. RAG / 그래프 통합 전략

> 이 절은 ODL-VL을 LightRAG를 비롯한 RAG/그래프 구축 툴과 통합하는 방식의 계약이다. 핵심 원칙:
> **파싱·청킹(Stage 1)과 그래프 구축(Stage 2)을 분리하고, 특정 RAG에 종속되지 않는 중립 기재(substrate)로
> 남으며, 남의 extractor를 wrap하지 말고 delegate한다.** 근거는 §9.1~§9.9.

### 9.1 두 통합 접점

LightRAG(및 유사 툴)와의 접점은 둘이다.

1. **업스트림(파서) 접점 — LightRAG RFC #3197 (`BaseExternalParser`).** LightRAG는 OCR/VLM 파서를
   `async parse_file() -> IRDoc` + `cache_valid()` 프로토콜로 플러그인화하려 한다(PaddleOCR-VL/DeepSeek-OCR/
   Mistral OCR 등). ODL-VL은 이 타깃군에 그대로 든다. **이점**: 사용자가 ODL-VL을 파서로 바로 선택.
   **함정**: IRDoc 뒤에서 LightRAG가 자기 청커로 재청킹 → 우리 구조·의미 청킹이 버려진다.
   → **정책: 추적하되 지금 구축하지 않는다(RFC, 미머지).** 안정화되면 lean core에만 의존하는 어댑터로 구현.
2. **다운스트림(인제스트) 접점.** 아래 §9.2의 세 경로.

### 9.2 LightRAG 인제스트 3경로 (A / B / C)

| 경로 | 청킹 | 엔티티 추출 | 우리 부담 | 커플링 |
|---|---|---|---|---|
| **A. `ainsert()` 기본** | LightRAG(token-size) | LightRAG(LLM) | 없음(청킹 손실) | 공개 API |
| **B. `ainsert()`+`chunking_func`** | 우리 | LightRAG(LLM) | 어댑터 | **내부 시그니처 커플링** |
| **C. `ainsert_custom_kg()`** | 우리 | **직접 해야 함** | entity+relationship 전부 | 공개 API(불안정) |

- `chunking_func`는 교체 가능 속성이고, `ainsert()`는 `chunking_func` 호출 뒤 `_process_extract_entities`로
  **LLM 추출을 자동 수행**한다. 즉 B는 "우리 청킹 + 그들 추출"이 한 콜에 된다.
- **`ainsert_custom_kg()`는 LLM 추출을 전혀 하지 않는다.** 준 chunks/entities/relationships를 각 벡터스토어에
  임베딩·업서트만 한다. `entities:[]`로 넘기면 **청크는 들어가나 KG는 안 생긴다** → LightRAG의 핵심(graph 검색)을
  버리는 셈. 그래프를 원하면 entity+relationship을 우리가 공급해야 한다.

#### `ainsert_custom_kg()` 성숙도 (C의 리스크)

작동하고 공식 예제(`example/insert_custom_kg.py`)도 있으나 **저수준·미성숙**:

- 엔티티 커스텀 속성 유실(#2101 — `acreate_entity`가 하드코딩 필드만 취함).
- 메타데이터 passthrough가 파이프라인 전 구간에서 취약(Discussion #2000/#2001 — 멀티인스턴스 cross-org bleed 우려).
- `source_id`를 청크/문서 중 무엇에 걸지 규약 미정(#1616).
- 하부 인제스트에 동시성/좀비태스크 버그(#1968), `unknown_source` 네이밍(#2764).

→ **C는 통제된 "구조 시딩" 용도로만. 메타 충실도가 필요한 주 경로로 삼지 않는다.**

### 9.3 고정 청크 스키마와 "메타 천장" (A와 B가 동일)

LightRAG 청크 저장 스키마는 **고정**이다. 레코드는 `{content, full_doc_id, tokens, chunk_order_index,
file_path}`만 유지하고, `chunks_vdb.meta_fields = {full_doc_id, content, file_path}`. **`chunking_func`가
무엇을 더 반환하든 그 외 키는 strip된다.**

- **살아남는 것**: 청크 경계 · 내용 품질(클린 텍스트·표 md·수식 LaTeX·furniture 제거) · 순서(`chunk_order_index`) ·
  **자유 문자열 1칸(`file_path`, 질의 가능)**.
- **죽는 것(구조화 필드로는)**: `role` · `heading_path`/`parent_id` · `source_refs`(→bbox) · `refs` · 표 메타 · page#.

**결정적 포인트: 이 천장은 A나 B나 같다.** 다운스트림 저장 스키마가 동일하므로 **B가 A보다 메타를 더 보존하지
못한다.** B의 유일한 실이득은 `chunking_func`가 tokenizer를 받고 async라는 것(토큰 정렬 + 델리미터 해킹 회피).
그 대가가 내부 커플링 → **정보 보존을 이유로 B를 택할 근거는 없다.**

**정보를 살리는 3기법 (경로 무관):**

1. **구조를 content에 굽는다.** heading breadcrumb + role 태그를 청크 텍스트 맨 앞에(`[Results › 3.2 Ablation]`).
   content라서 안 죽고 contextual retrieval로 검색 품질이 오른다.
2. **`file_path`를 chunk_id 조인키로.** 리치 레코드는 `chunks.jsonl` 사이드카에 두고 검색 결과에서 조인해
   role/bbox/refs 복원(인용·필터).
3. **그래프 엣지는 custom_kg(C) 별도 콜.** table→section·cross-ref 엣지는 청킹 경로로는 절대 안 들어간다.

> **성숙도 태그(§9.4–9.6).** `[확정 인터페이스]` = 검증된 LightRAG mechanics(§9.2–9.3)에 근거한 설계로,
> 지금 build 대상이자 retrieval 측정의 하네스다. `[build 유예]` = 설계는 확정하되 코드는 retrieval 정량
> 지표(§8 골든셋)가 나온 뒤로 미룬다. 유예 대상은 스키마 정교화지, 아래 인터페이스가 아니다.

### 9.4 책임 분리: Stage 1 ⟂ Stage 2  `[확정 인터페이스]`

**Stage 1(파싱·청킹, 우리)과 Stage 2(그래프 구축, 그들)를 분리한다.** 이는 옳을 뿐 아니라 생태계가 강제한다
(§9.8: 그래프 툴 4개 중 3개가 Stage 2를 통째로 소유하고 Stage 1 출력만 받는다). 또한 **그래프가 필요 없는
케이스가 많으므로**(순수 벡터검색·long-context 직접 주입·요약·번역) **Stage 1은 단독으로 가치가 완결되어야
하고, Stage 2는 opt-in**이어야 한다.

```
Stage 1 (우리, 재사용 코어)  parse + chunk → 클린 마크다운 + chunks.jsonl + roles (+선택적 graph-hints)
                            └ RAG-agnostic. 그 자체로 완결.  === Mode 1
Stage 2 (그들 or 우리)       graph 구축 — 각 툴이 자기 방식대로.  === Mode 2(우리 KG) / delegate(그들 KG)
```

### 9.5 Mode 1 — text/chunks 출력의 세 옵션  `[확정 인터페이스]`

Mode 1은 그래프 없는 RAG-agnostic 출력이다. **청크 경계를 누가 소유하나**의 스펙트럼으로 세 옵션을 구분한다.
이 세 옵션은 곧 **retrieval 측정 하네스**다 — 1a(청킹 안 함=귀무가설) vs 1c vs 1b를 A/B 해서 데이터가 default를
고르게 한다(아래 "1c 기본"은 성능 우위가 아니라 최소-커플링·degrade-safe에 근거한 공학적 default이며, 어느
옵션도 아직 최선으로 *입증*되진 않았다).

| 옵션 | 경계 소유 | 산출 | LightRAG 호출 |
|---|---|---|---|
| **1a. no chunk** | 소비자 | `document.md`(클린·합본·furniture 제거) | `ainsert(md)` |
| **1c. no chunk + hint** (기본) | 공유: 우리=원자성/안전seam, 소비자=사이징 | `document.md` + soft seam 마커 | `ainsert(md, split_by_character=SEAM, split_by_character_only=False)` |
| **1b. chunk** | 우리 | `chunks.jsonl` + 델리미터 직렬화 | `ainsert(txt, split_by_character=SENTINEL, split_by_character_only=True)` |

- **1a** — 소비자가 강한 청커 보유 / long-context 직접 주입 / 비RAG 용도. 우리 값 = 문서레벨 정제(페이지걸친
  stitching, reading order, furniture 제거), 경계 아님.
- **1c** — 우리가 "여기 자르지 마(원자 단위) / 여기가 안전한 seam"만 주고, 토큰 사이징·overlap은 소비자
  (LightRAG의 `chunk_token_size`, paragraph-semantic/semantic-vector 전략)가 소유. **LightRAG와 가장
  협조적·최소 커플링. degrade-safe**: 마커를 무시하는 소비자는 1a로 떨어지고, 쓰는 소비자는 가이드받는다.
- **1b** — 우리 구조·의미 경계를 정확히 강제. 원자 단위(표/그림/수식) 불파괴 보장.

**정직한 caveat — hint는 원자성을 보장 못 한다.** `split_by_character_only=False`면 소비자가 oversize
세그먼트를 토큰으로 재분할하므로 **거대한 표가 mid-table로 잘릴 수 있다.** 원자성 보장이 필요하면 `1b(only=True)`
이되 소비자가 사이징 통제를 잃는다(큰 청크가 임베딩 윈도우 초과 가능). **(a)원자 불파괴 + (b)소비자 사이징
소유는 우리 청크가 이미 소비자 버짓에 맞을 때만 동시 성립.** 현실 절충: prose는 미리 합리적 크기로 나눠 seam
힌트만 주고 **oversize 원자 단위만 hard-split(하이브리드).**

**메타 왕복 차이:** `1b`는 하드 경계 = 안정 chunk id → `chunks.jsonl` 사이드카 조인 깔끔. `1a/1c`는 소비자
최종 청크가 우리와 1:1이 아니므로 **section/block 레벨 사이드카**(role per 섹션·블록)를 주고 소비자가
텍스트/offset으로 매핑. 리치 메타 왕복은 `1b`가 최적.

### 9.6 Mode 2 — 우리 KG 출력 (extractor 추상화 + fusion)  `[build 유예]`

> 설계는 확정, 코드는 retrieval 지표(§8) 이후. Mode 1 인터페이스가 안정화·측정되기 전에 KG/extractor/fusion을
> 먼저 짓지 않는다(적대 리뷰의 "측정 없는 정교화 동결"이 겨눈 지점). Mode 2는 Stage 1의 `1b` 청크를 입력으로 쓴다.

Mode 2는 우리가 소유하는 KG를 산출하는 모드다. **비경쟁 조건**: (i) **portable·중립 KG IR**까지만 내고,
(ii) **retrieval/query 레이어는 만들지 않는다.** KG 아티팩트는 LightRAG 등의 *입력*이지 경쟁물이 아니다
(그래프 툴 4개 중 graphify·Understand-Anything은 애초에 "KG 아티팩트 생산자"다 — 확립된 카테고리).

**Extractor 포트:**

```
Extractor.extract(chunks, schema_hint) -> KG_IR   # 우리 중립 IR로 반환
```

- **잘 맞는 백엔드(= "그래프를 반환"이 계약인 library 모양, 안정·독립):** LangChain `LLMGraphTransformer`
  (`aconvert_to_graph_documents(docs) -> GraphDocument[]`), Microsoft GraphRAG(parquet 산출), **우리 자체
  LLM 프롬프트 추출기**. cherry-pick·조합 자유.
- **LightRAG는 여기서 안 맞는다.** 공개 표면상 추출이 `ainsert` 파이프라인 + 자기 스토어에 **용접**돼 있어
  `chunks → graph`를 **반환**하는 공개 함수가 없다. 그래서 (i) 풀 `ainsert` 후 그들 graph store에서 **read-back**
  (무겁고 store 스키마 커플링) 또는 (ii) 내부 import(불안정 추종 함정)뿐. → **LightRAG는 extractor-plug로
  감싸지 말고 delegate 타깃으로 둔다**(텍스트 먹이고 그들이 자기 그래프 소유). 굳이 LightRAG-flavor 추출을
  우리 IR로 원하면 **옵션 read-back 어댑터**로 "더 무겁고 느슨한 커플링" 명시.

**차별점 — fusion (우리가 extractor 리셀러가 아닌 이유):**

> **결정론적 문서-구조 그래프**(sections·tables·figures·cross-refs·페이지걸친표 — 우리만 가진 것) **⊕ LLM
> 의미 엔티티**(pluggable 엔진) → **하나의 provenance-grounded IR**. 모든 노드/엣지가 chunk id + bbox
> `source_ref`를 물어 인용·하이라이트로 왕복. 넷 중 누구도 결정론 구조 ⊕ 의미추출을 bbox 그라운딩으로
> 융합하지 않는다. 예: 구조 엣지는 우리 결정론 패스, 산문 엔티티는 LangChain transformer, 둘을 merge.

### 9.7 delegate-not-wrap 원칙과 upstream 추종 지속가능성

- **wrap/vendor(그들 추출 내부를 우리 안으로) = 경쟁 + 불안정 추종 → 금지.** **delegate(공개 front door로 위임)
  = 보완재 + 최소 추종 → 채택.**
- **extractor 모듈은 추종하지 않는다.** extractor는 그들의 가장 빠르게 변하는 핵심 IP다. **공개 계약만** 추종하며
  **안정성 순위 = `ainsert`(텍스트 in) > `custom_kg`(그래프 스키마 in) > 내부.** → 지속가능성에서도 **Path A(텍스트)
  > Path C(그래프 시딩).** C는 추상화도 안 되고(§9.8) 추적하기에도 가장 불안정한 표면.
- **커플링 예산**: `core(LightRAG 무지) → GraphTarget/Extractor 포트 → adapters/lightrag.py(얇음·버전 pin·
  계약 테스트·opt-in, 공개 API만)`. 업스트림 변경 → pin 올리고 계약 테스트 → 끝. `operate.py`는 절대 안 읽는다.
- **비경쟁 리트머스:** 그래프 툴 교체 시 **어댑터만** 바뀌면 보완재, **코어가** 바뀌어야 하면 경쟁재로 표류한 것.
  오직 어댑터만 바뀌도록 설계.

### 9.8 그래프 툴 추상화 범위 (capability 매트릭스)

| 툴 | 사전 구축 그래프 주입 | 스키마 주입 | 파싱↔추출 분리 | 산출/저장 |
|---|---|---|---|---|
| **LightRAG** | ✅ `ainsert_custom_kg` | 부분(entity type) | ✅ | 내장 vdb/graph |
| **neo4j llm-graph-builder** | ❌ 자체 LLM 추출 | ✅ 허용 노드/관계 라벨 | ❌ 통합 | Neo4j |
| **graphify** | ❌ 자체 추출 | ❌ | △ CLI 모듈 | graph.json/html |
| **Understand-Anything** | ❌ 자체 end-to-end | ❌ | ❌ 통합 | knowledge-graph.json |

- **넷 중 셋은 "raw 문서를 받아 자기가 추출"하는 닫힌 파이프라인** → **그래프 시딩(C)은 공통 추상화 불가**
  (주입 포트가 LightRAG 전용). graphify·Understand-Anything은 코드베이스 이해 쪽(tree-sitter)이라 문서-RAG
  그래프 빌더도 아니다.
- **추상화 지점은 그래프 층이 아니라 Stage 1 출력(문서/청크) 층.** `GraphTarget`을 **2티어**로:
  - **Tier 1 (universal)** `ingest_documents(clean_chunks|markdown, schema_hint?)` — 넷 다 구현.
  - **Tier 2 (optional)** `seed_graph(entities, relationships, chunks)` — LightRAG만(=C). 없으면 Tier 1로 degrade.
- **우리 구조 값을 툴 능력에 맞춰 3방식으로 흘린다:** ① 스키마/온톨로지 힌트(LightRAG·llm-graph-builder — 우리
  role taxonomy → "허용 노드/관계 타입") ② 사전 구축 구조 그래프 시딩(LightRAG만, C) ③ content-baking(닫힌
  툴엔 마크다운에 구조를 명시적으로 실어 추출기가 줍게).

### 9.9 포지셔닝 — 기존 OCR/VLM 엔진 대비 가치 (정직하게)

- **단일 페이지 표 TEDS·수식 OCR은 MinerU/PaddleOCR-VL이 강자.** 우리가 그걸 이긴다고 주장하지 않으며, 실제로
  그들을 provider로 소비한다.
- **우리 가치는 페이지 위 레이어**: ① 결정론-우선 + 숫자 오라클/산술/source-gate(환각 숫자 차단 — 특화 파서는
  "prompt-incapable") ② 문서레벨 구조(페이지걸친 표·섹션 계층·cross-ref·furniture/front-matter — per-page
  파서가 잃고 LightRAG flat 청커가 못 살림) ③ 구조·의미 인지 + 계층 청킹을 1급 산출로 ④ 런타임 온톨로지/도메인
  적응 ⑤ loss-aware provenance→bbox 인용 왕복.
- **포지셔닝: "더 나은 OCR"이 아니라 best-in-class OCR/VLM 위에 얹는 "구조 + 숫자무결성 + 청킹" 레이어.**
  심지어 MinerU를 우리 앞단 provider로 소비 가능(#3197 경유).
- **정직한 단서:** 이 가치는 골든셋 정량검증(`pdf-pipeline-requirements.md` §8) 전엔 "설계상 우위"지 입증된
  우위가 아니다. reading-order·TEDS·numeric accuracy·hallucination rate 실측이 선행.

## 10. 리포/패키지 경계 (Mode 2를 어디에 둘까)

**결정: 지금은 한 리포, 두 패키지 + extras. 리포 분리는 export 계약이 안정되면 그때.**

근거 — bounded context · 의존성 방향 · 스키마 churn 세 축:

- **churn(지금 분리 반대):** Mode 2 fusion은 구조 그래프(Layer 0/1)에 깊이 접근해야 하는데 그 스키마는 아직
  빠르게 변한다. 지금 리포를 쪼개면 `odl-kg`가 `odl-vl` 스키마 버전에 pin → **크로스리포 버전 댄스**, 원자적
  리팩터 불가. **미성숙한 경계의 하드 분리는 가장 아픈 실수.**
- **의존성(격리 찬성):** Mode 2는 LangChain/GraphRAG/Neo4j 드라이버/엔티티 임베딩을 끌어온다. "그래프 필요없는
  다수"가 설치하면 안 된다. 방향은 `odl-kg → odl-vl` 단방향(역방향 없음).

**구조:**

```
odl-vl (core)            parse + chunk + Mode 1.  lean deps(pypdfium2/ODL/PIL).
                         └ 안정·버전링된 "구조 export 계약" 노출.
odl-vl[kg] (subpackage)  extractor 포트 + fusion + KG IR.  무거운 deps 여기만. opt-in.
                         └ core의 공개 export만 import. core는 kg를 절대 모름(import-linter 강제).
```

- `pip install odl-vl`(가벼움) vs `pip install odl-vl[kg]`(무거움) — **extras가 리포 분리 없이 의존성 격리를 준다**
  ("지금 분리"의 최강 논거를 상쇄).
- **#3197 BaseExternalParser 플러그인도 lean core에만 의존**해야 하니 Mode 2를 core 밖에 두는 또 하나의 이유.

**두 export surface (지금 못 박아야 할 load-bearing 계약):**

- **Mode 1 소비자 → Layer 2** (chunks.jsonl / 클린 텍스트). 얕은 계약.
- **Mode 2(KG) 소비자 → Layer 0+1** (grounded 구조 그래프: blocks/sections/tables/figures/cross-refs/roles/
  source_refs). fusion엔 chunks론 부족 — 구조 그래프 필요.
- **둘 다 public·버전링.** 이 계약이 seam이며, 리포 경계든 인트라리포 import 경계든 동일하다 → 미래 분리는
  **리라이트가 아니라 packaging 작업**이 된다.

**리포 분리 트리거(충족되면 그때):** ① 구조 export 계약 안정(N 릴리스 breaking change 거의 없음 — 최우선)
② Mode 2가 자체 소비자·릴리스 케이던스 확보 ③ KG deps가 core 사용자에 실질 부담 ④ 팀/오너십·라이선스·브랜딩 분기.

## 11. 종합 — 최종 스탠스 한 장

- **레이어**: Layer 0(loss-aware IR, bbox=provenance) → Layer 1(role overlay, 온톨로지 소유) → Layer 2(agent-ready
  projection + chunks). 비파괴·재생성 가능.
- **온톨로지**: structural type(닫힘, 코드) ⟂ semantic role(열림, Markdown+frontmatter, `SourceProfile`로 런타임
  주입). 새 문서종류 = 파일 추가, 코드 0.
- **청킹**: 이 모듈에서. section 트리·reading order·원자 경계·cross-ref·furniture 제거를 살려서. opt-in.
- **통합**: Stage 1(파싱·청킹) ⟂ Stage 2(그래프). RAG-agnostic 코어 + 얇은 opt-in 어댑터.
  - **Mode 1**(그래프 없음) `[확정 인터페이스]`: `1a` no-chunk / `1c` hint(기본, degrade-safe) / `1b` chunk(원자
    보장·메타 왕복 최적). 이 3옵션 = retrieval 측정 하네스(1a=귀무가설). 지금 build 대상.
  - **Mode 2**(우리 KG) `[build 유예]`: Extractor 포트(반환형 엔진: LangChain/GraphRAG/자체) ⊕ 결정론 구조 =
    grounded KG IR. portable IR까지만, query 레이어 없음(비경쟁). 설계 확정, 코드는 §8 지표 이후.
- **build 순서**: 확정 인터페이스(§9.4–9.5) + 측정(§8 골든셋)을 먼저. role taxonomy 확장·Mode 2·리포 분리는
  측정 뒤로 유예 — "측정 없는 정교화 동결". 계약 코어(§10)는 측정의 인프라이자 seam이라 유예 대상 아님.
- **LightRAG**: delegate-not-wrap. 공개 표면(`ainsert` 텍스트 > `custom_kg` > 내부)만 추종. extractor-plug 아님(용접).
  `custom_kg`는 구조 시딩 보조로만. 메타 천장은 A/B 동일.
- **패키지**: `odl-vl` core(lean) + `odl-vl[kg]`(무거움, opt-in), 단방향 import 강제. 두 export 계약 public·버전링.
  리포 분리는 계약 안정 후.

### 참고 (LightRAG 조사 출처)

- [LightRAG #3197 — BaseExternalParser RFC](https://github.com/HKUDS/LightRAG/issues/3197)
- [LightRAG #2332 — pre-chunked ingestion](https://github.com/HKUDS/LightRAG/issues/2332) ·
  [#1616 — doc-chunk-entity 모델링](https://github.com/HKUDS/LightRAG/issues/1616) ·
  [#2101 — custom 속성 유실](https://github.com/HKUDS/LightRAG/issues/2101) ·
  [#1968 — 동시성 버그](https://github.com/HKUDS/LightRAG/issues/1968) ·
  [Discussion #2000/#2001 — 청크 메타](https://github.com/HKUDS/LightRAG/discussions/2000)
- [neo4j-labs/llm-graph-builder](https://github.com/neo4j-labs/llm-graph-builder) ·
  [safishamsi/graphify](https://github.com/safishamsi/graphify) ·
  [Egonex-AI/Understand-Anything](https://github.com/Egonex-AI/Understand-Anything)
- [문서 파서 벤치마크(MinerU/Docling/Marker)](https://www.eulerai.au/blog/doc-parser-benchmark)
