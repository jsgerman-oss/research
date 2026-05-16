package eval

import (
	"context"
	"crypto/rand"
	"encoding/base32"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"

	"github.com/auditidentity/blackrim.dev/internal/calibration"
	"github.com/auditidentity/blackrim.dev/internal/pricing"
	"github.com/auditidentity/blackrim.dev/internal/scorer"
	// Side-effect imports register every scorer family with the
	// scorer registry. The runner accepts any registered scorer by
	// name, so importing these here is what makes BuildScorers see
	// "levenshtein", "factuality", "embedding_similarity", etc.
	_ "github.com/auditidentity/blackrim.dev/internal/scorer/embedding"
	_ "github.com/auditidentity/blackrim.dev/internal/scorer/heuristic"
	llmscorer "github.com/auditidentity/blackrim.dev/internal/scorer/llm"
	"github.com/auditidentity/blackrim.dev/internal/scorer/pairwise"
	"github.com/auditidentity/blackrim.dev/internal/scorer/trajectory"
)

// PairwiseJudgeFactory is the seam by which the eval runner obtains a
// concrete pairwise.PairwiseJudge for a `kind: pairwise` scorer.
//
// Production: cmd/gt eval wires this to a closure that wraps the
// process-wide AnthropicJudge in a llmscorer.PairwiseAnthropicJudge.
// Tests: override with a closure returning a mock judge — the eval-
// runner integration test in pairwise_judge_test.go does exactly this.
//
// Returning a nil judge with no error signals "no pairwise judge
// configured"; the runner errors out at BuildScorers time so a
// misconfigured suite fails at load, not on the first case.
var PairwiseJudgeFactory = func(spec *llmscorer.Spec) (pairwise.PairwiseJudge, error) {
	j := llmscorer.CurrentDefaultJudge()
	if j == nil {
		return nil, nil
	}
	anth, ok := j.(*llmscorer.AnthropicJudge)
	if !ok {
		// CachingJudge or another adapter — pairwise needs the raw
		// HTTP transport. The caller can wire a custom factory if
		// they need a different adapter.
		return nil, fmt.Errorf("eval: PairwiseJudgeFactory: default judge is %T, want *llmscorer.AnthropicJudge", j)
	}
	return llmscorer.NewPairwiseAnthropicJudge(spec, anth)
}

// TaskInvoker produces an Output for a Case. Implementations include:
//   - ReplayInvoker: returns the Case's pre-captured Output (test +
//     replay mode).
//   - (slice 6) Production invokers: Anthropic direct, harness, codex.
type TaskInvoker interface {
	Invoke(ctx context.Context, in TaskInput) (TaskOutput, error)
}

// TaskInput is the input to an invoker.
type TaskInput struct {
	Case     Case
	Task     Task
	Metadata map[string]any
	// SessionID is the audit-log session this case's invocation should
	// emit under. The runner injects a per-case ID before invocation;
	// production invokers (slice 6+) propagate it into spawned agents
	// so the audit trail is filterable post-hoc.
	SessionID string
}

// TaskOutput is the result of an invocation.
type TaskOutput struct {
	Output       string
	LatencyMs    int64
	InputTokens  int64
	OutputTokens int64
	// CacheReadInputTokens is Anthropic prompt-cache hit tokens
	// (charged at 0.1x of standard input rate). Optional; production
	// invokers populate from response.usage.cache_read_input_tokens.
	CacheReadInputTokens int64
	// CacheCreationInputTokens is Anthropic prompt-cache write tokens
	// (charged at 1.25x). Optional; populate from
	// response.usage.cache_creation_input_tokens.
	CacheCreationInputTokens int64
	// Provider is the LLM vendor (e.g. "anthropic", "openai"). When
	// empty, the runner falls back to deriving from the suite's
	// task.model prefix (claude-* → anthropic, gpt-* → openai), or to
	// pricing.DefaultProvider when both are empty. Only used for cost
	// attribution.
	Provider string
	// Model is the model id used for this invocation (e.g.
	// "claude-haiku-4-5"). When empty, the runner falls back to
	// Suite.Task.Model. Only used for cost attribution — invokers can
	// override the suite-level model on a per-case basis if needed.
	Model string
	// SessionID is the actual session ID the invocation ran under.
	// Replay invokers reflect TaskInput.SessionID; production invokers
	// may overwrite it with a runtime-assigned value.
	SessionID string
}

// ReplayInvoker returns Case.Output unchanged. Used for replay-mode
// suites and for tests. Errors when Case.Output is empty (caller
// should arrange the output ahead of time).
type ReplayInvoker struct{}

// Invoke returns the case's pre-captured output.
func (ReplayInvoker) Invoke(_ context.Context, in TaskInput) (TaskOutput, error) {
	if in.Case.Output == "" {
		return TaskOutput{}, fmt.Errorf("replay: case %q has no output", in.Case.ID)
	}
	return TaskOutput{Output: in.Case.Output, SessionID: in.SessionID}, nil
}

