// Citizens + exoselves + specialists surfaced in <CrewGrid /> and elsewhere.
//
// Three tiers:
//   citizens    — 8 opus domain leads (Yatima, Paolo, Blanca, Orlando,
//                 Karpal, Renata, Hashim, Inoshiro). Each owns a vertical,
//                 can spawn exoselves in parallel. Named after characters
//                 from Greg Egan's Diaspora — Blackrim's internal codename
//                 is Polis.
//   exoselves   — 7 sonnet/haiku workers in a shared pool. Any citizen
//                 can call any exoself.
//   specialists — opt-in domain experts, registered in
//                 bin/blackrim-features.default.json, activated by
//                 `gt feature enable <name>`. SpecialistDispatcher
//                 routes between tool and knowledge specialists by
//                 tag match.
//
// Source: README.md §"Core Concepts" + agent definition files at
// agents/citizens/*.md and agents/workers/*.md.

export interface CrewMember {
  name: string;
  role: string; // Title-cased role description
  model: "opus" | "sonnet" | "haiku" | "reference";
  glyph?: string; // Emoji/symbol shown on the card (citizen tier only)
  domain: string; // Domain summary
  sig: string; // Signature behavior (one-liner discipline tag)
}

export interface Worker {
  name: string;
  model: "sonnet" | "haiku";
  role: string;
  sig: string;
}

export interface Specialist {
  id: string; // Filesystem-safe slug; matches `gt feature enable <id>`
  name: string; // Display name (usually equal to id)
  kind: "tool" | "knowledge";
  owner: string; // Citizen that hands off to this specialist
  model: "haiku" | "reference" | "opus" | "sonnet";
  role: string; // Short label used by <CrewGrid /> tier
  sig: string; // Discipline one-liner used by <CrewGrid /> tier
  description: string; // Long-form blurb used by /specialists catalog
  tags: string[]; // SpecialistDispatcher routing tags
}

export const crew: CrewMember[] = [
  {
    name: "Yatima",
    role: "Engineering & Platform",
    model: "opus",
    glyph: "⚒",
    domain: "Backend, frontend, API, testing, performance, developer experience",
    sig: "Always uses the cheapest exoself that can do the work",
  },
  {
    name: "Paolo",
    role: "Infrastructure & Operations",
    model: "opus",
    glyph: "⛰",
    domain: "Cloud, IaC, networking, SRE, database, edge, ops, IT, FinOps",
    sig: "Runtime-first — no infra change without rollback",
  },
  {
    name: "Blanca",
    role: "Security & Compliance",
    model: "opus",
    glyph: "🛡",
    domain: "CISO, GRC, security arch, IAM, vuln mgmt, SOC, incident response",
    sig: "STRIDE before every code-change touching auth/secrets/network",
  },
  {
    name: "Orlando",
    role: "Product & Design",
    model: "opus",
    glyph: "🧭",
    domain: "Product, design/UX, change management, customer success, solutions",
    sig: "Storyline skills opt-in only — never auto-chained",
  },
  {
    name: "Karpal",
    role: "Data & Analytics",
    model: "opus",
    glyph: "⌬",
    domain: "Data pipelines, analytics, release engineering, professional services",
    sig: "Owns the pre-commit hook + signed-release verification",
  },
  {
    name: "Renata",
    role: "AI & Machine Learning",
    model: "opus",
    glyph: "◈",
    domain: "AI/ML systems, model evaluation, agent design, LLM pipelines",
    sig: "eval-driven — no prompt change without a before/after trajectory score",
  },
  {
    name: "Hashim",
    role: "Knowledge & Communications",
    model: "opus",
    glyph: "✎",
    domain: "Program mgmt, documentation, training, comms, governance, HR",
    sig: "Captures the recovery SHA on every history rewrite",
  },
  {
    name: "Inoshiro",
    role: "Frontend & UX",
    model: "opus",
    glyph: "◻",
    domain: "UI components, design systems, accessibility, motion, visual polish",
    sig: "WCAG 2.2 AA floor on every surface — contrast checked before merge",
  },
];

export const workers: Worker[] = [
  {
    name: "architect",
    model: "sonnet",
    role: "System design, ADRs, architecture review",
    sig: "Read-only by default — leaves files for the calling citizen to commit",
  },
  {
    name: "builder",
    model: "sonnet",
    role: "Code, IaC, configs, scripts",
    sig: "Implements exactly the spec — no scope creep",
  },
  {
    name: "reviewer",
    model: "sonnet",
    role: "Code review, security audit, compliance",
    sig: "Read-only. Severity-tagged findings, never modifies",
  },
  {
    name: "tester",
    model: "sonnet",
    role: "Test authoring, coverage gaps, regression suites",
    sig: "Red-Green-Refactor — failing test written before any fix",
  },
  {
    name: "researcher",
    model: "haiku",
    role: "Fast search, data gathering, web research",
    sig: "Cheapest tier. Returns facts + citations, no analysis",
  },
  {
    name: "writer",
    model: "haiku",
    role: "Docs, runbooks, reports, communications",
    sig: "Imperative voice in instructions. No hedging",
  },
  {
    name: "judge",
    model: "haiku",
    role: "LLM-as-judge scoring; read-only",
    sig: "Scores against a rubric. Never proposes fixes",
  },
];

