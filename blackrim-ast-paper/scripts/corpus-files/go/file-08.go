package bdmemory

// Reciprocal Rank Fusion (RRF).
//
// Cormack, Clarke & Buettcher (2009): "Reciprocal rank fusion outperforms
// Condorcet and individual rank learning methods" (SIGIR '09). For each
// document d, the fused score is:
//
//	RRF(d) = sum over rankers r of  1 / (k + rank_r(d))
//
// where rank_r(d) is d's 1-based position in ranker r's result list (a
// document missing from r contributes nothing). k=60 is the value
// recommended by Cormack et al. and is the default below.
//
// RRF has two properties that matter for hybrid retrieval:
//
//  1. Score-free fusion. We don't have to normalize BM25's TF-IDF score
//     to be comparable with cosine similarity from embeddings — only
//     ranks combine.
//  2. Robust to outlier rankers. A ranker that gets one query badly
//     wrong barely moves the fused order; majority rule wins.

// DefaultRRFK is the Cormack et al. (2009) recommended constant. Higher
// k flattens the reciprocal curve (less weight to top ranks); lower k
// makes the top of each list dominate. 60 is the empirically robust
// choice.
const DefaultRRFK = 60

// FuseRRF combines multiple ranked lists into a single ScoredMemory list
// using Reciprocal Rank Fusion.
//
// Each input list is a slice of memories ordered best-first; positions
// matter, not the per-list scores. Memories appearing in multiple lists
// have their reciprocal-rank contributions summed.
//
// k controls the reciprocal curve; pass DefaultRRFK (60) for the
// canonical RRF behavior.
func FuseRRF(k int, lists ...[]Memory) []ScoredMemory {
	if k <= 0 {
		k = DefaultRRFK
	}
	if len(lists) == 0 {
		return nil
	}

	// Map memory slug → accumulator. Slug is the stable identifier;
	// we resolve back to Memory via the first list that contained it.
	type accum struct {
		mem   Memory
		score float64
	}
	acc := map[string]*accum{}

	for _, list := range lists {
		for rank, m := range list {
			// rank is 0-based here; RRF formula uses 1-based.
			contrib := 1.0 / float64(k+rank+1)
			if a, ok := acc[m.Slug]; ok {
				a.score += contrib
			} else {
				acc[m.Slug] = &accum{mem: m, score: contrib}
			}
		}
	}

	out := make([]ScoredMemory, 0, len(acc))
	for _, a := range acc {
		out = append(out, ScoredMemory{Memory: a.mem, Score: a.score})
	}
	sortScored(out)
	return out
}

// FuseRRFScored is the ScoredMemory-list variant. The fused result
// drops the per-input scores in favor of the RRF combined score; the
// rank within each input list is what matters for fusion.
func FuseRRFScored(k int, lists ...[]ScoredMemory) []ScoredMemory {
	memLists := make([][]Memory, len(lists))
	for i, l := range lists {
		memLists[i] = MemoriesFromScored(l)
	}
	return FuseRRF(k, memLists...)
}
