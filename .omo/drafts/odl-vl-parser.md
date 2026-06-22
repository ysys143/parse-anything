---
slug: odl-vl-parser
status: awaiting-approval
intent: clear
pending-action: write .omo/plans/odl-vl-parser.md
approach: Plan an ODL/VLM parser bake-off that separates unmodified ODL hybrid use from an ODL fork/HybridRequest extension path.
---

# Draft: odl-vl-parser

## Components (topology ledger)
<!-- Lock the SHAPE before depth. One row per top-level component that can succeed or fail independently. -->
<!-- id | outcome (one line) | status: active|deferred | evidence path -->

| id | outcome | status | evidence path |
|---|---|---|---|
| A1 | Unmodified ODL hybrid adapter logs `page_ranges` and proves what ODL can route to a backend without code changes. | active | `docs/parsing-engine-tracks-pdf.md:14`, `docs/parsing-engine-tracks-pdf.md:60` |
| A2 | Real VLM adapter implements the best possible no-fork Track A: page render, optional adapter-side first pass, VLM call, DoclingDocument-shaped response. | active | `docs/parsing-engine-tracks-pdf.md:40`, `docs/parsing-engine-tracks-pdf.md:61` |
| A3 | ODL fork path extends `HybridRequest` to carry first-pass md and/or dynamic prompt, then maps VLM output into ODL's expected internal shape. | active | `docs/parsing-engine-tracks-pdf.md:62`, `docs/parsing-engine-tracks-pdf.md:124` |
| B1 | External orchestrator consumes ODL local JSON and owns first-pass md, prompt policy, VLM 2-pass, merge, and ledger. | active | `docs/parsing-engine-tracks-pdf.md:75`, `docs/parsing-engine-tracks-pdf.md:90` |
| IR | Shared output contract keeps A2/A3/B comparable: markdown plus JSON elements, bbox, table HTML, confidence, and ledger fields where available. | active | `docs/parsing-engine-tracks-pdf.md:26`, `docs/parsing-engine-spike-plan.md:40` |

## Open assumptions (announced defaults)
<!-- Record any default you adopt instead of asking, so the user can veto it at the gate. -->
<!-- assumption | adopted default | rationale | reversible? -->

| assumption | adopted default | rationale | reversible? |
|---|---|---|---|
| The word "Track A" is ambiguous. | Split it into A1/A2(no ODL fork) and A3(ODL fork). | The code-confirmed protocol limit applies only to the current `HybridRequest` path, not to a fork that changes that contract. | Yes |
| "Enhans-style 2-pass" means first-pass deterministic grounding plus a dynamic user/document intent prompt. | Treat both grounding and dynamic prompt as required. | Existing docs define the shared VLM contract as `(first_pass_md + page_image + intent_prompt) -> md/json`. | Yes |
| The next artifact is a plan, not implementation. | Draft should be decision-complete enough to generate `.omo/plans/odl-vl-parser.md`. | `pending-action` already points to a plan file. | Yes |

## Findings (cited - path:lines)

1. Current ODL hybrid backend calls receive the original PDF plus selected page ranges, and the request shape is `HybridRequest{ pdfBytes, pageNumbers, outputFormats }`. The backend does not receive ODL's first-pass deterministic markdown, and the request has no prompt field. Evidence: `docs/parsing-engine-tracks-pdf.md:14`, `docs/parsing-engine-tracks-pdf.md:16`.
2. Therefore, unmodified Track A via the existing hybrid adapter cannot natively implement the full Enhans-style 2-pass contract if that contract requires both first-pass md grounding and dynamic intent prompts. Evidence: `docs/parsing-engine-tracks-pdf.md:53`, `docs/parsing-engine-tracks-pdf.md:55`, `docs/parsing-engine-tracks-pdf.md:124`.
3. That does not mean "ODL can never do it." The existing design already names A3 as the path that changes ODL: extend `HybridRequest` to pass first-pass md and/or prompt, then map the result into the shape ODL can absorb. Evidence: `docs/parsing-engine-tracks-pdf.md:62`, `docs/parsing-engine-tracks-pdf.md:124`.
4. Track B naturally satisfies the full 2-pass requirement because the external orchestrator can hold ODL local output, supply dynamic prompts, run VLM, merge results, and write a full ledger. Evidence: `docs/parsing-engine-tracks-pdf.md:75`, `docs/parsing-engine-tracks-pdf.md:81`, `docs/parsing-engine-tracks-pdf.md:90`.
5. The bake-off should compare three meaningful candidates, not two: A2(no fork, adapter-side workaround), A3(fork/protocol extension), and B(external orchestration). Evidence: `docs/parsing-engine-tracks-pdf.md:128`, `docs/parsing-engine-tracks-pdf.md:136`, `docs/parsing-engine-spike-plan.md:97`.

