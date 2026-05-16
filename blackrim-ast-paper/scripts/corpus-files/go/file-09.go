// Package dispatch — adapter from the CC-TS Bayesian advisor (MOA-9,
// blackrim-6tov) into the existing static rule cascade (MOA-3,
// AdviseModel).
//
// The CC-TS layer (internal/dispatch/ccts) implements the four-layer
// algorithm specified in docs/research/model-advisor-algorithms.md.
// Its types use ordinal tiers (0=haiku, 1=sonnet, 2=opus) and
// per-(agent, shape) ShapeKey cells. This file bridges that to the
// existing dispatch.ModelTier (string identifier) + dispatch.TaskSignals
// (role + file count + …) shape so cmd/gt/dispatch_advise.go can
// consume the learned advice identically.
//
// Wiring contract (per MOA-9 spec):
//
//	AdviseWithLearning(state, signals) -> ModelAdvice
//
// When `state == nil` OR the cell isn't in `state.Cells`, the
// function falls back to AdviseModel(signals) — the cold-cold-start
// path. This preserves the MOA-3 behavior bit-for-bit when learning
// is disabled.
//
// AdviseWithLearning is opt-in. The default `gt dispatch --advise`
// path still goes through AdviseModel; --learn switches it. See
// cmd/gt/dispatch_advise.go for the flag plumbing (MOA-9).
package dispatch

import (
	"fmt"
	"strings"

	"github.com/auditidentity/blackrim.dev/internal/dispatch/ccts"
)

// ToCCTSTier converts a parent dispatch.ModelTier (string) to the
// ccts ordinal ModelTier. Used at the AdviseWithLearning boundary
// and in tests that need to assert "the static rule's tier matches
// the learning path's tier."
//
// Defaults to TierSonnet for unknown tiers — the safe middle.
func ToCCTSTier(m ModelTier) ccts.ModelTier {
	switch m {
	case ModelHaiku:
		return ccts.TierHaiku
	case ModelSonnet:
		return ccts.TierSonnet
	case ModelOpus:
		return ccts.TierOpus
	default:
		return ccts.TierSonnet
	}
}

// FromCCTSTier converts the ccts ordinal back to the parent's string
// tier. The two are conceptually identical; we just stringify.
func FromCCTSTier(m ccts.ModelTier) ModelTier {
	switch m {
	case ccts.TierHaiku:
		return ModelHaiku
	case ccts.TierSonnet:
		return ModelSonnet
	case ccts.TierOpus:
		return ModelOpus
	default:
		return ModelSonnet
	}
}

// ParseTierName accepts a short tier alias ("haiku", "sonnet", "opus")
// or the full canonical model identifier (claude-haiku-4-5 etc.) and
// returns the parent ModelTier. Used by the `--override-tier` CLI flag
// and any other operator-facing surface that wants a friendlier vocab
// than the canonical strings.
//
// Returns ("", false) for any other input — caller should error out
// rather than guess. We deliberately do NOT fall back to a "sensible"
// tier here: an unknown override is operator error and silently
// pretending it parsed would mask bugs in tooling that calls us.
func ParseTierName(name string) (ModelTier, bool) {
	switch strings.ToLower(strings.TrimSpace(name)) {
	case "haiku", string(ModelHaiku):
		return ModelHaiku, true
	case "sonnet", string(ModelSonnet):
		return ModelSonnet, true
	case "opus", string(ModelOpus):
		return ModelOpus, true
	default:
		return "", false
	}
}