// Runner runs a Suite end-to-end and persists results.
type Runner struct {
	// Suite is the loaded suite definition.
	Suite *Suite
	// Invoker drives the task per case.
	Invoker TaskInvoker
	// Scorers is the configured scorer set, in order. Built by
	// BuildScorers from Suite.Scorers.
	Scorers []scorer.Scorer
	// CommitSHA pins the run to a commit (set by the CLI).
	CommitSHA string
	// EvalRunsPath is the JSONL output path. EvalRunPath() helper
	// builds the canonical one.
	EvalRunsPath string
	// AuditLogPath is the .beads/telemetry/audit.jsonl path used by
	// RunTrajectory when a case has no inline trajectory. Optional —
	// empty path skips disk reads (test path / inline-only suites).
	AuditLogPath string
	// Now is injected for deterministic test timestamps. Defaults to
	// time.Now if nil.
	Now func() time.Time
	// NewSessionID returns the session id assigned to a case before
	// invocation. Defaults to a random short id; tests inject a
	// deterministic counter.
	NewSessionID func(c Case) string
	// Concurrency caps how many cases run in parallel. <= 0 falls back
	// to defaultConcurrency. The CLI exposes this via
	// `gt eval run --concurrency N`. Case order in the output is
	// preserved regardless of concurrency.
	Concurrency int
	// AttributionSink, when non-nil, receives one Apply call per used
	// memory ID per case after RunSuite/RunTrajectory aggregates. Wires
	// the eval-outcome → memory-record feedback loop (blackrim-cwu).
	// Nil disables attribution silently — replay-only suites that don't
	// declare used memories simply produce zero writes.
	AttributionSink AttributionSink
	// CalibrationRoot, when non-empty, is the project root under which
	// per-judge calibration cases are appended after a successful run
	// (evals/_calibration/<judge>/cases.jsonl). Empty disables the
	// write — replay tests and synthetic CI sweeps that would pollute
	// the calibration store opt out by leaving this unset. Honoring
	// BLACKRIM_CALIBRATION_OFF=1 also disables. blackrim-k2nm.
	CalibrationRoot string
}

// defaultConcurrency is the per-suite worker pool size when
// Runner.Concurrency is unset. Picked to give >5x speedup on bulk
// LLM-bound suites without hammering rate limits at single-tenant
// API tiers. Operators with higher tiers can raise; tests set it
// to 1 to preserve sequential semantics.
const defaultConcurrency = 8

// SuiteResult is the aggregate outcome of running a suite.
type SuiteResult struct {
	RunID     string
	Suite     string
	CommitSHA string
	Cases     []EvalRun
	// MeanByScorer maps scorer name → mean Score.Value across cases
	// where the scorer ran successfully.
	MeanByScorer map[string]float64
	// PairwiseMetrics holds the terminal swap-test snapshots, one
	// EvalRun per kind:pairwise scorer. Rows have Kind="pairwise_metrics"
	// and the same RunID as the parent SuiteResult so the pair is
	// rejoinable. Empty when the suite has no kind:pairwise scorers.
	PairwiseMetrics []EvalRun
	// MeanOverall is the mean of MeanByScorer values (equally weighted
	// by scorer, not by case).
	MeanOverall float64
	// PctCorrect is the fraction of cases where the per-case mean
	// score >= 0.5.
	PctCorrect float64
	// GateResult is populated when Suite.Gates is non-nil.
	GateResult *GateResult
	// TotalCostUSD is the sum of per-case cost_usd over Cases. Zero
	// when no case carries token counts (replay-only suite without a
	// pre-captured cost). Cost is computed at run time using
	// internal/pricing rates; persisted on each EvalRun for later
	// recomputation under a different rate card if needed.
	TotalCostUSD float64
}

// GateResult records pass/fail against Suite.Gates.
type GateResult struct {
	Passed        bool
	FailedReasons []string
}

// BuildScorers materializes scorer instances from a Suite's scorer
// configs. Heuristic and embedding scorers come from the registry;
// LLM scorers with kind=llm look up the registry too (which returns
// a Classifier with the embedded template); kind=rubric loads inline
// YAML via llm.LoadCustom; kind=pairwise builds a llm.PairwiseScorer
// over a llm.PairwiseAnthropicJudge wrapped in pairwise.SwapScorer.
//
// Suite-level controls (e.g., Pairwise.SwapTest) are not consulted
// here — call BuildScorersForSuite when those matter. BuildScorers
// runs every kind:pairwise scorer with the swap test ENABLED (the
// safe default).
func BuildScorers(configs []ScorerConfig) ([]scorer.Scorer, error) {
	return BuildScorersForSuite(configs, nil)
}

// BuildScorersForSuite is the suite-aware constructor. The pairwise
// argument carries the suite's PairwiseSuiteConfig (or nil) so
// kind:pairwise scorers honor the suite-level swap-test toggle.
func BuildScorersForSuite(configs []ScorerConfig, pairwiseCfg *PairwiseSuiteConfig) ([]scorer.Scorer, error) {
	out := make([]scorer.Scorer, 0, len(configs))
	for _, cfg := range configs {
		s, err := buildScorer(cfg, pairwiseCfg)
		if err != nil {
			return nil, err
		}
		out = append(out, s)
	}
	return out, nil
}