## Decisions (with rationale)

1. Use precise language: "Track A1/A2 with unmodified ODL hybrid protocol cannot provide first-pass md or dynamic prompt to the backend." Do not write "ODL cannot do Enhans-style 2-pass" without qualification.
2. Treat A3 as a first-class candidate, not a footnote. It is the answer to the objection that a fork can change the protocol. The plan must price A3 separately: Java/ODL fork surface area, request schema change, downstream transformer change, and maintenance burden.
3. Keep B as the baseline for capability completeness. If the primary requirement is grounded, promptable 2-pass plus rich ledger, B is the simplest architecture to reason about unless A3's compactness wins enough quality/cost points.
4. Do not let A2 pretend to be the same as A3. A2 can approximate grounding only by adapter-side reparsing, and can approximate intent only through fixed adapter-level prompts.
5. The final plan should run the cheapest disambiguating experiments first: A1 logging, B1 local JSON sufficiency, then A2/A3 feasibility measurement before full VLM bake-off.

## Scope IN

- Write a plan for PDF-focused ODL/VLM parser architecture selection.
- Explicitly distinguish:
  - A1: dummy/no-fork adapter proof.
  - A2: no-fork real VLM adapter with adapter-side workarounds.
  - A3: ODL fork or patch that extends `HybridRequest` and related mapping.
  - B: external orchestrator around ODL local output.
- Include acceptance criteria for whether each candidate satisfies Enhans-style 2-pass.
- Include measurements for quality, routing accuracy, implementation cost, latency, ledger completeness, and maintenance risk.
- Preserve the code-confirmed constraints as evidence, but scope the conclusion to the current protocol.

## Scope OUT (Must NOT have)

- Must not claim that forking ODL cannot solve first-pass md or prompt delivery.
- Must not collapse A2(no fork) and A3(fork) into one Track A conclusion.
- Must not choose B solely because current ODL protocol is limited; A3 must be evaluated as a real option if Java/ODL maintenance is acceptable.
- Must not begin implementation before the plan is approved.
- Must not weaken the definition of Enhans-style 2-pass by silently dropping either first-pass grounding or dynamic prompt.

## Open questions

1. Is maintaining an ODL fork acceptable if A3 materially improves compactness or output quality?
2. Does the project require per-document/per-query dynamic prompts, or is corpus-level fixed prompting acceptable for the initial PDF slice?
3. Is Java/ODL patch maintenance a hard constraint, or only a cost to be measured?
4. What is the minimum acceptable ledger for Track A: adapter logs only, ODL logs plus adapter logs, or a normalized ledger emitted outside ODL?
5. Should the first approved plan target only PDF, or include HWP/xlsx/png routing from the start?

## Approval gate
status: awaiting-approval
<!-- When exploration is exhausted and unknowns are answered, set status: awaiting-approval. -->
<!-- That durable record is the loop guard: on a later turn read it and resume at the gate instead of re-running exploration. -->

Approve this draft to generate `.omo/plans/odl-vl-parser.md` with A1/A2/A3/B work packages and bake-off gates.
