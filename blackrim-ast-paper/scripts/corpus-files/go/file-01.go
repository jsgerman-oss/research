// Package main — gt compress structure subcommand.
//
// Emit a structural "map" of a source file — package declaration,
// imports, top-level types / funcs / consts / vars — dropping bodies
// and implementation detail. Useful when an agent needs to know
// "what's in this file" without paying for every line. On a typical
// 500-line Go file the structure map is ~30-60 lines (90-95% saved).
//
// MVP language coverage: Go, via the standard library's go/parser +
// go/ast. The command is designed to dispatch by file extension so
// additional languages (Python, TypeScript, JavaScript) can be added
// as separate functions in follow-up beads without touching the
// command surface.
//
// Files whose extension isn't recognized pass through unchanged
// (same convention as every other `gt compress` filter).
package main

import (
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"io"
	"os"
	"path/filepath"
	"strings"

	"github.com/spf13/cobra"
)

// compressStructureCmd is wired into compressCmd() in compress.go.
func compressStructureCmd() *cobra.Command {
	var path string
	var lang string
	var coverage bool
	var coverageRoot string
	var coverageJSON bool
	var coverageAll bool
	cmd := &cobra.Command{
		Use:   "structure",
		Short: "Emit an AST-derived structural map of a source file [deprecated: use gt outline --bulk]",
		// Deprecated marks this command as superseded. Cobra prints the
		// deprecation notice before running the command, so the user sees it
		// once per invocation without blocking operation (preserved for 1
		// release per spec §A: "backward-compat alias for one release").
		Deprecated: "use `gt outline --bulk <dir>` instead (this alias will be removed in the next release)",
		Long: `Structural summary of a source file — package, imports, top-level
types, funcs, consts, vars. Drops function bodies, inline comments,
and struct-field docstrings. On large files the savings are
dramatic (~75-95% on typical Go / Python / JS / TS files).

Language dispatch is automatic via file extension:

  .go                         Go          (via stdlib go/parser + go/ast)
  .py                         Python      (via python3 -c ast walker)
  .js .jsx .mjs .cjs          JavaScript  (via npx acorn ESTree walker)
  .ts .tsx                    TypeScript  (via tools/structure-ts/ + tsc)
  other                       —           (pass-through)

--lang forces a specific parser regardless of extension. Useful
when the file has no extension or a non-standard one.

Files that don't parse (syntax errors, incomplete source) fall
back to pass-through so a broken file never produces garbled
output.

--coverage walks --coverage-root (default: cwd) and reports per-
file before/after bytes for every eligible source file. Useful for
measuring the aggregate savings this filter realizes across a repo;
powers the chart + Svelte dashboards.`,
		RunE: func(cmd *cobra.Command, args []string) error {
			if coverage {
				root := coverageRoot
				if root == "" {
					root = "."
				}
				rep, err := structureCoverage(root, coverageAll)
				if err != nil {
					return err
				}
				out := os.Stdout
				if f, ok := cmd.OutOrStdout().(*os.File); ok {
					out = f
				}
				return emitCoverageReport(rep, out, coverageJSON)
			}
			if path == "" {
				return fmt.Errorf("--path is required (or use --coverage for repo-wide report)")
			}
			data, err := os.ReadFile(path)
			if err != nil {
				return fmt.Errorf("reading %s: %w", path, err)
			}
			if lang == "" {
				lang = detectLang(path)
			}
			return emitStructure(cmd.OutOrStdout(), path, data, lang)
		},
	}
	cmd.Flags().StringVar(&path, "path", "", "Source file to summarize")
	cmd.Flags().StringVar(&lang, "lang", "",
		"Override language dispatch (go | python | javascript | typescript; other values pass through)")
	cmd.Flags().BoolVar(&coverage, "coverage", false,
		"Walk the tree and report aggregate before/after bytes across all eligible files")
	cmd.Flags().StringVar(&coverageRoot, "coverage-root", "",
		"Root directory for --coverage walk (default: cwd)")
	cmd.Flags().BoolVar(&coverageJSON, "json", false,
		"With --coverage, emit JSON instead of the human-readable table")
	cmd.Flags().BoolVar(&coverageAll, "all-files", false,
		"With --coverage, include every file in the JSON output (default: top-10 only)")
	return cmd
}

