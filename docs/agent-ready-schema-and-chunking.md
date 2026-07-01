# Agent-Ready Schema, Semantic Ontology, and In-Module Chunking

> 상태: 설계 제안(계약 아님). ODL-VL 파이프라인이 현재 뱉는 loss-aware `document.json` 위에,
> **바로 에이전트/RAG에 먹일 수 있는 파생 레이어**와 **런타임 주입형 문서 온톨로지**, 그리고
> **구조·의미 인지 계층 청킹**을 이 모듈 안에서 함께 산출하기 위한 설계.
> 적용 범위: `src/odl_vl/pipeline/output.py`, `structure.py`, `sections.py`, `docmeta.py`, `profile.py`가
> 이미 만든 구조 그래프를 입력으로 하는 후속 스테이지.

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

1. 토크나이저: 청크 `token_count`를 어느 토크나이저 기준으로 셀지(모델 종속). 프로파일 필드로 뺄지.
2. `document.agent.json`(문서 뷰)과 `chunks.jsonl`(검색 단위) 중 우선 구현 순서.
3. VLM disambiguation을 role 분류에 어느 선까지 허용할지(비용 vs 정확도) — 기본은 결정론-only.
4. 온톨로지 `base.md`의 공통 role 최소 집합 확정.
