package compress

import (
	"bytes"
	"fmt"
	"sort"
	"strings"
)

// Grep compresses `grep -n -r` / `rg` output by grouping by file and
// capping matches per file. Output format:
//
//	path/to/file.go  (N matches)
//	  12:  first matching line trimmed to ~80 chars
//	  48:  second ...
//	  ... (+K more)
//	path/to/other.go (1 match)
//	  77:  line
//
// Recognizes two common shapes:
//
//	"path:lineno:content"  (grep -n / ripgrep default)
//	"path-lineno-content"  (grep -A/-B/-C context)
//
// Falls through unchanged if no lines parse.
func Grep(input []byte, opts Options) ([]byte, error) {
	lines := splitLines(input)
	if len(lines) == 0 {
		return []byte{}, nil
	}

	type match struct {
		lineno  string
		content string
	}
	groups := map[string][]match{}
	paths := []string{}
	parsed := 0

	for _, line := range lines {
		path, lineno, content, ok := parseGrepLine(line)
		if !ok {
			continue
		}
		if _, seen := groups[path]; !seen {
			paths = append(paths, path)
		}
		groups[path] = append(groups[path], match{lineno, content})
		parsed++
	}

	if parsed == 0 {
		return input, nil
	}

	max := EffectiveMax(opts, 80)
	perFileCap := 5
	if len(paths) > 0 && max/len(paths) > perFileCap {
		perFileCap = max / len(paths)
	}

	sort.Strings(paths)
	var out bytes.Buffer
	total := 0
	for _, path := range paths {
		matches := groups[path]
		plural := "match"
		if len(matches) != 1 {
			plural = "matches"
		}
		fmt.Fprintf(&out, "%s  (%d %s)\n", path, len(matches), plural)
		shown := matches
		if len(shown) > perFileCap {
			shown = shown[:perFileCap]
		}
		for _, m := range shown {
			content := m.content
			if len(content) > 80 {
				content = content[:77] + "..."
			}
			fmt.Fprintf(&out, "  %s:  %s\n", m.lineno, content)
		}
		if len(matches) > len(shown) {
			fmt.Fprintf(&out, "  ... (+%d more)\n", len(matches)-len(shown))
		}
		total += len(matches)
	}
	fmt.Fprintf(&out, "Total: %d match(es) across %d file(s)\n", total, len(paths))
	return out.Bytes(), nil
}

// parseGrepLine tries the "path:N:content" and "path-N-content" shapes.
// Returns (path, lineno, content, true) on match. Rejects lines that
// don't start with a sensible path char.
func parseGrepLine(line string) (string, string, string, bool) {
	if line == "" || line[0] == ' ' || line[0] == '\t' {
		return "", "", "", false
	}
	for _, sep := range []byte{':', '-'} {
		i := strings.IndexByte(line, sep)
		if i <= 0 {
			continue
		}
		rest := line[i+1:]
		j := strings.IndexByte(rest, sep)
		if j <= 0 {
			continue
		}
		lineno := rest[:j]
		if !allDigits(lineno) {
			continue
		}
		return line[:i], lineno, rest[j+1:], true
	}
	return "", "", "", false
}

func allDigits(s string) bool {
	if s == "" {
		return false
	}
	for i := 0; i < len(s); i++ {
		if s[i] < '0' || s[i] > '9' {
			return false
		}
	}
	return true
}

func init() { Register("grep", Grep) }
