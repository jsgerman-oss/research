// Package eval is the eval-suite runner — it loads a Suite YAML, runs
// each Case through a TaskInvoker, scores Outputs against the Suite's
// Scorers, and persists the run to .beads/telemetry/eval-runs.jsonl.
//
// The Suite format is dual-versioned. v1 is the legacy fixtures.yaml
// format used by `gt model eval` (a flat list of prompt/expected_outcome
// pairs). v2 adds a structured `task / dataset / scorers / gates`
// shape — fully specified in docs/specs/eval-suite-v2.md, parsed here.
// v2 also supports an optional `trajectory:` block (slice 5) for grading
// the agent orchestration tree rather than only the final output.
//
// The loader API is split so callers can either read from disk
// (LoadSuite resolves relative paths against the suite file's
// directory) or feed bytes directly (ParseSuite, used by tests).
//
// See docs/specs/eval-suite-v2.md for the full v2 schema reference and
// worked examples (evals/_demo/example, evals/_demo/example-file,
// evals/_demo/example-rubric — demo shelf, not run by the CI gate).
package eval

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"

	"github.com/auditidentity/blackrim.dev/internal/scorer/trajectory"
)

// ErrSuiteInvalid is returned by ParseSuite when the YAML is malformed
// or violates a structural invariant (missing version, no cases, etc.).
var ErrSuiteInvalid = errors.New("eval: suite invalid")

// Suite is a parsed eval suite. Both v1 and v2 records use this struct;
// the Version field determines which fields are populated.
type Suite struct {
	Version   int    `yaml:"version"`
	Name      string `yaml:"name"`
	SpecRef   string `yaml:"spec_ref,omitempty"`
	CreatedAt string `yaml:"created_at,omitempty"`

	// v2-only fields ────────────────────────────────────────────────
	Task       *Task             `yaml:"task,omitempty"`
	Dataset    *Dataset          `yaml:"dataset,omitempty"`
	Scorers    []ScorerConfig    `yaml:"scorers,omitempty"`
	Gates      *Gates            `yaml:"gates,omitempty"`
	Trajectory *TrajectoryConfig `yaml:"trajectory,omitempty"`
	// Pairwise carries suite-level controls for kind:pairwise scorers.
	// When unset, the runner constructs SwapScorers with the swap test
	// ENABLED by default — this is the position-bias-mitigating safe
	// path (Zheng et al. 2023, §E1.4 of docs/research/eval-suite-
	// algorithms.md). Suites that explicitly accept the bias for cost
	// reasons set `pairwise.swap_test: false`.
	Pairwise *PairwiseSuiteConfig `yaml:"pairwise,omitempty"`

	// v1-only fields ────────────────────────────────────────────────
	Fixtures []Fixture `yaml:"fixtures,omitempty"`

	// sourceDir is the directory containing the suite file, used to
	// resolve relative dataset paths. Set by LoadSuite; empty for
	// ParseSuite (caller's problem).
	sourceDir string `yaml:"-"`
}

// Task describes how to invoke the system under test for each case.
type Task struct {
	Agent  string `yaml:"agent,omitempty"`
	Worker string `yaml:"worker,omitempty"`
	// Invoke names the invocation strategy. Slice 2 supports "replay"
	// (use Case.Output as captured pre-recorded output). Slice 6
	// will add "anthropic-direct" and harness invocation.
	Invoke string `yaml:"invoke"`
	// Model is the model id passed to the invocation strategy when
	// applicable.
	Model string `yaml:"model,omitempty"`
}

// Dataset locates the cases for a suite.
type Dataset struct {
	// Source is one of "file" | "inline" | "sampled".
	Source string `yaml:"source"`
	// Path is the relative path to the cases JSONL when Source == "file".
	// Resolved against the suite file's directory.
	Path string `yaml:"path,omitempty"`
	// Inline is the list of cases when Source == "inline".
	Inline []Case `yaml:"inline,omitempty"`
}