// detectLang maps a filename to its language token. "auto" /
// unknown -> unknown (pass-through).
func detectLang(path string) string {
	ext := strings.ToLower(filepath.Ext(path))
	switch ext {
	case ".go":
		return "go"
	case ".py":
		return "python"
	case ".ts", ".tsx":
		return "typescript"
	case ".js", ".jsx", ".mjs", ".cjs":
		return "javascript"
	}
	return "unknown"
}

// emitStructure dispatches to the per-language formatter. Pass-
// through fallback keeps the filter safe on unrecognized inputs.
func emitStructure(w io.Writer, path string, data []byte, lang string) error {
	switch lang {
	case "go":
		out, err := structureGo(path, data)
		if err != nil {
			// Parse failure — pass through the original content so
			// callers never get a malformed summary.
			_, err2 := w.Write(data)
			return err2
		}
		_, err = w.Write(out)
		return err
	case "python":
		out, err := structurePython(path, data)
		if err != nil {
			_, err2 := w.Write(data)
			return err2
		}
		_, err = w.Write(out)
		return err
	case "javascript":
		out, err := structureJS(path, data)
		if err != nil {
			_, err2 := w.Write(data)
			return err2
		}
		_, err = w.Write(out)
		return err
	case "typescript":
		out, err := structureTS(path, data)
		if err != nil {
			_, err2 := w.Write(data)
			return err2
		}
		_, err = w.Write(out)
		return err
	default:
		_, err := w.Write(data)
		return err
	}
}

// ---------------------------------------------------------------------------
// Go
// ---------------------------------------------------------------------------

// structureGo parses Go source and emits a structural summary:
//
//	package <name>
//	imports: [<N>] (see list below)
//	  "fmt"
//	  "os"
//	  ...
//
//	const ALPHA = 10
//	var counter int
//	type Foo struct { ... 3 fields ... }
//	type Bar interface { ... 2 methods ... }
//	func main()
//	func (r *Receiver) Method(arg int) (string, error)
//
// Exported identifiers and unexported ones are both listed — the
// summary is for the caller's situational awareness, not for
// generating stubs, so visibility isn't a filter criterion.
func structureGo(path string, data []byte) ([]byte, error) {
	fset := token.NewFileSet()
	f, err := parser.ParseFile(fset, path, data, parser.ParseComments|parser.SkipObjectResolution)
	if err != nil {
		return nil, fmt.Errorf("parse go: %w", err)
	}

	var out strings.Builder
	fmt.Fprintf(&out, "// [structure] %s (go, %d decls)\n", path, len(f.Decls))
	fmt.Fprintf(&out, "package %s\n\n", f.Name.Name)

	if len(f.Imports) > 0 {
		fmt.Fprintf(&out, "imports: (%d)\n", len(f.Imports))
		for _, imp := range f.Imports {
			fmt.Fprintf(&out, "  %s\n", imp.Path.Value)
		}
		out.WriteByte('\n')
	}

	for _, decl := range f.Decls {
		switch d := decl.(type) {
		case *ast.GenDecl:
			writeGoGenDecl(&out, d)
		case *ast.FuncDecl:
			writeGoFuncDecl(&out, d)
		}
	}

	return []byte(out.String()), nil
}

// writeGoGenDecl handles import / const / var / type declarations.
// Imports are already rendered at the top via f.Imports, so this
// skips the import case to avoid duplication.
func writeGoGenDecl(w *strings.Builder, d *ast.GenDecl) {
	switch d.Tok {
	case token.IMPORT:
		return
	case token.CONST, token.VAR:
		for _, spec := range d.Specs {
			vs, ok := spec.(*ast.ValueSpec)
			if !ok {
				continue
			}
			for _, name := range vs.Names {
				kind := "var"
				if d.Tok == token.CONST {
					kind = "const"
				}
				typeStr := ""
				if vs.Type != nil {
					typeStr = " " + exprString(vs.Type)
				}
				fmt.Fprintf(w, "%s %s%s\n", kind, name.Name, typeStr)
			}
		}
	case token.TYPE:
		for _, spec := range d.Specs {
			ts, ok := spec.(*ast.TypeSpec)
			if !ok {
				continue
			}
			writeGoTypeSpec(w, ts)
		}
	}
}

