// Package dispatch — static model-tier advisory rules.
//
// AdviseModel returns the recommended Claude model tier for a given set of
// task signals. It is a pure, deterministic, no-LLM-cost function that
// implements the rule cascade documented in docs/research/model-cost-quality-landscape.md
// (blackrim-x4u1, MOA-1).
//
// Rules fire in priority order; first match wins. The result surfaces in
// `gt dispatch --advise` (MOA-4) and the dashboard advisor card (MOA-6).
//
// No third-party imports. No I/O. No global mutable state.
package dispatch

import "strings"

// ModelTier labels a Claude model size. Strings match what
// statusline/hooks/invocations-tracker.py emits as `model`.
type ModelTier string

const (
	ModelHaiku  ModelTier = "claude-haiku-4-5"
	ModelSonnet ModelTier = "claude-sonnet-4-6"
	ModelOpus   ModelTier = "claude-opus-4-7"
)

// ModelCostPerMillion is the input token rate (USD per 1M tokens) for each
// model tier. Mirrors internal/pricing/pricing.go (captured 2026-04-24,
// https://www.anthropic.com/pricing#anthropic-api). Output rates scale
// proportionally (5:15:75) but cost-saving math here uses input rates as
// the primary rank signal — the haiku:sonnet:opus input ratio is 1:3:15
// and the output ratio is identical, so the relative savings are the same
// regardless of which rate you use.
var ModelCostPerMillion = map[ModelTier]float64{
	ModelHaiku:  1.00,
	ModelSonnet: 3.00,
	ModelOpus:   15.00,
}

// ModelAdvice is the result of asking the dispatcher which model to use
// for a given task signal set.
type ModelAdvice struct {
	Model ModelTier
	// Reason is human-facing. It surfaces in `gt dispatch --advise` and
	// the dashboard advisor card (MOA-4, MOA-6).
	Reason string
	// CostSavedVsOpus is an estimated USD saving per typical task compared
	// to running the same task on opus. Positive means cheaper. Derived
	// from the per-role typical-task cost profiles in
	// docs/research/model-cost-quality-landscape.md.
	CostSavedVsOpus float64
	// CostSavedVsSonnet is the USD saving vs sonnet on the same task.
	// Zero when the recommended model IS sonnet; negative when opus is
	// recommended (opus costs more than sonnet).
	CostSavedVsSonnet float64
}

// ChainPosition classifies a task's position in a multi-step workflow.
// MOA-10 (blackrim-iee0): the advisor's CC-TS Layer 2 conservative gate
// uses ChainPosition as a SECONDARY dimension alongside ToleranceTier —
// upstream tasks bias toward higher quality (downgrades blocked) because
// their quality propagates to all downstream dependents; leaf tasks
// retain default behavior (downgrades admitted under tolerance margin).
//
// Default zero value PositionUnknown preserves backward compat: callers
// who don't set ChainPosition see the original CC-TS behavior bit-for-bit.
type ChainPosition int

const (
	// PositionUnknown is the zero value — no chain context provided.
	// Behavior is identical to pre-MOA-10 CC-TS dispatch.
	PositionUnknown ChainPosition = iota
	// PositionLeaf — terminal task, no downstream dependents. The
	// advisor may downgrade aggressively under the tolerance margin.
	PositionLeaf
	// PositionMid — task has 1-2 downstream dependents. Default CC-TS
	// gate applies (no chain-position bias added).
	PositionMid
	// PositionUpstream — task has 3+ downstream dependents. The Layer 2
	// gate rejects ANY downgrade unconditionally; quality propagates.
	PositionUpstream
	// PositionRoot — task gates the entire downstream flow (e.g., an
	// epic-defining ADR). Pinned to static MOA-3 baseline; no
	// posterior-driven downgrade ever, regardless of evidence.
	PositionRoot
)

// String renders the chain position for human-readable logs and JSON
// telemetry rows.
func (c ChainPosition) String() string {
	switch c {
	case PositionLeaf:
		return "leaf"
	case PositionMid:
		return "mid"
	case PositionUpstream:
		return "upstream"
	case PositionRoot:
		return "root"
	default:
		return "unknown"
	}
}