// PairwiseSuiteConfig is the suite-level toggle for kind:pairwise
// scorers. The only knob today is the swap-test opt-out — additional
// position-bias controls (e.g. randomize per-case, dual-family panel)
// land in a follow-up.
type PairwiseSuiteConfig struct {
	// SwapTest, when explicitly false, disables the position-bias swap
	// test on every kind:pairwise scorer in this suite — only the
	// forward (A, B) call runs, halving cost at the price of ~30%
	// position-flip bias. Pointer so we can distinguish "unset (default
	// true)" from "explicitly false". Default behavior: swap test ON.
	SwapTest *bool `yaml:"swap_test,omitempty"`
}

// SwapTestEnabled returns whether the swap test is on for this suite.
// Default true (swap-test enabled) when the block is unset; honors the
// explicit pointer when the user sets it.
func (c *PairwiseSuiteConfig) SwapTestEnabled() bool {
	if c == nil || c.SwapTest == nil {
		return true
	}
	return *c.SwapTest
}

// ScorerConfig declares one scorer to apply to each case.
type ScorerConfig struct {
	// Name is the registry-lookup key OR a custom display name for
	// kind: rubric inline scorers.
	Name string `yaml:"name"`
	// Kind is one of "heuristic" | "llm" | "rubric" | "embedding" |
	// "pairwise". For kind:pairwise the runner builds a
	// llm.PairwiseScorer wrapping the rubric in `template:` (or the
	// embedded `factuality_pairwise` default) inside a
	// pairwise.SwapScorer (toggled by Suite.Pairwise.SwapTest).
	Kind string `yaml:"kind"`
	// Func is the registered scorer name when Kind == "heuristic" or
	// "embedding". Defaults to Name.
	Func string `yaml:"func,omitempty"`
	// Template is the scorer template name when Kind == "llm" (looks
	// up an embedded template), or the inline YAML when Kind ==
	// "rubric".
	Template string `yaml:"template,omitempty"`
	// JudgeModel is the optional override fed to the LLM scorer.
	JudgeModel string `yaml:"judge_model,omitempty"`
	// Config is a free-form per-scorer configuration block. The runner
	// passes it (via scorer.Configurable) to scorers that declare
	// dependence on YAML-supplied parameters — e.g. symbol_exists's
	// expected-symbols list, command_succeeds's command vector, or
	// regression_touched's file scope. Stateless scorers ignore it.
	Config map[string]any `yaml:"config,omitempty"`
}

// Gates declares pass/fail thresholds for a suite.
type Gates struct {
	MinMean       float64                  `yaml:"min_mean,omitempty"`
	MinPctCorrect float64                  `yaml:"min_pct_correct,omitempty"`
	PerScorer     map[string]PerScorerGate `yaml:"per_scorer,omitempty"`
}

// PerScorerGate is a per-scorer threshold inside Gates.PerScorer.
type PerScorerGate struct {
	MinMean float64 `yaml:"min_mean,omitempty"`
}

// TrajectoryConfig declares trajectory-aware scoring for a v2 suite.
// All fields are optional; the runner instantiates only the scorers
// whose corresponding fields are populated.
//
// Slice 5 of the eval epic (flagshipsyst-08o). Live tracing /
// runtime enforcement of MaxToolCalls is out of scope — these
// scorers grade the audit log post-hoc.
type TrajectoryConfig struct {
	// ExpectedRoute is the canonical agent-spawn sequence the suite
	// author expects. RouteMatchScorer compares observed trajectory
	// route via Levenshtein edit distance.
	ExpectedRoute []string `yaml:"expected_route,omitempty"`

	// ForbiddenWorkers is the set of agent names that must NOT be
	// spawned during the trajectory (e.g., production-only agents in
	// a smoke suite). Binary score: 1.0 if none observed, 0.0 if any.
	ForbiddenWorkers []string `yaml:"forbidden_workers,omitempty"`

	// MaxToolCalls is the soft budget for tool invocations across the
	// whole trajectory. Linear fall-off above the budget. 0 disables
	// the scorer (always 1.0).
	MaxToolCalls int `yaml:"max_tool_calls,omitempty"`

	// MustTerminate, when true, instantiates the TerminationScorer
	// (every spawn must have a matching close). When false the scorer
	// is omitted; users who want vacuous-pass behavior should leave
	// this off rather than hand-set MustTerminate: true on a suite
	// with no spawns expected.
	MustTerminate bool `yaml:"must_terminate,omitempty"`

	// GoalAchieved, when set, instantiates the LLM-as-judge
	// GoalAchievedScorer over the rendered trajectory + final output.
	GoalAchieved *GoalAchievedConfig `yaml:"goal_achieved_judge,omitempty"`
}