// Mirrors bin/blackrim-features.default.json — every specialist with
// `tier: specialist` or `kind: knowledge-specialist` should appear here
// so the marketing surface stays in lockstep with the runtime catalog.
export const specialists: Specialist[] = [
  {
    id: "terraform-module-author",
    name: "terraform-module-author",
    kind: "tool",
    owner: "Paolo",
    model: "haiku",
    role: "Terraform / HCL authoring",
    sig: "Writes module-registry-clean HCL. tflint passes before handoff",
    description:
      "Writes, refactors, and validates Terraform modules — variables, outputs, locals, provider constraints, and tfvars. Paolo hands off when the HCL needs more than a single pass.",
    tags: ["terraform", "hcl", "iac", "modules", "tflint"],
  },
  {
    id: "python-patterns",
    name: "python-patterns",
    kind: "knowledge",
    owner: "Yatima",
    model: "reference",
    role: "Python idiom + edge-case advisor",
    sig: "Advises Yatima on async, typing, stdlib gotchas. Writes nothing",
    description:
      "Python idiom specialist: async patterns, type annotations, stdlib edge cases, and common anti-patterns. Loads when Yatima edits Python; stays out of the way otherwise.",
    tags: ["python", "async", "typing", "stdlib", "safety"],
  },
  {
    id: "staged-review",
    name: "staged-review",
    kind: "knowledge",
    owner: "Yatima",
    model: "reference",
    role: "Two-stage subagent review gate",
    sig: "Spec compliance, then code quality — fixed status-code contract",
    description:
      "Two-stage subagent review gate (spec compliance, then code quality) with a fixed status-code contract — DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED.",
    tags: ["review", "staged", "subagent", "spec-compliance", "quality"],
  },
  {
    id: "completion-verification",
    name: "completion-verification",
    kind: "knowledge",
    owner: "Blanca",
    model: "reference",
    role: "Evidence-before-claims completion gate",
    sig: "IDENTIFY → RUN → READ → VERIFY → CLAIM. Rejects probabilistic language",
    description:
      "Evidence-before-claims gate that runs before any agent reports a task complete — IDENTIFY, RUN, READ, VERIFY, CLAIM. Rejects probabilistic language and trust-based handoffs.",
    tags: ["verification", "evidence", "completion", "quality-gate", "rigor"],
  },
  {
    id: "code-review-loop",
    name: "code-review-loop",
    kind: "knowledge",
    owner: "Yatima",
    model: "reference",
    role: "Two-sided code review protocol",
    sig: "Severity triage, pushback criteria, no-performative-agreement rule",
    description:
      "Two-sided code review protocol — what the requester hands the reviewer, and how the implementer triages what comes back. Severity triage, pushback criteria, no-performative-agreement rule.",
    tags: ["code-review", "protocol", "severity", "pushback", "feedback-triage"],
  },
  {
    id: "branch-finishing",
    name: "branch-finishing",
    kind: "knowledge",
    owner: "Karpal",
    model: "reference",
    role: "Pre-merge gate + close-out for dev branches",
    sig: "Wraps blackrim-merge-agent with mandatory test/lint/typecheck checks",
    description:
      "Pre-merge gate + structured close-out for development branches. Wraps bin/blackrim-merge-agent with mandatory test/lint/typecheck checks and explicit close options.",
    tags: ["branch", "merge", "close", "gate", "worktree-cleanup"],
  },
  {
    id: "engineering-rigor-rules",
    name: "engineering-rigor-rules",
    kind: "knowledge",
    owner: "Yatima",
    model: "reference",
    role: "Hard-rules surface for engineering discipline",
    sig: "TDD failing-test-first, no-fix-without-root-cause, no-placeholder",
    description:
      "Hard rules surface — TDD's failing-test-first, debugging's no-fix-without-root-cause, planning's no-placeholder, verification's no-probabilistic-claim, subagent-reports-are-not-evidence. Surfaced when an agent is tempted to rationalize past them.",
    tags: ["rigor", "discipline", "hard-rules", "tdd", "root-cause", "planning"],
  },
];