// DeriveChainPosition maps a dependent count + issue type to the
// ChainPosition class. Pure function — no I/O. Caller resolves the
// dependent count from bd (or any other source).
//
// Mapping (per MOA-10 spec):
//
//	type=epic               → PositionRoot
//	dependents == 0         → PositionLeaf
//	dependents in 1..2      → PositionMid
//	dependents >= 3         → PositionUpstream
//
// An empty issueType + dependents=0 still yields Leaf (the type signal
// is used only to escalate to Root). When neither signal is informative
// (negative dependents), returns PositionUnknown to preserve backward
// compat — callers should not see a forced bias from missing data.
func DeriveChainPosition(dependents int, issueType string) ChainPosition {
	if strings.EqualFold(strings.TrimSpace(issueType), "epic") {
		return PositionRoot
	}
	switch {
	case dependents < 0:
		return PositionUnknown
	case dependents == 0:
		return PositionLeaf
	case dependents <= 2:
		return PositionMid
	default:
		return PositionUpstream
	}
}

// TaskSignals is the input to AdviseModel. All fields optional;
// AdviseModel falls through to defaults when unset.
type TaskSignals struct {
	// Role is one of: "researcher" | "explore" | "builder" | "reviewer" |
	// "plan" | "architect" | "claude-code-guide" | "general-purpose" | "".
	// An empty or unrecognized role falls through to the tail rules.
	Role string

	// FileCount is the number of files the task reads or writes.
	FileCount int

	// PromptWords is the estimated word count of the task brief.
	PromptWords int

	// IntentKeywords is a list of free-form intent tags. Recognized
	// values: "refactor", "design", "audit", "explore", "novel".
	IntentKeywords []string

	// PriorFailureFlag signals that a previous attempt at this exact task
	// failed. AdviseModel escalates one tier from the rule's normal
	// default when this is set.
	PriorFailureFlag bool

	// EstOutputWords is the estimated output word count (useful for prose
	// tasks; currently used to distinguish trivial from non-trivial tasks
	// at the tail rules).
	EstOutputWords int

	// ChainPosition classifies the task's place in a multi-step
	// workflow (MOA-10). Default zero value PositionUnknown preserves
	// backward compat. The CC-TS Layer 2 gate consults this when set
	// to bias upstream tasks toward higher quality. AdviseModel itself
	// (the static rule cascade) is unaffected — only the learning
	// path uses this signal.
	ChainPosition ChainPosition

	// Dependents is the count of downstream tasks that depend on this
	// task. Used to derive ChainPosition (see DeriveChainPosition);
	// also recorded in telemetry so the paper analysis can correlate
	// raw count with decision outcome.
	Dependents int
}

// hasKeyword returns true when kw is present in keywords (case-insensitive).
func hasKeyword(keywords []string, kw string) bool {
	for _, k := range keywords {
		if strings.EqualFold(k, kw) {
			return true
		}
	}
	return false
}

// tierUp escalates a model one tier. haiku→sonnet, sonnet→opus, opus stays opus.
func tierUp(m ModelTier) ModelTier {
	switch m {
	case ModelHaiku:
		return ModelSonnet
	case ModelSonnet:
		return ModelOpus
	default:
		return ModelOpus
	}
}

// Typical-task cost profiles used by cost-savings helpers
// (from docs/research/model-cost-quality-landscape.md):
//
//	Researcher    haiku=$0.055  sonnet=$0.166  opus=$0.828
//	Explore       haiku=$0.100  sonnet=$0.300  opus=$1.501
//	Builder-small haiku=$0.108  sonnet=$0.324  opus=$1.620
//	Builder-multi haiku=$0.222  sonnet=$0.666  opus=$3.330
//	Reviewer-sm   haiku=$0.081  sonnet=$0.243  opus=$1.215
//	Reviewer-arch haiku=$0.143  sonnet=$0.429  opus=$2.145
//	Plan-small    haiku=$0.103  sonnet=$0.308  opus=$1.538
//	Plan-large    haiku=$0.213  sonnet=$0.639  opus=$3.195
//	Architect     haiku=$0.330  sonnet=$0.990  opus=$4.950
//	CCGuide       haiku=$0.056  sonnet=$0.168  opus=$0.841
//	General       haiku=$0.128  sonnet=$0.383  opus=$1.913

