package compress

import (
	"bytes"
	"fmt"
	"regexp"
	"strings"
)

// GitLog compresses `git log` output to one line per commit:
//
//	abc1234  subject line
//
// Dropped: author email, long timestamp, blank lines, body paragraphs
// beyond the subject. Effective for default `git log` output
// (commit + Author + Date + blank + subject indented by 4 spaces).
// If the input doesn't parse as that format we pass it through
// unchanged so we never produce garbled output.
//
// Handles both decorated (`--decorate=short`) and plain log output.
func GitLog(input []byte, opts Options) ([]byte, error) {
	raw := string(input)
	if raw == "" {
		return []byte{}, nil
	}

	// Split into commit chunks — each chunk starts at a `commit <sha>`
	// header line.
	commitHeader := regexp.MustCompile(`(?m)^commit ([0-9a-f]{7,64})\b`)
	idxs := commitHeader.FindAllStringSubmatchIndex(raw, -1)
	if len(idxs) == 0 {
		return input, nil
	}

	max := EffectiveMax(opts, 60)
	var out bytes.Buffer
	shown := 0
	for i, m := range idxs {
		if shown >= max {
			fmt.Fprintf(&out, "... (+%d more commits)\n", len(idxs)-shown)
			break
		}
		sha := raw[m[2]:m[3]][:7]

		// Chunk runs from end-of-header to the next commit header
		// (or EOF).
		chunkStart := m[1]
		chunkEnd := len(raw)
		if i+1 < len(idxs) {
			chunkEnd = idxs[i+1][0]
		}
		chunk := raw[chunkStart:chunkEnd]

		// The subject line is the first non-blank line after the
		// header block (Author/Date/blank). Scan line-by-line.
		subject := extractSubject(chunk)
		if subject == "" {
			subject = "(no subject)"
		}
		fmt.Fprintf(&out, "%s  %s\n", sha, subject)
		shown++
	}
	return out.Bytes(), nil
}

// extractSubject returns the first non-header, non-blank, non-indented
// line from a git-log commit body. The default log body has indented
// subject lines (four spaces); other formats have unindented ones.
func extractSubject(chunk string) string {
	for _, line := range strings.Split(chunk, "\n") {
		if strings.HasPrefix(line, "Author:") ||
			strings.HasPrefix(line, "AuthorDate:") ||
			strings.HasPrefix(line, "Commit:") ||
			strings.HasPrefix(line, "CommitDate:") ||
			strings.HasPrefix(line, "Date:") ||
			strings.HasPrefix(line, "Merge:") ||
			strings.HasPrefix(line, "Refs:") {
			continue
		}
		trim := strings.TrimSpace(line)
		if trim == "" {
			continue
		}
		// Stop before trailing sections that repeat across commits.
		if strings.HasPrefix(trim, "diff --git") {
			return ""
		}
		return trim
	}
	return ""
}

func init() { Register("git-log", GitLog) }
