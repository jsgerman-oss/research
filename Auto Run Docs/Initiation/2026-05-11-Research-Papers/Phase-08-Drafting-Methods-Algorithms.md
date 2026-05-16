# Phase 08: Draft Methods, System & Algorithm Sections — Both Papers

The middle sections of both papers (problem formulation, system overview, algorithms) are currently placeholder-with-substantive-where-data-exists. This phase converts them into rigorous methods writeups: formal problem statements, system diagrams described in prose, algorithmic specifications in `algorithm` / `algorithmic` LaTeX environments, and complexity / correctness arguments where applicable.

## Tasks

- [ ] Read the current draft state for the routing-caching paper:
  - `sections/03-problem-formulation.tex` — note existing variables, assumptions, objective function
  - `sections/04-system.tex` — note the system architecture currently described
  - `sections/05-routing-algorithm.tex` — the routing classifier / decision rule
  - `sections/06-plancache-algorithm.tex` — the semantic cache lookup/store algorithm
  - The data from Phase 05 + figures from Phase 06 — methods must be consistent with what was actually measured

- [ ] Rewrite the routing-caching methods sections:
  - **§3 Problem Formulation**: define the per-turn routing problem formally (turn $t$, tier set $\mathcal{M}$, quality function $q$, cost function $c$, objective). Define the plan-caching problem similarly (plan key space, similarity function, hit/miss/correctness tradeoff). Be explicit about assumptions (static prefix, dispatch-fanout shape, telemetry observability)
  - **§4 System**: describe the architecture without ASCII diagrams (LaTeX-safe); reference any figure if one is added. Explain the data flow: turn arrives → router decides → response → cache write-back if applicable
  - **§5 Routing Algorithm**: present as an `algorithm` environment with pseudocode. Include training (if any), inference, the confidence/similarity threshold mechanism, and fallback policy. Discuss complexity and any latency budget
  - **§6 Plan-Cache Algorithm**: similarly formalized. Cover key extraction, embedding, similarity threshold, eviction policy, and the orthogonality claim w.r.t. prefix caching (proof-sketch level rigor)

- [ ] Read the current draft state for the instruction-trim paper:
  - `sections/03-problem-formulation.tex`
  - `sections/04-system.tex`
  - `sections/05-algorithm.tex` — the residency decision algorithm
  - Phase 05 data + Phase 07 figures

- [ ] Rewrite the instruction-trim methods sections:
  - **§3 Problem Formulation**: formal definition of the static-prefix-residency problem. Variables: instruction line $\ell$, frequency-of-use $f(\ell)$, retention decision $r(\ell) \in \{0,1\}$, fidelity function $F$, prefix cost $C_{\text{prefix}}$. Objective: maximize cost reduction subject to fidelity ≥ threshold. State assumptions (line independence approximation, frequency stationarity, on-demand-read budget)
  - **§4 System**: describe the trimming workflow (measure → score → decide → apply → validate), the role of Read-on-demand in the agent loop, and the static-prefix economics that make this matter at fleet scale
  - **§5 Algorithm**: `algorithm` environment with pseudocode for the frequency-weighted residency decision. Include scoring rule, threshold derivation, conservative-retention safeguards, and the iterative refinement loop. Discuss complexity (linear in instruction lines) and the inverse — how dynamic frequency drift would invalidate the static decision

- [ ] Build both papers and verify the new methods sections compile cleanly:
  - `make` in both directories
  - Check that any new `\usepackage{algorithm}` / `\usepackage{algorithmic}` (or `algorithm2e` or `algpseudocode`) declarations are added to `main.tex` and consistent across both papers — pick one package family and use it in both for cross-paper consistency
  - Confirm all `\ref{}` / `\eqref{}` resolve
  - Save build status to `Auto Run Docs/Initiation/Working/Phase-08-Build.md`

- [ ] Cross-link the methods sections against the lit-review theme docs. For each algorithm or formalism, add a footnote or trailing sentence positioning it relative to the nearest precedent identified in Phase 02/03. Update the corresponding theme doc with a back-reference to "this paper §X" so the knowledge graph stays bidirectional.
