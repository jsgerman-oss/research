---
title: 'The AST as LLM Lens: Outline-First Reading and Compile-Gated Symbolic Surgery for Multi-Agent Coding Systems'

authors:
  - me

date: '2026-05-15T00:00:00Z'
publishDate: '2026-05-15T00:00:00Z'

publication_types: ['article']
publication: 'Working paper, draft'
publication_short: ''

abstract: |
  Large-language-model (LLM) agents that read and modify code pay two recurring taxes: a **read tax** when they consume entire source files to answer questions whose answer lies in the file's structure rather than its bodies, and a **write tax** when they emit free-form diffs that can silently corrupt working programs. Both taxes scale with file size; both can be cut by routing through the abstract syntax tree (AST). This paper introduces and evaluates the design of an AST-native code surface for the multi-agent framework Blackrim: a single Markdown outline emitter with three entry points (a CLI, a runtime hook that auto-prepends outlines to `Read` tool results, and an MCP retrieval surface), a plan/execute pair contract for symbolic surgery, and a polyglot compile-gate that rejects refactors whose dry-run output fails the language's native syntax check.

  We formalise the design as a constrained reduction problem: minimise the expected token cost of an agent's interaction with a file while preserving task-success rate $q$ and ruling out false-positive edits (those that compile or parse without error but alter behaviour unintendedly). The reduction has three measurable components: outline compression ratio $r(F) = |O(F)|/|F|$, outline adoption rate, and refactor false-negative rate.

  Implemented across Go, Python, JavaScript, and TypeScript via per-language parser backends (`go/ast`, embedded CPython `ast`, `acorn`, `ts.createSourceFile`), our compression backends achieve measured token savings of **82.0% (Go)**, **84.1% (Python)**, **83.0% (JavaScript)**, and **75.2% (TypeScript)** on a realistic benchmark fixture, with graceful fallback-to-passthrough on parse error or missing host runtime. The outline emitter targets a ~300-token output regardless of file size, yielding an estimated ~100× token reduction on a 2700-line file relative to a full `Read`; the end-to-end reduction on real agent traces is the central pending empirical claim.

summary: |
  An AST-native code surface for multi-agent LLM workflows. Outline-first reading achieves 75–84% token savings across Go/Python/JS/TS; compile-gated symbolic surgery rejects refactors whose dry-run output fails the language's syntax check. Pre-registers OQ-AST-1..7 for the still-unmeasured claims.

tags:
  - Abstract syntax tree
  - Code outline
  - Context window
  - Multi-agent systems
  - LLM tooling
  - Tree-sitter
  - Code refactoring
  - Language server protocol
  - Prompt compression

featured: true

links:
  - type: source
    url: https://github.com/jsgerman-oss/research/tree/main/blackrim-ast-paper

image:
  caption: ''
  focal_point: ''
  preview_only: false

projects: []
slides: ''
---

## Status

Working draft. §6.2 (compression ratios by language) is backed by real measurements; the remaining §6 empirical claims (outline adoption rate, refactor false-negative rate, end-to-end token reduction on real traces) are pre-registered open questions, marked in the LaTeX with `\tothink{}`.

## Reproducibility

§6.2's compression ratios are produced by `scripts/pull-compression-ratios.py` + `scripts/aggregate-by-language.py`, reading bench fixtures from a Blackrim checkout. To reproduce:

```bash
make data       # runs the four aggregation scripts
make            # latex picks up new data/*.csv automatically via pgfplots
```

## Companion software

The paper describes the AST surface as a system component of [Blackrim](https://github.com/jsgerman-oss/blackrim.dev). Reference implementations: `cmd/gt/outline/` (Phase 1a outline emitter), `cmd/gt/compress_structure*.go` (polyglot backends), `internal/codeindex/refactor/` (LSP-driven Tier-1 symbolic refactors), `hooks-staging/outline-discipline.sh` (warn→auto→block hook), `skills/read-with-outline/SKILL.md` (agent-facing skill).