// rule is one entry in the static advisory table. Rules fire in slice order;
// first match wins. The name field is human-readable and surfaces in
// telemetry (r.name) — it is NOT derived from a function name.
type rule struct {
	name   string
	match  func(role string, s TaskSignals) bool
	advice ModelAdvice
}

// advisorRules is the ordered cascade implementing rules 1, 3–15.
// Rule 2 (PriorFailure escalation) is handled in AdviseModel itself because
// it recurses into AdviseModel. Rule numbering matches blackrim-fasf.
// First match wins; order is significant.
var advisorRules = []rule{
	// R1: architect always opus — ADR/cross-cutting work requires full system model.
	{"architect",
		func(role string, s TaskSignals) bool { return role == "architect" },
		ModelAdvice{ModelOpus, "architect/ADR-grade work — opus reasoning breadth justified", 0.00, -3.96}},
	// R3: plan + novel/design intent → opus. (R2 is pre-table; see AdviseModel.)
	{"novel-plan",
		func(role string, s TaskSignals) bool {
			return role == "plan" && (hasKeyword(s.IntentKeywords, "novel") || hasKeyword(s.IntentKeywords, "design"))
		},
		ModelAdvice{ModelOpus, "novel design — opus default per landscape research", 0.00, -2.56}},
	// R4: researcher + ≤5 files → haiku.
	{"researcher-small",
		func(role string, s TaskSignals) bool { return role == "researcher" && s.FileCount <= 5 },
		ModelAdvice{ModelHaiku, "small-scope read-only research — haiku validated by telemetry (9 measured calls)", 0.77, 0.11}},
	// R5: explore → haiku.
	{"explore",
		func(role string, s TaskSignals) bool { return role == "explore" },
		ModelAdvice{ModelHaiku, "file search — haiku validated", 1.40, 0.20}},
	// R6: claude-code-guide → haiku.
	{"claude-code-guide",
		func(role string, s TaskSignals) bool { return role == "claude-code-guide" },
		ModelAdvice{ModelHaiku, "Q&A about Claude Code — haiku validated", 0.79, 0.11}},
	// R7: builder + ≤3 files → sonnet.
	{"builder-small",
		func(role string, s TaskSignals) bool { return role == "builder" && s.FileCount <= 3 },
		ModelAdvice{ModelSonnet, "single-package mechanical edit — sonnet sufficient", 1.30, 0.00}},
	// R8: builder + >3 files + refactor intent → sonnet.
	{"builder-multi-refactor",
		func(role string, s TaskSignals) bool {
			return role == "builder" && s.FileCount > 3 && hasKeyword(s.IntentKeywords, "refactor")
		},
		ModelAdvice{ModelSonnet, "multi-file refactor with seams — sonnet sufficient (opus only when budget>$5)", 2.66, 0.00}},
	// R9: reviewer + design intent or >5 files → opus.
	{"reviewer-arch",
		func(role string, s TaskSignals) bool {
			return role == "reviewer" && (hasKeyword(s.IntentKeywords, "design") || s.FileCount > 5)
		},
		ModelAdvice{ModelOpus, "architecture review — opus default", 0.00, -1.72}},
	// R10: reviewer (default) → sonnet.
	{"reviewer-default",
		func(role string, s TaskSignals) bool { return role == "reviewer" },
		ModelAdvice{ModelSonnet, "correctness review — sonnet sufficient", 0.97, 0.00}},
	// R11: plan + ≤500 words → sonnet.
	{"plan-small",
		func(role string, s TaskSignals) bool { return role == "plan" && s.PromptWords <= 500 },
		ModelAdvice{ModelSonnet, "200-500 word design — sonnet sufficient", 1.23, 0.00}},
	// R12: plan (default) → sonnet.
	{"plan-default",
		func(role string, s TaskSignals) bool { return role == "plan" },
		ModelAdvice{ModelSonnet, "design — sonnet default", 2.56, 0.00}},
	// R13: general-purpose + >5 files + audit/design/refactor → sonnet.
	{"general-multi-synth",
		func(role string, s TaskSignals) bool {
			return role == "general-purpose" && s.FileCount > 5 &&
				(hasKeyword(s.IntentKeywords, "audit") ||
					hasKeyword(s.IntentKeywords, "design") ||
					hasKeyword(s.IntentKeywords, "refactor"))
		},
		ModelAdvice{ModelSonnet, "multi-file synthesis — sonnet", 1.53, 0.00}},
	// R14: general-purpose (default) → sonnet.
	{"general-default",
		func(role string, s TaskSignals) bool { return role == "general-purpose" },
		ModelAdvice{ModelSonnet, "general-purpose — sonnet default per landscape (8.9× cheaper than opus, 1.56× output)", 1.53, 0.00}},
	// R15: no role + ≤2 files + ≤100 words → haiku.
	{"trivial",
		func(role string, s TaskSignals) bool { return role == "" && s.FileCount <= 2 && s.PromptWords <= 100 },
		ModelAdvice{ModelHaiku, "trivial task — haiku", 1.78, 0.26}},
}