func buildScorer(cfg ScorerConfig, pairwiseCfg *PairwiseSuiteConfig) (scorer.Scorer, error) {
	switch cfg.Kind {
	case "heuristic", "embedding", "llm":
		// Use Func override if provided, else fall back to Name.
		key := cfg.Func
		if key == "" {
			key = cfg.Name
		}
		s, err := scorer.Lookup(key)
		if err != nil {
			return nil, fmt.Errorf("eval: scorer %q (kind=%s): %w", cfg.Name, cfg.Kind, err)
		}
		if len(cfg.Config) > 0 {
			c, ok := s.(scorer.Configurable)
			if !ok {
				return nil, fmt.Errorf("eval: scorer %q (kind=%s, func=%s) does not accept a config block", cfg.Name, cfg.Kind, key)
			}
			if err := c.Configure(cfg.Config); err != nil {
				return nil, fmt.Errorf("eval: scorer %q (kind=%s, func=%s) config: %w", cfg.Name, cfg.Kind, key, err)
			}
		}
		return s, nil
	case "rubric":
		if strings.TrimSpace(cfg.Template) == "" {
			return nil, fmt.Errorf("eval: scorer %q kind=rubric requires inline template", cfg.Name)
		}
		// LoadCustom expects a full Spec YAML — wrap the inline prompt
		// + a yes/no choice_scores default if the user didn't include
		// one. Convention: bare-prompt rubrics get a Yes/No binary
		// schema. Power users provide a full Spec under template:.
		spec := buildRubricSpec(cfg)
		c, err := llmscorer.LoadCustom([]byte(spec), nil)
		if err != nil {
			return nil, fmt.Errorf("eval: scorer %q kind=rubric: %w", cfg.Name, err)
		}
		return c, nil
	case "pairwise":
		spec, err := resolvePairwiseSpec(cfg)
		if err != nil {
			return nil, fmt.Errorf("eval: scorer %q kind=pairwise: %w", cfg.Name, err)
		}
		if cfg.JudgeModel != "" {
			spec.JudgeModel = cfg.JudgeModel
		}
		judge, err := PairwiseJudgeFactory(spec)
		if err != nil {
			return nil, fmt.Errorf("eval: scorer %q kind=pairwise: judge: %w", cfg.Name, err)
		}
		if judge == nil {
			return nil, fmt.Errorf("eval: scorer %q kind=pairwise: no PairwiseJudge configured (set llm.SetDefaultJudge or override eval.PairwiseJudgeFactory)", cfg.Name)
		}
		return llmscorer.NewPairwiseScorerFromSpec(cfg.Name, spec, judge, pairwiseCfg.SwapTestEnabled())
	default:
		return nil, fmt.Errorf("eval: unknown scorer kind %q", cfg.Kind)
	}
}

// resolvePairwiseSpec finds the rubric Spec for a kind:pairwise scorer.
// Resolution order:
//  1. cfg.Template references an embedded pairwise template by name
//     (e.g. "factuality_pairwise") — lookup via
//     llmscorer.EmbeddedPairwiseTemplate.
//  2. cfg.Template is inline YAML (contains "choice_scores") — parse
//     via ParseSpec.
//  3. cfg.Template is empty — fall back to the bundled
//     "factuality_pairwise" template.
func resolvePairwiseSpec(cfg ScorerConfig) (*llmscorer.Spec, error) {
	t := strings.TrimSpace(cfg.Template)
	if t == "" {
		spec, ok := llmscorer.EmbeddedPairwiseTemplate("factuality_pairwise")
		if !ok {
			return nil, fmt.Errorf("default factuality_pairwise template not embedded — check init order")
		}
		return spec, nil
	}
	// Treat single-line, no-newline, no-colon strings as a template
	// name lookup.
	if !strings.ContainsAny(t, "\n:") {
		spec, ok := llmscorer.EmbeddedPairwiseTemplate(t)
		if !ok {
			return nil, fmt.Errorf("unknown embedded pairwise template %q", t)
		}
		return spec, nil
	}
	// Otherwise, treat as inline YAML.
	spec, err := llmscorer.ParseSpec([]byte(cfg.Template))
	if err != nil {
		return nil, fmt.Errorf("inline rubric: %w", err)
	}
	return spec, nil
}

// buildRubricSpec wraps a bare prompt into a Spec YAML when the
// template field doesn't already declare name/choice_scores. Detects
// "this is a Spec" via the presence of `choice_scores:`.
func buildRubricSpec(cfg ScorerConfig) string {
	t := cfg.Template
	if strings.Contains(t, "choice_scores") {
		return t
	}
	// Wrap a bare prompt with a Yes/No binary schema and the user-
	// supplied prompt body.
	return fmt.Sprintf(`name: %s
prompt: |
%s
choice_scores:
  "Yes": 1.0
  "No": 0.0
use_cot: true
`, cfg.Name, indent(t, "  "))
}

func indent(s, prefix string) string {
	lines := strings.Split(s, "\n")
	for i, line := range lines {
		lines[i] = prefix + line
	}
	return strings.Join(lines, "\n")
}

// applyTokenTelemetry copies the token / latency fields from a
// TaskOutput onto the EvalRun. Only non-zero counts are persisted —
// JSONL readers infer "no telemetry" from absence rather than zero.
func applyTokenTelemetry(run *EvalRun, out TaskOutput) {
	if out.LatencyMs > 0 {
		v := out.LatencyMs
		run.LatencyMs = &v
	}
	if out.InputTokens > 0 {
		v := out.InputTokens
		run.InputTokens = &v
	}
	if out.OutputTokens > 0 {
		v := out.OutputTokens
		run.OutputTokens = &v
	}
	if out.CacheReadInputTokens > 0 {
		v := out.CacheReadInputTokens
		run.CacheReadInputTokens = &v
	}
	if out.CacheCreationInputTokens > 0 {
		v := out.CacheCreationInputTokens
		run.CacheCreationInputTokens = &v
	}
}