// writeGoTypeSpec emits a one-line (or few-line) summary of a type.
// Struct and interface types get a field / method count rather than
// the full list — the map-not-the-detail trade.
func writeGoTypeSpec(w *strings.Builder, ts *ast.TypeSpec) {
	switch t := ts.Type.(type) {
	case *ast.StructType:
		n := 0
		if t.Fields != nil {
			n = len(t.Fields.List)
		}
		fmt.Fprintf(w, "type %s struct { /* %d field(s) */ }\n", ts.Name.Name, n)
	case *ast.InterfaceType:
		n := 0
		if t.Methods != nil {
			n = len(t.Methods.List)
		}
		fmt.Fprintf(w, "type %s interface { /* %d method(s) */ }\n", ts.Name.Name, n)
	default:
		fmt.Fprintf(w, "type %s %s\n", ts.Name.Name, exprString(ts.Type))
	}
}

// writeGoFuncDecl emits a function / method signature without body.
func writeGoFuncDecl(w *strings.Builder, fn *ast.FuncDecl) {
	w.WriteString("func ")
	if fn.Recv != nil && len(fn.Recv.List) > 0 {
		w.WriteString("(")
		w.WriteString(fieldListString(fn.Recv))
		w.WriteString(") ")
	}
	w.WriteString(fn.Name.Name)
	w.WriteString("(")
	w.WriteString(fieldListString(fn.Type.Params))
	w.WriteString(")")
	if fn.Type.Results != nil && len(fn.Type.Results.List) > 0 {
		w.WriteString(" ")
		if len(fn.Type.Results.List) == 1 && len(fn.Type.Results.List[0].Names) == 0 {
			// Single unnamed return — no parens.
			w.WriteString(exprString(fn.Type.Results.List[0].Type))
		} else {
			w.WriteString("(")
			w.WriteString(fieldListString(fn.Type.Results))
			w.WriteString(")")
		}
	}
	w.WriteString("\n")
}

// fieldListString renders a FieldList (params / results / receiver)
// in the compact Go idiom — "name type" or just "type" when unnamed.
func fieldListString(fl *ast.FieldList) string {
	if fl == nil {
		return ""
	}
	var parts []string
	for _, f := range fl.List {
		ts := exprString(f.Type)
		if len(f.Names) == 0 {
			parts = append(parts, ts)
			continue
		}
		names := make([]string, 0, len(f.Names))
		for _, n := range f.Names {
			names = append(names, n.Name)
		}
		parts = append(parts, strings.Join(names, ", ")+" "+ts)
	}
	return strings.Join(parts, ", ")
}

// exprString renders a simple type expression back to source-like
// text. Handles the common cases (idents, selectors, pointers,
// slices, arrays, maps, channels, function types, ellipsis); falls
// back to "…" for exotic / generic forms so the output stays
// readable even when we can't losslessly round-trip.
func exprString(e ast.Expr) string {
	if e == nil {
		return ""
	}
	switch x := e.(type) {
	case *ast.Ident:
		return x.Name
	case *ast.SelectorExpr:
		return exprString(x.X) + "." + x.Sel.Name
	case *ast.StarExpr:
		return "*" + exprString(x.X)
	case *ast.ArrayType:
		inner := exprString(x.Elt)
		if x.Len == nil {
			return "[]" + inner
		}
		return "[" + exprString(x.Len) + "]" + inner
	case *ast.MapType:
		return "map[" + exprString(x.Key) + "]" + exprString(x.Value)
	case *ast.ChanType:
		dir := "chan"
		if x.Dir == ast.SEND {
			dir = "chan<-"
		} else if x.Dir == ast.RECV {
			dir = "<-chan"
		}
		return dir + " " + exprString(x.Value)
	case *ast.FuncType:
		return "func(" + fieldListString(x.Params) + ")" + funcResultsString(x.Results)
	case *ast.Ellipsis:
		return "..." + exprString(x.Elt)
	case *ast.InterfaceType:
		return "interface{}"
	case *ast.StructType:
		return "struct{…}"
	case *ast.BasicLit:
		return x.Value
	case *ast.IndexExpr:
		return exprString(x.X) + "[" + exprString(x.Index) + "]"
	case *ast.BinaryExpr:
		return exprString(x.X) + x.Op.String() + exprString(x.Y)
	}
	return "…"
}

func funcResultsString(fl *ast.FieldList) string {
	if fl == nil || len(fl.List) == 0 {
		return ""
	}
	return " " + "(" + fieldListString(fl) + ")"
}