// SignalsToShapeKey heuristically maps a TaskSignals into the
// (Agent, Shape) coordinates the CC-TS state is keyed by.
//
// The mapping uses the role + first-keyword (or file count) to
// resolve an agent + shape. It is deliberately small — the static
// rule cascade in AdviseModel already encodes this domain knowledge,
// and we don't want a parallel router. When the mapping fails
// (signals don't match any known shape), the caller falls through
// to AdviseModel.
//
// Returned `ok=false` means: no matching cell — caller should fall
// back to the static rule cascade.
func SignalsToShapeKey(s TaskSignals) (key ccts.ShapeKey, ok bool) {
	role := strings.ToLower(strings.TrimSpace(s.Role))
	switch role {
	case "researcher":
		// Re1 (≤5 files), Re5 (>10 files synthesis).
		if s.FileCount <= 5 {
			return ccts.ShapeKey{Agent: "Researcher", Shape: "Re1"}, true
		}
		return ccts.ShapeKey{Agent: "Researcher", Shape: "Re5"}, true
	case "explore":
		// Researcher Re1 — file lookup pattern.
		return ccts.ShapeKey{Agent: "Researcher", Shape: "Re1"}, true
	case "builder":
		// Bu1 (≤3 files single-file edit), Bu2 (multi-file refactor).
		if s.FileCount <= 3 {
			return ccts.ShapeKey{Agent: "Builder", Shape: "Bu1"}, true
		}
		if hasKeyword(s.IntentKeywords, "refactor") {
			return ccts.ShapeKey{Agent: "Builder", Shape: "Bu2"}, true
		}
		return ccts.ShapeKey{Agent: "Builder", Shape: "Bu2"}, true
	case "reviewer":
		// Rv1 default; Rv2 for design / large.
		if hasKeyword(s.IntentKeywords, "design") || s.FileCount > 5 {
			return ccts.ShapeKey{Agent: "Reviewer", Shape: "Rv2"}, true
		}
		return ccts.ShapeKey{Agent: "Reviewer", Shape: "Rv1"}, true
	case "architect":
		// A1 cross-cutting (default for architect role).
		return ccts.ShapeKey{Agent: "Architect", Shape: "A1"}, true
	case "claude-code-guide":
		// W1 — closest match in MOA-1b (templated short-form).
		return ccts.ShapeKey{Agent: "Writer", Shape: "W1"}, true
	case "general-purpose":
		// No direct cell; fall through.
		return ccts.ShapeKey{}, false
	case "plan":
		// No direct cell; planning is citizen judgment, falls through.
		return ccts.ShapeKey{}, false
	}
	return ccts.ShapeKey{}, false
}

// ToCCTSChainPosition converts the parent dispatch.ChainPosition to
// the ccts package's ordinal. Both enums use identical semantics —
// duplicated only to keep ccts free of upward dependencies.
func ToCCTSChainPosition(p ChainPosition) ccts.ChainPosition {
	switch p {
	case PositionLeaf:
		return ccts.PositionLeaf
	case PositionMid:
		return ccts.PositionMid
	case PositionUpstream:
		return ccts.PositionUpstream
	case PositionRoot:
		return ccts.PositionRoot
	default:
		return ccts.PositionUnknown
	}
}

// AdviseWithLearning combines the CC-TS posterior advisor with the
// existing static rule cascade.
//
//   - When `state` is nil OR the signals don't map to a known cell,
//     fall back to AdviseModel(signals) — the static rule path.
//   - When the cell is known, run state.RecommendWithChain(key, pos,
//     dependents) and wrap the result in ModelAdvice. Reason becomes a
//     CC-TS-style explanation ("CC-TS recommends sonnet — pooled-mean=
//     0.92, candidates=[…], chain=upstream").
//
// MOA-10 (blackrim-iee0): when signals.ChainPosition is non-default
// (i.e., not PositionUnknown), the CC-TS Layer 2 gate biases upstream
// tasks toward higher quality regardless of posterior evidence. See
// ccts.RecommendWithChain for the constraint semantics.
//
// The returned ModelAdvice's CostSavedVsOpus / CostSavedVsSonnet
// fields are computed via the same general-purpose cost profile
// as the PriorFailureFlag escalation path (costSavedVsOpus /
// costSavedVsSonnet). For exact role-specific costs, the CLI layer
// in cmd/gt/dispatch_advise.go re-derives via the rate sheet.
func AdviseWithLearning(state *ccts.AdvisorState, signals TaskSignals) ModelAdvice {
	if state == nil {
		return AdviseModel(signals)
	}
	key, ok := SignalsToShapeKey(signals)
	if !ok {
		return AdviseModel(signals)
	}
	if _, exists := state.Cells[key]; !exists {
		return AdviseModel(signals)
	}
	tier, reasons := state.RecommendWithChain(
		key,
		ToCCTSChainPosition(signals.ChainPosition),
		signals.Dependents,
	)
	model := FromCCTSTier(tier)
	pooledMean := reasons.PriorMass[tier]
	chainSuffix := ""
	if signals.ChainPosition != PositionUnknown {
		chainSuffix = fmt.Sprintf(", chain=%s", reasons.ChainPosition)
		if reasons.ChainPinned {
			chainSuffix += "[pinned]"
		}
	}
	reason := fmt.Sprintf(
		"CC-TS %s×%s → %s (pooled_mean=%.3f, candidates=%v, eval_flagged=%v%s)",
		key.Agent, key.Shape, tier.String(), pooledMean, reasons.Candidates, reasons.EvalFlagged,
		chainSuffix,
	)
	return ModelAdvice{
		Model:             model,
		Reason:            reason,
		CostSavedVsOpus:   costSavedVsOpus(model),
		CostSavedVsSonnet: costSavedVsSonnet(model),
	}
}