// computeCaseCost returns the dollar cost of one case at list-price
// rates for (provider, model). Cache-read tokens are billed at 0.1× of
// the model's input rate (Anthropic's published prompt-cache hit
// discount); cache-creation tokens at 1.25× (write-tier surcharge).
// The provider and model arguments are matched case-insensitively
// against internal/pricing's table; if the (provider, model) key is
// unknown, the framework default is used (the call still produces a
// number — flagged as estimated by pricing.LookupOrDefault — instead
// of zero, which would silently misreport the run as free).
//
// Zero in/out/cache tokens → zero cost. The function never errors;
// missing rate cards fall back to the default and missing tokens
// trivially zero out their term.
func computeCaseCost(provider, model string, in, out, cacheRead, cacheCreate int64) float64 {
	if in == 0 && out == 0 && cacheRead == 0 && cacheCreate == 0 {
		return 0
	}
	mp, _ := pricing.LookupOrDefault(provider, model)
	cost := mp.CostFor(in, out)
	// Cache-read: 10% of input rate (Anthropic prompt-cache hit).
	cost += float64(cacheRead) * mp.InputPer1MTokens / 1_000_000.0 * 0.1
	// Cache-creation: 125% of input rate (Anthropic prompt-cache write).
	cost += float64(cacheCreate) * mp.InputPer1MTokens / 1_000_000.0 * 1.25
	return cost
}

// inferProvider returns a provider id from a model name when the
// invoker didn't supply one. claude-* → anthropic, gpt-* → openai,
// otherwise the framework default. Centralized so cost attribution is
// consistent across replay/invoke/batch paths.
func inferProvider(model string) string {
	m := strings.ToLower(strings.TrimSpace(model))
	switch {
	case strings.HasPrefix(m, "claude"):
		return "anthropic"
	case strings.HasPrefix(m, "gpt"):
		return "openai"
	default:
		return pricing.DefaultProvider
	}
}

// resolveCostAttribution picks the (provider, model) pair to bill this
// case under. Prefers TaskOutput-supplied values (production invokers
// may overwrite per-case), falls back to Suite.Task.Model, then to the
// pricing default. Returned values are normalized (lowercase, trimmed).
func (r *Runner) resolveCostAttribution(out TaskOutput) (provider, model string) {
	model = strings.ToLower(strings.TrimSpace(out.Model))
	provider = strings.ToLower(strings.TrimSpace(out.Provider))
	if model == "" && r.Suite != nil && r.Suite.Task != nil {
		model = strings.ToLower(strings.TrimSpace(r.Suite.Task.Model))
	}
	if model == "" {
		model = pricing.DefaultModel
	}
	if provider == "" {
		provider = inferProvider(model)
	}
	return provider, model
}

