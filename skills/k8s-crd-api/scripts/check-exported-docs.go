// Command check-exported-docs checks documentation on newly written API files.
package main

import (
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type finding struct {
	path    string
	line    int
	message string
}

func main() {
	paths := os.Args[1:]
	if len(paths) > 0 && paths[0] == "--" {
		paths = paths[1:]
	}
	if len(paths) == 0 {
		fmt.Fprintln(os.Stderr, "usage: go run check-exported-docs.go -- <go-file-or-directory>...")
		os.Exit(2)
	}

	files, err := collectGoFiles(paths)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}

	var findings []finding
	for _, path := range files {
		fileFindings, err := checkFile(path)
		if err != nil {
			fmt.Fprintf(os.Stderr, "%s: %v\n", path, err)
			os.Exit(2)
		}
		findings = append(findings, fileFindings...)
	}

	for _, item := range findings {
		fmt.Printf("%s:%d: %s\n", item.path, item.line, item.message)
	}
	if len(findings) > 0 {
		os.Exit(1)
	}
}

func collectGoFiles(paths []string) ([]string, error) {
	seen := map[string]bool{}
	var files []string
	for _, path := range paths {
		info, err := os.Stat(path)
		if err != nil {
			return nil, err
		}
		if !info.IsDir() {
			if strings.HasSuffix(path, ".go") && !isGeneratedName(filepath.Base(path)) && !seen[path] {
				seen[path] = true
				files = append(files, path)
			}
			continue
		}
		err = filepath.WalkDir(path, func(candidate string, entry os.DirEntry, walkErr error) error {
			if walkErr != nil {
				return walkErr
			}
			if entry.IsDir() {
				if candidate != path && strings.HasPrefix(entry.Name(), ".") {
					return filepath.SkipDir
				}
				return nil
			}
			if !strings.HasSuffix(candidate, ".go") || isGeneratedName(entry.Name()) || seen[candidate] {
				return nil
			}
			seen[candidate] = true
			files = append(files, candidate)
			return nil
		})
		if err != nil {
			return nil, err
		}
	}
	sort.Strings(files)
	return files, nil
}

func isGeneratedName(name string) bool {
	return strings.HasPrefix(name, "zz_generated.") ||
		name == "generated.pb.go" ||
		name == "types_swagger_doc_generated.go"
}

func checkFile(path string) ([]finding, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	if strings.Contains(string(content[:min(len(content), 2048)]), "Code generated") {
		return nil, nil
	}

	fset := token.NewFileSet()
	file, err := parser.ParseFile(fset, path, content, parser.ParseComments)
	if err != nil {
		return nil, err
	}

	var findings []finding
	isTestFile := strings.HasSuffix(path, "_test.go")
	add := func(pos token.Pos, message string) {
		findings = append(findings, finding{path: path, line: fset.Position(pos).Line, message: message})
	}

	for _, decl := range file.Decls {
		switch node := decl.(type) {
		case *ast.FuncDecl:
			if node.Name.IsExported() && !(isTestFile && isTestingEntryPoint(node.Name.Name)) && !docStartsWith(node.Doc, node.Name.Name) {
				add(node.Name.Pos(), fmt.Sprintf("exported function or method %s needs a doc comment beginning with %s", node.Name.Name, node.Name.Name))
			}
		case *ast.GenDecl:
			for _, rawSpec := range node.Specs {
				switch spec := rawSpec.(type) {
				case *ast.TypeSpec:
					if spec.Name.IsExported() {
						doc := spec.Doc
						if doc == nil {
							doc = node.Doc
						}
						if !docStartsWith(doc, spec.Name.Name) {
							add(spec.Name.Pos(), fmt.Sprintf("exported type %s needs a doc comment beginning with %s", spec.Name.Name, spec.Name.Name))
						}
					}
					if structure, ok := spec.Type.(*ast.StructType); ok {
						checkStructFields(structure, add)
					}
				case *ast.ValueSpec:
					doc := spec.Doc
					if doc == nil && len(node.Specs) == 1 {
						doc = node.Doc
					}
					for _, name := range spec.Names {
						if name.IsExported() && !docStartsWith(doc, name.Name) {
							add(name.Pos(), fmt.Sprintf("exported constant or variable %s needs its own doc comment beginning with %s", name.Name, name.Name))
						}
					}
				}
			}
		}
	}
	return findings, nil
}

func isTestingEntryPoint(name string) bool {
	for _, prefix := range []string{"Test", "Benchmark", "Fuzz", "Example"} {
		if strings.HasPrefix(name, prefix) {
			return true
		}
	}
	return false
}

func checkStructFields(structure *ast.StructType, add func(token.Pos, string)) {
	for _, field := range structure.Fields.List {
		if len(field.Names) == 0 {
			continue
		}
		for _, name := range field.Names {
			if name.IsExported() && !hasSemanticComment(field.Doc, field.Comment) {
				add(name.Pos(), fmt.Sprintf("exported API field %s needs a semantic doc comment", name.Name))
			}
		}
	}
}

func docStartsWith(doc *ast.CommentGroup, name string) bool {
	if doc == nil {
		return false
	}
	text := strings.TrimSpace(doc.Text())
	if text == name {
		return true
	}
	return strings.HasPrefix(text, name+" ") || strings.HasPrefix(text, name+"\n")
}

func hasSemanticComment(groups ...*ast.CommentGroup) bool {
	for _, group := range groups {
		if group != nil && strings.TrimSpace(group.Text()) != "" {
			return true
		}
	}
	return false
}
