// TEST_STAGE = TestStage.SMOKE
package main

import (
	"encoding/json"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"strconv"
	"testing"
)

func TestSharedProtocolContract(t *testing.T) {
	data, err := os.ReadFile("protocol_contract.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		Schema  int      `json:"schema"`
		Actions []string `json:"actions"`
		Cases   []struct {
			Action  string         `json:"action"`
			Request map[string]any `json:"request"`
			OK      bool           `json:"ok"`
		} `json:"cases"`
	}
	if err := json.Unmarshal(data, &fixture); err != nil {
		t.Fatal(err)
	}
	if fixture.Schema != 1 {
		t.Fatal("unsupported fixture schema")
	}
	handled := map[string]bool{}
	add := func(expr ast.Expr) {
		if literal, ok := expr.(*ast.BasicLit); ok && literal.Kind == token.STRING {
			value, err := strconv.Unquote(literal.Value)
			if err == nil {
				handled[value] = true
			}
		}
	}
	for _, filename := range []string{"protocol.go", "requests.go"} {
		tree, err := parser.ParseFile(token.NewFileSet(), filename, nil, 0)
		if err != nil {
			t.Fatal(err)
		}
		for _, decl := range tree.Decls {
			function, ok := decl.(*ast.FuncDecl)
			if !ok || (function.Name.Name != "dispatch" && function.Name.Name != "executeRequest") {
				continue
			}
			ast.Inspect(function.Body, func(node ast.Node) bool {
				switch node := node.(type) {
				case *ast.SwitchStmt:
					if tag, ok := node.Tag.(*ast.Ident); ok && tag.Name == "action" {
						for _, item := range node.Body.List {
							for _, expr := range item.(*ast.CaseClause).List {
								add(expr)
							}
						}
					}
				case *ast.BinaryExpr:
					if left, ok := node.X.(*ast.Ident); ok && left.Name == "action" && node.Op == token.EQL {
						add(node.Y)
					}
				}
				return true
			})
		}
	}
	for _, action := range fixture.Actions {
		if !handled[action] {
			t.Errorf("fixture action is not handled: %s", action)
		}
		delete(handled, action)
	}
	if len(handled) != 0 {
		t.Errorf("native actions missing from fixture: %v", handled)
	}
	clearSession()
	t.Cleanup(clearSession)
	for _, item := range fixture.Cases {
		request, _ := json.Marshal(item.Request)
		var reply map[string]any
		if err := json.Unmarshal([]byte(dispatch(item.Action, string(request))), &reply); err != nil {
			t.Fatal(err)
		}
		if reply["ok"] != item.OK {
			t.Errorf("%s: unexpected response status", item.Action)
		}
	}
}

func TestSharedRequestLimits(t *testing.T) {
	data, err := os.ReadFile("protocol_contract.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		Limits []struct {
			Action string `json:"action"`
			Native int    `json:"native"`
		} `json:"request_limits"`
	}
	if err := json.Unmarshal(data, &fixture); err != nil {
		t.Fatal(err)
	}
	if len(fixture.Limits) == 0 {
		t.Fatal("request limit fixture is empty")
	}
	for _, item := range fixture.Limits {
		if actual := requestLimit(item.Action); actual != item.Native {
			t.Errorf("%s: limit %d, want %d", item.Action, actual, item.Native)
		}
	}
}