// RunSuite executes every case in the suite, scores each, persists
// results, and returns aggregates. Cases run concurrently, bounded by
// Runner.Concurrency (default 8); output ordering matches input
// ordering regardless of completion order.
func (r *Runner) RunSuite(ctx context.Context) (*SuiteResult, error) {
	if r.Suite == nil {
		return nil, errors.New("eval: runner: nil suite")
	}
	if r.Invoker == nil {
		return nil, errors.New("eval: runner: nil invoker")
	}
	cases, err := r.Suite.Cases()
	if err != nil {
		return nil, err
	}
	if len(cases) == 0 {
		return nil, errors.New("eval: runner: suite has no cases")
	}

	now := r.now
	runID := newRunID()
	result := &SuiteResult{
		RunID:        runID,
		Suite:        r.Suite.Name,
		CommitSHA:    r.CommitSHA,
		Cases:        make([]EvalRun, len(cases)),
		MeanByScorer: make(map[string]float64),
	}

	// Each goroutine writes into its own slot of result.Cases (indexed
	// by i) — no shared map mutation. Aggregation runs single-threaded
	// after the pool drains, so the existing scorer-mean math doesn't
	// need locking.
	runOne := func(i int, c Case) {
		evalRun := EvalRun{
			TS:        now(),
			RunID:     runID,
			Kind:      "suite",
			Suite:     r.Suite.Name,
			CommitSHA: r.CommitSHA,
			CaseID:    c.ID,
			Input:     c.Input,
			Expected:  c.Expected,
			Metadata:  c.Metadata,
		}
		var task Task
		if r.Suite.Task != nil {
			task = *r.Suite.Task
		}
		out, invokeErr := r.Invoker.Invoke(ctx, TaskInput{Case: c, Task: task})
		if invokeErr != nil {
			evalRun.Error = "invoke: " + invokeErr.Error()
			result.Cases[i] = evalRun
			return
		}
		evalRun.Output = out.Output
		applyTokenTelemetry(&evalRun, out)
		provider, model := r.resolveCostAttribution(out)
		evalRun.Provider = provider
		evalRun.Model = model
		evalRun.CostUSD = computeCaseCost(provider, model,
			out.InputTokens, out.OutputTokens,
			out.CacheReadInputTokens, out.CacheCreationInputTokens)

		scoresIn := scorer.ScorerInput{
			Input:    c.Input,
			Output:   out.Output,
			Expected: c.Expected,
			Metadata: c.Metadata,
		}
		caseScores := make([]CaseScore, 0, len(r.Scorers))
		for _, s := range r.Scorers {
			score, err := s.Score(ctx, scoresIn)
			if err != nil {
				caseScores = append(caseScores, CaseScore{
					Name:     s.Name(),
					Value:    0,
					Metadata: map[string]any{"error": err.Error()},
				})
				continue
			}
			caseScores = append(caseScores, CaseScore{
				Name:      score.Name,
				Value:     score.Value,
				Rationale: score.Rationale,
				Metadata:  score.Metadata,
			})
		}
		evalRun.Scores = caseScores
		result.Cases[i] = evalRun
	}

	r.runConcurrent(ctx, len(cases), func(i int) {
		runOne(i, cases[i])
	})

	// Aggregate (single-threaded — concurrency-safe by construction).
	scorerSums := make(map[string]float64)
	scorerCounts := make(map[string]int)
	caseMeanCount := 0
	correctCount := 0
	for _, evalRun := range result.Cases {
		result.TotalCostUSD += evalRun.CostUSD
		if evalRun.Error != "" || len(evalRun.Scores) == 0 {
			continue
		}
		var caseMean float64
		var caseScoreCount int
		for _, s := range evalRun.Scores {
			if errMeta, isErr := s.Metadata["error"]; isErr && errMeta != nil {
				continue
			}
			scorerSums[s.Name] += s.Value
			scorerCounts[s.Name]++
			caseMean += s.Value
			caseScoreCount++
		}
		if caseScoreCount > 0 {
			caseMean /= float64(caseScoreCount)
			caseMeanCount++
			if caseMean >= 0.5 {
				correctCount++
			}
		}
	}
	for name, sum := range scorerSums {
		count := scorerCounts[name]
		if count > 0 {
			result.MeanByScorer[name] = sum / float64(count)
		}
	}
	if len(result.MeanByScorer) > 0 {
		var total float64
		for _, v := range result.MeanByScorer {
			total += v
		}
		result.MeanOverall = total / float64(len(result.MeanByScorer))
	}
	if caseMeanCount > 0 {
		result.PctCorrect = float64(correctCount) / float64(caseMeanCount)
	}

	// Gates
	if r.Suite.Gates != nil {
		result.GateResult = evaluateGates(r.Suite.Gates, result)
	}

	// Snapshot pairwise telemetry — one synthetic EvalRun per pairwise
	// scorer carrying the SwapScorer's terminal Metrics. Lands in the
	// same JSONL stream so per-judge position_flip_rate is observable
	// per run (OQ-E5; §E1.4 / §E6.1 of docs/research/eval-suite-
	// algorithms.md). Snapshot rows have Kind="pairwise_metrics" and
	// share the run_id of the parent suite run; readers filter by Kind.
	pairwiseSnapshots := r.collectPairwiseSnapshots(result.RunID, now())
	result.PairwiseMetrics = pairwiseSnapshots

	// Persist
	if r.EvalRunsPath != "" {
		toPersist := append([]EvalRun(nil), result.Cases...)
		toPersist = append(toPersist, pairwiseSnapshots...)
		if err := AppendRuns(r.EvalRunsPath, toPersist); err != nil {
			return result, err
		}
	}

	// Calibration data write (blackrim-k2nm). Per-case rows for ECE /
	// reliability-diagram computation under evals/_calibration/<judge>.
	// Best-effort — a write failure logs nothing here (the runner has
	// no logger); the operator surface is `gt eval show --calibration`,
	// which simply reports the cases it can find. Skipping this branch
	// is the right behavior for replay tests and synthetic CI sweeps
	// (CalibrationRoot left unset).
	if r.CalibrationRoot != "" && !calibration.CalibrationDisabled() {
		writeCalibrationCases(r.CalibrationRoot, result)
	}

	// Attribution sink (blackrim-cwu). Run AFTER persist so a sink
	// failure doesn't strand the run record on disk; the caller can
	// always re-attribute from the persisted run via gt memory attribute.
	if r.AttributionSink != nil {
		_, _ = AttributeSuiteResult(r.AttributionSink, result)
	}

	return result, nil
}

// collectPairwiseSnapshots inspects r.Scorers for *llmscorer.PairwiseScorer
// instances and emits one EvalRun per scorer carrying the terminal
// swap-test Metrics. Returns nil when no pairwise scorers are present.
//
// The snapshot is the closing telemetry for the run — readers (e.g.
// `gt eval show --pairwise`) filter on Kind="pairwise_metrics" + RunID
// to find it. Per-judge position_flip_rate lands here.
func (r *Runner) collectPairwiseSnapshots(runID string, ts time.Time) []EvalRun {
	if len(r.Scorers) == 0 {
		return nil
	}
	var out []EvalRun
	for _, s := range r.Scorers {
		ps, ok := s.(*llmscorer.PairwiseScorer)
		if !ok {
			continue
		}
		m := ps.Metrics()
		out = append(out, EvalRun{
			TS:        ts,
			RunID:     runID,
			Kind:      "pairwise_metrics",
			Suite:     r.Suite.Name,
			CommitSHA: r.CommitSHA,
			CaseID:    ps.Name(),
			Metadata: map[string]any{
				"scorer":              ps.Name(),
				"judge_name":          m.JudgeName,
				"total":               m.Total,
				"consistent_verdicts": m.ConsistentVerdicts,
				"position_flip_count": m.PositionFlipCount,
				"position_flip_rate":  m.PositionFlipRate,
				"error_count":         m.ErrorCount,
			},
		})
	}
	return out
}