// GoalAchievedConfig configures the goal_achieved trajectory scorer.
//
// Template is either an inline llm.Spec YAML (full schema with
// choice_scores) or a bare prompt that the runner wraps with a
// default Yes/No binary schema. Empty Template uses
// trajectory.DefaultGoalAchievedTemplate.
type GoalAchievedConfig struct {
	Template   string `yaml:"template"`
	JudgeModel string `yaml:"judge_model,omitempty"`
}

// Case is one input/output/expected triple to score. ID must be unique
// within the dataset.
type Case struct {
	ID       string `yaml:"id" json:"id"`
	Input    string `yaml:"input" json:"input"`
	Expected string `yaml:"expected,omitempty" json:"expected,omitempty"`
	// Output is optional pre-captured output. When present, the runner
	// can use it directly (Task.Invoke == "replay"); otherwise the
	// runner produces it via the configured TaskInvoker.
	Output   string         `yaml:"output,omitempty" json:"output,omitempty"`
	Metadata map[string]any `yaml:"metadata,omitempty" json:"metadata,omitempty"`

	// Trajectory carries inline trajectory test data. When present, the
	// trajectory runner uses these events instead of reading
	// .beads/telemetry/audit.jsonl — the deterministic test path. The
	// production path (slice 6+) leaves this empty and the runner reads
	// from the audit log filtered by SessionID.
	Trajectory []trajectory.Event `yaml:"trajectory,omitempty" json:"trajectory,omitempty"`
}

// Fixture is the v1 case shape from the legacy fixtures.yaml.
type Fixture struct {
	ID              string `yaml:"id"`
	Agent           string `yaml:"agent"`
	Prompt          string `yaml:"prompt"`
	ExpectedOutcome string `yaml:"expected_outcome"`
	Notes           string `yaml:"notes,omitempty"`
}

// LoadSuite reads + parses a Suite YAML from disk. Relative dataset
// paths are resolved against the suite file's directory.
//
// For v1 suites missing the `name:` field (the legacy fixtures.yaml
// shape predates name-as-required), the name is derived from the
// suite file's parent directory — e.g. evals/codex-mini-haiku/
// fixtures.yaml → name="codex-mini-haiku".
func LoadSuite(path string) (*Suite, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("eval: read suite %s: %w", path, err)
	}
	s, err := ParseSuite(data)
	if err != nil {
		return nil, err
	}
	s.sourceDir = filepath.Dir(path)
	if s.Name == "" {
		s.Name = filepath.Base(s.sourceDir)
	}
	return s, nil
}