// AdviseModel applies the static rule cascade and returns a ModelAdvice.
// Rules fire in priority order; first match wins. The returned advice is
// fully determined by the input — no randomness, no I/O, no global state.
//
// Rule numbering matches the spec in the bd issue blackrim-fasf.
func AdviseModel(s TaskSignals) ModelAdvice {
	role := strings.ToLower(strings.TrimSpace(s.Role))

	// Rule 2 — escalate one tier when a previous attempt failed.
	// This is a meta-rule: it recurses into AdviseModel with the flag
	// cleared to compute the base advice, then escalates one tier.
	// It must remain outside the table because it calls AdviseModel itself.
	if s.PriorFailureFlag {
		lower := s
		lower.PriorFailureFlag = false
		base := AdviseModel(lower)
		if base.Model == ModelOpus {
			base.Reason = "previous attempt failed at opus tier — escalating (already at max)"
			return base
		}
		escalated := tierUp(base.Model)
		return ModelAdvice{
			Model:             escalated,
			Reason:            "previous attempt failed at " + string(base.Model) + " tier — escalating",
			CostSavedVsOpus:   costSavedVsOpus(escalated),
			CostSavedVsSonnet: costSavedVsSonnet(escalated),
		}
	}

	// Rules 1, 3–15: table-driven, first match wins.
	for _, r := range advisorRules {
		if r.match(role, s) {
			// Rule 1 special-case: annotate PriorFailureFlag even though it
			// can't escalate above opus (handled by rule 2 path above; this
			// branch is only reached when PriorFailureFlag is false).
			return r.advice
		}
	}

	// Rule 16 — Fall-through: sonnet conservative default.
	return ModelAdvice{
		Model:             ModelSonnet,
		Reason:            "no rule fired — sonnet conservative default",
		CostSavedVsOpus:   1.53, // opus($1.913) - sonnet($0.383)
		CostSavedVsSonnet: 0.00,
	}
}

// costSavedVsOpus returns an approximate USD saving vs opus for the given
// model tier, using the general-purpose typical-task cost profile as a
// conservative proxy. Used by the PriorFailureFlag escalation path where
// the exact role cost profile is unknown.
//
// Profile: general-purpose — haiku=$0.128, sonnet=$0.383, opus=$1.913
func costSavedVsOpus(m ModelTier) float64 {
	switch m {
	case ModelHaiku:
		return 1.78 // opus($1.913) - haiku($0.128)
	case ModelSonnet:
		return 1.53 // opus($1.913) - sonnet($0.383)
	default:
		return 0.00 // opus — no saving
	}
}

// costSavedVsSonnet returns an approximate USD saving vs sonnet for the
// given model tier, using the general-purpose typical-task cost profile.
func costSavedVsSonnet(m ModelTier) float64 {
	switch m {
	case ModelHaiku:
		return 0.26 // sonnet($0.383) - haiku($0.128)
	case ModelOpus:
		return -1.53 // opus costs $1.53 more than sonnet (negative = more expensive)
	default:
		return 0.00 // sonnet — no delta
	}
}