// writeCalibrationCases extracts (predicted_prob, observed_outcome)
// rows from a SuiteResult and appends them to the per-judge JSONL
// stores. Grouped by judge so each judge's store stays isolated.
//
// The function never returns an error — partial writes are tolerated;
// the calibration surface degrades gracefully when a judge directory
// is unwritable. The runner's hot path keeps working.
func writeCalibrationCases(root string, result *SuiteResult) {
	cases := make([]calibration.CaseLike, 0, len(result.Cases))
	for _, r := range result.Cases {
		if r.Error != "" {
			continue
		}
		scores := make([]calibration.ScoreLike, 0, len(r.Scores))
		for _, s := range r.Scores {
			scores = append(scores, calibration.ScoreLike{
				Name:      s.Name,
				Value:     s.Value,
				Rationale: s.Rationale,
				Metadata:  s.Metadata,
			})
		}
		cases = append(cases, calibration.CaseLike{
			CaseID:   r.CaseID,
			Suite:    r.Suite,
			Expected: r.Expected,
			Output:   r.Output,
			TS:       r.TS,
			Scores:   scores,
		})
	}
	calibCases := calibration.ExtractCases(cases)
	if len(calibCases) == 0 {
		return
	}
	// Group by judge so we open one file per judge.
	byJudge := make(map[string][]calibration.CalibrationCase)
	for _, cc := range calibCases {
		byJudge[cc.Judge] = append(byJudge[cc.Judge], cc)
	}
	for judge, cs := range byJudge {
		_ = calibration.AppendCases(root, judge, cs)
	}
}

// runConcurrent runs f(i) for i in [0, n) with at most
// r.effectiveConcurrency() goroutines in flight. Returns when every
// invocation has completed. Uses a buffered-channel semaphore +
// sync.WaitGroup; cancellation is honored via ctx.Done().
//
// f MUST be safe to call from multiple goroutines (no shared mutable
// state across calls). The runner's case-loop satisfies this by
// writing into a pre-sized Cases slice indexed by i.
func (r *Runner) runConcurrent(ctx context.Context, n int, f func(i int)) {
	if n == 0 {
		return
	}
	// effectiveConcurrency always returns >= 1 (defaultConcurrency = 8
	// or the operator-supplied positive value), so we don't re-clamp.
	conc := r.effectiveConcurrency()
	if conc > n {
		conc = n
	}
	// Sequential fast path: skip goroutine overhead when conc == 1.
	// Tests and small suites benefit; behavior is identical.
	if conc == 1 {
		for i := 0; i < n; i++ {
			if ctx.Err() != nil {
				return
			}
			f(i)
		}
		return
	}
	sem := make(chan struct{}, conc)
	var wg sync.WaitGroup
	for i := 0; i < n; i++ {
		// Honor cancellation between dispatches — already-running
		// goroutines see ctx via their own callbacks.
		select {
		case <-ctx.Done():
			wg.Wait()
			return
		case sem <- struct{}{}:
		}
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			defer func() { <-sem }()
			f(i)
		}(i)
	}
	wg.Wait()
}

// effectiveConcurrency returns Runner.Concurrency clamped to a
// sensible default. Zero or negative falls back to defaultConcurrency.
func (r *Runner) effectiveConcurrency() int {
	if r.Concurrency > 0 {
		return r.Concurrency
	}
	return defaultConcurrency
}

func evaluateGates(g *Gates, r *SuiteResult) *GateResult {
	out := &GateResult{Passed: true}
	if g.MinMean > 0 && r.MeanOverall < g.MinMean {
		out.Passed = false
		out.FailedReasons = append(out.FailedReasons,
			fmt.Sprintf("mean %.3f below min_mean %.3f", r.MeanOverall, g.MinMean))
	}
	if g.MinPctCorrect > 0 && r.PctCorrect < g.MinPctCorrect {
		out.Passed = false
		out.FailedReasons = append(out.FailedReasons,
			fmt.Sprintf("pct_correct %.3f below min_pct_correct %.3f", r.PctCorrect, g.MinPctCorrect))
	}
	for name, gate := range g.PerScorer {
		if mean, ok := r.MeanByScorer[name]; ok {
			if gate.MinMean > 0 && mean < gate.MinMean {
				out.Passed = false
				out.FailedReasons = append(out.FailedReasons,
					fmt.Sprintf("%s mean %.3f below per_scorer min_mean %.3f", name, mean, gate.MinMean))
			}
		}
	}
	return out
}

func (r *Runner) now() time.Time {
	if r.Now != nil {
		return r.Now()
	}
	return time.Now().UTC()
}

