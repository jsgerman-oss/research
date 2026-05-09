---
# Landing page — research portfolio for Jay German.
# Sections render as Hugo Blox blocks.

title: ''
summary: ''
date: 2026-05-09
type: landing

sections:
  # ── Bio ─────────────────────────────────────────────────────────────────
  - block: resume-biography-3
    content:
      username: me
      text: ''
      button:
        enable: false
      headings:
        about: ''
        education: ''
        interests: 'Research interests'
    design:
      background:
        gradient_mesh:
          enable: false
      name:
        size: lg
      avatar:
        size: medium
        shape: rounded

  # ── Research statement ──────────────────────────────────────────────────
  - block: markdown
    content:
      title: ''
      subtitle: ''
      text: |-
        ## Research

        The cost-control problem in production agent systems is not a model-selection problem in the usual sense. Rewards are asymmetric: a single poor decision in a critical-path task can erase weeks of cost savings. Per-cell sample sizes are small. A meaningful Bayesian prior is available from offline evaluation, but is itself imperfect.

        I formalise this as a constrained Bayesian decision problem and study policies — currently variants of conservative constrained Thompson sampling — that minimise cost subject to a per-task quality-preservation constraint, with conformal-prediction wrappers giving explicit confidence bounds.

        Methods I use, and write about: hierarchical Beta priors seeded from offline evals; Beta-Bernoulli posteriors updated from live telemetry; one-sided hypothesis testing under explicit asymmetric loss; uncertainty-triggered evaluation to resolve underdetermined cells.
    design:
      columns: '1'

  # ── Papers ──────────────────────────────────────────────────────────────
  - block: collection
    id: papers
    content:
      title: 'Papers'
      filters:
        folders:
          - publications
        exclude_featured: false
    design:
      view: citation

  # ── Code ────────────────────────────────────────────────────────────────
  - block: markdown
    id: code
    content:
      title: 'Code'
      text: |-
        - **[Blackrim](https://github.com/jsgerman-oss/blackrim.dev)** — open-source multi-agent framework. Includes the CC-TS dispatch policy (`internal/dispatch/model.go`).
        - **[Research repo](https://github.com/jsgerman-oss/research)** — paper sources, eval harnesses, reproducibility scripts.
    design:
      columns: '1'

  # ── Contact ─────────────────────────────────────────────────────────────
  - block: markdown
    id: contact
    content:
      title: 'Contact'
      text: |-
        Reach me at [camber.estate_6j@icloud.com](mailto:camber.estate_6j@icloud.com), or on GitHub at [@jsgerman-oss](https://github.com/jsgerman-oss). I'm open to research collaboration, technical advisory, and conversations about production agentic systems.
    design:
      columns: '1'
---