// ParseSuite parses YAML bytes into a Suite. Validates structural
// invariants but does NOT load referenced datasets — callers must
// invoke (*Suite).Cases() to materialize cases.
//
// `name:` is recommended but optional — LoadSuite fills it in from the
// filename when missing. Callers using ParseSuite directly should
// either set Name explicitly afterward or accept Suite.Name == "".
func ParseSuite(data []byte) (*Suite, error) {
	var s Suite
	if err := yaml.Unmarshal(data, &s); err != nil {
		return nil, fmt.Errorf("%w: yaml: %v", ErrSuiteInvalid, err)
	}
	if s.Version != 1 && s.Version != 2 {
		return nil, fmt.Errorf("%w: unsupported version %d (need 1 or 2)", ErrSuiteInvalid, s.Version)
	}
	switch s.Version {
	case 1:
		if len(s.Fixtures) == 0 {
			return nil, fmt.Errorf("%w: v1 suite has no fixtures", ErrSuiteInvalid)
		}
		if s.Trajectory != nil {
			return nil, fmt.Errorf("%w: trajectory block requires version 2", ErrSuiteInvalid)
		}
	case 2:
		if s.Task == nil {
			return nil, fmt.Errorf("%w: v2 suite missing task", ErrSuiteInvalid)
		}
		if s.Task.Invoke == "" {
			return nil, fmt.Errorf("%w: v2 suite task.invoke is required", ErrSuiteInvalid)
		}
		if s.Dataset == nil {
			return nil, fmt.Errorf("%w: v2 suite missing dataset", ErrSuiteInvalid)
		}
		switch s.Dataset.Source {
		case "file":
			if s.Dataset.Path == "" {
				return nil, fmt.Errorf("%w: v2 dataset.source=file requires path", ErrSuiteInvalid)
			}
		case "inline":
			if len(s.Dataset.Inline) == 0 {
				return nil, fmt.Errorf("%w: v2 dataset.source=inline requires inline cases", ErrSuiteInvalid)
			}
		case "sampled":
			// online sampling — slice 8 fills in details. Accept here.
		default:
			return nil, fmt.Errorf("%w: unknown dataset.source %q", ErrSuiteInvalid, s.Dataset.Source)
		}
		if s.Trajectory != nil && s.Trajectory.GoalAchieved != nil {
			// goal_achieved_judge is set but template is required (the
			// runner accepts empty template and falls back to a default,
			// but the explicit-empty case is treated as a config error
			// because users typically misspell or forget the field).
			//
			// We accept either an inline rubric (contains "choice_scores")
			// or a bare prompt; only fully empty is rejected.
			if s.Trajectory.GoalAchieved.Template == "" {
				return nil, fmt.Errorf("%w: trajectory.goal_achieved_judge.template is required", ErrSuiteInvalid)
			}
		}
		if s.Trajectory != nil && s.Trajectory.MaxToolCalls < 0 {
			return nil, fmt.Errorf("%w: trajectory.max_tool_calls must be >= 0", ErrSuiteInvalid)
		}
	}
	return &s, nil
}

// Cases materializes the full case list for the suite. v1 converts
// Fixtures; v2 reads the dataset (file or inline). For sampled
// datasets, returns an empty slice — slice 8's sampler populates them
// out-of-band.
func (s *Suite) Cases() ([]Case, error) {
	if s.Version == 1 {
		out := make([]Case, len(s.Fixtures))
		for i, fx := range s.Fixtures {
			out[i] = Case{
				ID:       fx.ID,
				Input:    fx.Prompt,
				Expected: fx.ExpectedOutcome,
				Metadata: map[string]any{
					"agent": fx.Agent,
					"notes": fx.Notes,
				},
			}
		}
		return out, nil
	}
	// v2
	switch s.Dataset.Source {
	case "inline":
		return append([]Case(nil), s.Dataset.Inline...), nil
	case "file":
		path := s.Dataset.Path
		if !filepath.IsAbs(path) && s.sourceDir != "" {
			path = filepath.Join(s.sourceDir, path)
		}
		return loadCasesJSONL(path)
	case "sampled":
		// Slice 8 will populate evals/<suite>/sampled.jsonl out-of-band.
		// Slice 2 reads it the same as a file dataset if it exists,
		// returns empty otherwise.
		if s.Dataset.Path == "" {
			return nil, nil
		}
		path := s.Dataset.Path
		if !filepath.IsAbs(path) && s.sourceDir != "" {
			path = filepath.Join(s.sourceDir, path)
		}
		if _, err := os.Stat(path); errors.Is(err, os.ErrNotExist) {
			return nil, nil
		}
		return loadCasesJSONL(path)
	}
	return nil, fmt.Errorf("eval: unhandled dataset source %q", s.Dataset.Source)
}