// newRunID returns a short URL-safe id for one suite invocation.
func newRunID() string {
	var b [8]byte
	_, _ = rand.Read(b[:])
	return "es-" + strings.ToLower(strings.TrimRight(base32.StdEncoding.EncodeToString(b[:]), "="))
}

// newSessionID returns a short URL-safe session id (used by
// RunTrajectory when Runner.NewSessionID is nil).
func newSessionID() string {
	var b [6]byte
	_, _ = rand.Read(b[:])
	return "ses-" + strings.ToLower(strings.TrimRight(base32.StdEncoding.EncodeToString(b[:]), "="))
}

// BuildTrajectoryScorers materializes trajectory.TrajectoryScorer
// instances from a Suite's TrajectoryConfig. Returns an empty slice if
// cfg is nil. Errors propagate from the GoalAchieved sub-builder.
func BuildTrajectoryScorers(cfg *TrajectoryConfig) ([]trajectory.TrajectoryScorer, error) {
	if cfg == nil {
		return nil, nil
	}
	var out []trajectory.TrajectoryScorer
	if len(cfg.ExpectedRoute) > 0 {
		out = append(out, trajectory.RouteMatchScorer{Expected: append([]string(nil), cfg.ExpectedRoute...)})
	}
	if len(cfg.ForbiddenWorkers) > 0 {
		out = append(out, trajectory.ForbiddenWorkersScorer{Forbidden: append([]string(nil), cfg.ForbiddenWorkers...)})
	}
	if cfg.MaxToolCalls > 0 {
		out = append(out, trajectory.ToolBudgetScorer{Max: cfg.MaxToolCalls})
	}
	if cfg.MustTerminate {
		out = append(out, trajectory.TerminationScorer{})
	}
	if cfg.GoalAchieved != nil {
		s, err := trajectory.NewGoalAchievedScorer(cfg.GoalAchieved.Template, cfg.GoalAchieved.JudgeModel, nil)
		if err != nil {
			return nil, fmt.Errorf("eval: build goal_achieved scorer: %w", err)
		}
		out = append(out, s)
	}
	return out, nil
}

// RunTrajectory executes every case, captures the orchestration tree
// (from Case.Trajectory inline OR by reading AuditLogPath filtered by
// the case's session id), runs trajectory scorers, and persists results
// alongside the trajectory tree in EvalRun.Metadata["trajectory"].
//
// Trajectory scoring is independent of the standard scorer set —
// Runner.Scorers and Suite.Scorers are NOT applied here. Suites that
// want both flow paths run RunSuite and RunTrajectory in sequence on
// the same Runner.
func (r *Runner) RunTrajectory(ctx context.Context) (*SuiteResult, error) {
	if r.Suite == nil {
		return nil, errors.New("eval: trajectory: nil suite")
	}
	if r.Invoker == nil {
		return nil, errors.New("eval: trajectory: nil invoker")
	}
	if r.Suite.Trajectory == nil {
		return nil, errors.New("eval: trajectory: suite has no trajectory: block")
	}
	cases, err := r.Suite.Cases()
	if err != nil {
		return nil, err
	}
	if len(cases) == 0 {
		return nil, errors.New("eval: trajectory: suite has no cases")
	}
	tscorers, err := BuildTrajectoryScorers(r.Suite.Trajectory)
	if err != nil {
		return nil, err
	}
	if len(tscorers) == 0 {
		return nil, errors.New("eval: trajectory: no trajectory scorers configured")
	}

	now := r.now
	runID := newRunID()
	result := &SuiteResult{
		RunID:        runID,
		Suite:        r.Suite.Name,
		CommitSHA:    r.CommitSHA,
		Cases:        make([]EvalRun, len(cases)),
		MeanByScorer: make(map[string]float64),
	}

	runOne := func(i int, c Case) {
		sid := r.assignSessionID(c)
		evalRun := EvalRun{
			TS:        now(),
			RunID:     runID,
			Kind:      "suite",
			Suite:     r.Suite.Name,
			CommitSHA: r.CommitSHA,
			CaseID:    c.ID,
			Input:     c.Input,
			Expected:  c.Expected,
			Metadata:  copyMetadata(c.Metadata),
		}
		if evalRun.Metadata == nil {
			evalRun.Metadata = map[string]any{}
		}
		evalRun.Metadata["session_id"] = sid

		var task Task
		if r.Suite.Task != nil {
			task = *r.Suite.Task
		}
		out, invokeErr := r.Invoker.Invoke(ctx, TaskInput{Case: c, Task: task, SessionID: sid})
		if invokeErr != nil {
			evalRun.Error = "invoke: " + invokeErr.Error()
			result.Cases[i] = evalRun
			return
		}
		evalRun.Output = out.Output
		applyTokenTelemetry(&evalRun, out)
		provider, model := r.resolveCostAttribution(out)
		evalRun.Provider = provider
		evalRun.Model = model
		evalRun.CostUSD = computeCaseCost(provider, model,
			out.InputTokens, out.OutputTokens,
			out.CacheReadInputTokens, out.CacheCreationInputTokens)
		if out.SessionID != "" {
			sid = out.SessionID
			evalRun.Metadata["session_id"] = sid
		}

		traj, terr := r.buildTrajectory(c, sid)
		if terr != nil {
			evalRun.Error = "trajectory: " + terr.Error()
			result.Cases[i] = evalRun
			return
		}
		evalRun.Metadata["trajectory"] = map[string]any{
			"route":       traj.Route,
			"tool_calls":  traj.ToolCalls,
			"workers":     traj.SortedWorkers(),
			"open_spawns": countOpenSpawns(traj),
		}

		scoresIn := scorer.ScorerInput{
			Input:    c.Input,
			Output:   out.Output,
			Expected: c.Expected,
			Metadata: c.Metadata,
		}
		caseScores := make([]CaseScore, 0, len(tscorers))
		for _, ts := range tscorers {
			score, serr := ts.ScoreTrajectory(ctx, traj, scoresIn)
			if serr != nil {
				caseScores = append(caseScores, CaseScore{
					Name:     ts.Name(),
					Value:    0,
					Metadata: map[string]any{"error": serr.Error()},
				})
				continue
			}
			caseScores = append(caseScores, CaseScore{
				Name:      score.Name,
				Value:     score.Value,
				Rationale: score.Rationale,
				Metadata:  score.Metadata,
			})
		}
		evalRun.Scores = caseScores
		result.Cases[i] = evalRun
	}

	r.runConcurrent(ctx, len(cases), func(i int) {
		runOne(i, cases[i])
	})

	// Aggregate (single-threaded — mirrors RunSuite for parity).
	scorerSums := make(map[string]float64)
	scorerCounts := make(map[string]int)
	caseMeanCount := 0
	correctCount := 0
	for _, evalRun := range result.Cases {
		result.TotalCostUSD += evalRun.CostUSD
		if evalRun.Error != "" || len(evalRun.Scores) == 0 {
			continue
		}
		var caseMean float64
		var caseScoreCount int
		for _, s := range evalRun.Scores {
			if errMeta, isErr := s.Metadata["error"]; isErr && errMeta != nil {
				continue
			}
			scorerSums[s.Name] += s.Value
			scorerCounts[s.Name]++
			caseMean += s.Value
			caseScoreCount++
		}
		if caseScoreCount > 0 {
			caseMean /= float64(caseScoreCount)
			caseMeanCount++
			if caseMean >= 0.5 {
				correctCount++
			}
		}
	}
	for name, sum := range scorerSums {
		count := scorerCounts[name]
		if count > 0 {
			result.MeanByScorer[name] = sum / float64(count)
		}
	}
	if len(result.MeanByScorer) > 0 {
		var total float64
		for _, v := range result.MeanByScorer {
			total += v
		}
		result.MeanOverall = total / float64(len(result.MeanByScorer))
	}
	if caseMeanCount > 0 {
		result.PctCorrect = float64(correctCount) / float64(caseMeanCount)
	}

	// Gates apply to trajectory runs the same as standard runs.
	if r.Suite.Gates != nil {
		result.GateResult = evaluateGates(r.Suite.Gates, result)
	}

	if r.EvalRunsPath != "" {
		if err := AppendRuns(r.EvalRunsPath, result.Cases); err != nil {
			return result, err
		}
	}

	// Calibration data write (blackrim-k2nm). Same post-persist
	// position as RunSuite. Trajectory scorers are typically heuristics
	// (route_match, forbidden_workers, tool_budget) that don't carry a
	// judge_model in their metadata, so ExtractCases will silently
	// produce no rows for them — write is still safe to attempt.
	if r.CalibrationRoot != "" && !calibration.CalibrationDisabled() {
		writeCalibrationCases(r.CalibrationRoot, result)
	}

	// Attribution sink (blackrim-cwu). Same post-persist position as
	// RunSuite — see comment there.
	if r.AttributionSink != nil {
		_, _ = AttributeSuiteResult(r.AttributionSink, result)
	}
	return result, nil
}

// assignSessionID returns the session id to assign to a case. Honors
// Runner.NewSessionID override; falls back to a random short id.
func (r *Runner) assignSessionID(c Case) string {
	if r.NewSessionID != nil {
		return r.NewSessionID(c)
	}
	return newSessionID()
}

// buildTrajectory chooses between the inline Case.Trajectory and a
// disk read of AuditLogPath. Inline takes precedence — the test path
// is deterministic.
func (r *Runner) buildTrajectory(c Case, sid string) (*trajectory.Trajectory, error) {
	if len(c.Trajectory) > 0 {
		return trajectory.FromInline(sid, c.Trajectory), nil
	}
	if r.AuditLogPath == "" {
		// No inline data and no audit log — return an empty trajectory
		// rather than an error. Trajectory scorers will score against
		// the empty case (typically 0 for forbidden_workers, etc.).
		return trajectory.FromInline(sid, nil), nil
	}
	return trajectory.ParseAuditLog(r.AuditLogPath, sid)
}

// copyMetadata returns a shallow copy of m so per-case mutation
// (session_id, trajectory) doesn't leak back into the suite's case
// definitions across iterations.
func copyMetadata(m map[string]any) map[string]any {
	if m == nil {
		return nil
	}
	out := make(map[string]any, len(m))
	for k, v := range m {
		out[k] = v
	}
	return out
}

func countOpenSpawns(t *trajectory.Trajectory) int {
	open := 0
	for id := range t.Spawns {
		if _, ok := t.Closes[id]; !ok {
			open++
		}
	}
	return open
}
