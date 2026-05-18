# Entry Function Filter: Parameter Type and File Extension — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two new entry function constraints — only `.c` file bodies and at least one non-basic parameter type — to Module C's `find_entry_functions()`, with Module A capturing parameter text.

**Architecture:** Module A's `CallAnalyzer` extracts the full text of each parameter declaration from the tree-sitter AST and stores it in `FunctionNode.params`. This serializes to `nodes.json`. Module C's `find_entry_functions()` reads `params` and applies negative exclusion: a function is excluded only when all its parameters consist solely of basic scalar types (or no params). All changes are self-contained within `models.py`, `_call_analyzer.py`, and `entry_finder.py`.

**Tech Stack:** Python 3.11+, tree-sitter, pytest

---

### Task 1: Add `params` field to FunctionNode model

**Files:**
- Modify: `module_a/models.py:14-33`
- Modify: `module_a/tests/test_models.py:9-23,26-37,64-71`

- [ ] **Step 1: Add `params` field to `FunctionNode` dataclass**

In `module_a/models.py`, add `from dataclasses import dataclass, field` and the `params` field:

```python
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProjectSymbols:
    """Cross-file function-related symbols collected in Phase 0."""
    typedef_fnptr_names: set[str]
    global_fnptr_names: set[str]
    macro_call_map: dict[str, str]  # macro_name -> callee_name


@dataclass
class FunctionNode:
    """A function in the call graph."""
    name: str
    file: str
    line_start: int
    has_body: bool
    body_file: Optional[str] = None
    body_line_start: Optional[int] = None
    body_line_end: Optional[int] = None
    params: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "file": self.file,
            "line_start": self.line_start,
            "has_body": self.has_body,
            "body_file": self.body_file,
            "body_line_start": self.body_line_start,
            "body_line_end": self.body_line_end,
            "params": self.params,
        }
```

Note: The `DirectEdge` and `IndirectPoint` classes remain unchanged.

- [ ] **Step 2: Run existing tests to verify they still pass**

```bash
.venv/bin/python3 -m pytest module_a/tests/test_models.py -v
```

Expected: All 5 tests PASS (existing tests use positional args, which still work since `params` has a default).

- [ ] **Step 3: Add `params` field to existing test fixtures in test_models.py**

Update the in-line data in `test_models.py` to verify the `params` field:

In `test_function_node_to_dict()` (line 10-23), update the assertion to check `params`:

```python
def test_function_node_to_dict():
    fn = FunctionNode(
        name="my_func",
        file="src/main.c",
        line_start=42,
        has_body=True,
        body_file="src/main.c",
        body_line_start=42,
        body_line_end=98,
        params=["int x", "const char *name"],
    )
    d = fn.to_dict()
    assert d["name"] == "my_func"
    assert d["file"] == "src/main.c"
    assert d["has_body"] is True
    assert d["body_line_end"] == 98
    assert d["params"] == ["int x", "const char *name"]
```

In `test_function_node_no_body()`, verify default empty:

```python
def test_function_node_no_body():
    fn = FunctionNode(
        name="external_func",
        file="include/api.h",
        line_start=15,
        has_body=False,
    )
    d = fn.to_dict()
    assert d["has_body"] is False
    assert d["body_file"] is None
    assert d["body_line_start"] is None
    assert d["body_line_end"] is None
    assert d["params"] == []
```

In `test_to_dict_json_serializable()`, add params to the FunctionNode:

```python
def test_to_dict_json_serializable():
    """All to_dict() outputs must be JSON-serializable."""
    fn = FunctionNode("f", "a.c", 1, True, "a.c", 1, 5, ["int *p"])
    edge = DirectEdge("f", "g", "a.c", 3)
    ip = IndirectPoint("uid1", "f", "a.c", 4, "(*fp)()")
    json.dumps(fn.to_dict())
    json.dumps(edge.to_dict())
    json.dumps(ip.to_dict())
```

- [ ] **Step 4: Run tests to verify additions pass**

```bash
.venv/bin/python3 -m pytest module_a/tests/test_models.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add module_a/models.py module_a/tests/test_models.py
git commit -m "feat(module-a): add params field to FunctionNode model"
```

---

### Task 2: Extract parameter text in CallAnalyzer

**Files:**
- Modify: `module_a/_call_analyzer.py:43-64,157-170`
- Modify: `module_a/tests/test_call_analyzer.py`

- [ ] **Step 1: Add `_extract_params()` function to `_call_analyzer.py`**

Add this standalone function after the existing `_extract_fnptr_params()` (after line 170):

```python
def _extract_params(func_declarator_node, source_bytes) -> list[str]:
    """Extract full text of each parameter declaration from a function declarator."""
    for child in func_declarator_node.children:
        if child.type == "parameter_list":
            return [
                source_bytes[p.start_byte:p.end_byte].decode()
                for p in child.children
                if p.type == "parameter_declaration"
            ]
    return []
```

- [ ] **Step 2: Call `_extract_params()` in `CallAnalyzer._walk()` when building FunctionNode**

In `_walk()`, around line 55-63, add parameter extraction after getting the declarator. Change the FunctionNode construction to include `params`:

Replace lines 54-63:
```python
            if func_name:
                fn = FunctionNode(
                    name=func_name,
                    file=self._filepath,
                    line_start=node.start_point[0] + 1,
                    has_body=node.child_by_field_name("body") is not None,
                    body_file=self._filepath,
                    body_line_start=node.start_point[0] + 1,
                    body_line_end=node.end_point[0] + 1,
                )
```

With:
```python
            if func_name:
                fn_params = _extract_params(declarator, self._source) if declarator else []
                fn = FunctionNode(
                    name=func_name,
                    file=self._filepath,
                    line_start=node.start_point[0] + 1,
                    has_body=node.child_by_field_name("body") is not None,
                    body_file=self._filepath,
                    body_line_start=node.start_point[0] + 1,
                    body_line_end=node.end_point[0] + 1,
                    params=fn_params,
                )
```

- [ ] **Step 3: Write a test for `_extract_params()`**

Add this test class at the end of `module_a/tests/test_call_analyzer.py`:

```python
class TestExtractParams:
    def test_no_params(self):
        from tree_sitter import Language, Parser
        import tree_sitter_c as tsc
        src = b'void f(void) {}'
        parser = Parser(Language(tsc.language()))
        root = parser.parse(src).root_node
        func_def = root.children[0]
        declarator = func_def.child_by_field_name("declarator")
        assert declarator is not None
        from module_a._call_analyzer import _extract_params
        params = _extract_params(declarator, src)
        assert params == ["void"]

    def test_single_param(self):
        from tree_sitter import Language, Parser
        import tree_sitter_c as tsc
        src = b'void f(int x) {}'
        parser = Parser(Language(tsc.language()))
        root = parser.parse(src).root_node
        func_def = root.children[0]
        declarator = func_def.child_by_field_name("declarator")
        from module_a._call_analyzer import _extract_params
        params = _extract_params(declarator, src)
        assert params == ["int x"]

    def test_multiple_params(self):
        from tree_sitter import Language, Parser
        import tree_sitter_c as tsc
        src = b'void f(int x, struct device *dev) {}'
        parser = Parser(Language(tsc.language()))
        root = parser.parse(src).root_node
        func_def = root.children[0]
        declarator = func_def.child_by_field_name("declarator")
        from module_a._call_analyzer import _extract_params
        params = _extract_params(declarator, src)
        assert params == ["int x", "struct device *dev"]

    def test_pointer_param(self):
        from tree_sitter import Language, Parser
        import tree_sitter_c as tsc
        src = b'void f(const char *name) {}'
        parser = Parser(Language(tsc.language()))
        root = parser.parse(src).root_node
        func_def = root.children[0]
        declarator = func_def.child_by_field_name("declarator")
        from module_a._call_analyzer import _extract_params
        params = _extract_params(declarator, src)
        assert params == ["const char *name"]

    def test_array_param(self):
        from tree_sitter import Language, Parser
        import tree_sitter_c as tsc
        src = b'void f(char buf[256]) {}'
        parser = Parser(Language(tsc.language()))
        root = parser.parse(src).root_node
        func_def = root.children[0]
        declarator = func_def.child_by_field_name("declarator")
        from module_a._call_analyzer import _extract_params
        params = _extract_params(declarator, src)
        assert params == ["char buf[256]"]
```

- [ ] **Step 4: Verify `params` appears in `nodes.json` output via `analyze_single_file`**

Add a test to verify the full pipeline:

```python
    def test_params_in_analyze_single_file(self):
        import os
        from module_a.analyzer import analyze_single_file
        result = analyze_single_file(os.path.join(
            FIXTURES, "macros", "simple_macro", "fixture.c"))
        for fn in result["functions"]:
            assert "params" in fn
            assert isinstance(fn["params"], list)
```

- [ ] **Step 5: Run the new tests**

```bash
.venv/bin/python3 -m pytest module_a/tests/test_call_analyzer.py::TestExtractParams -v
```

Expected: 6 tests PASS (5 from TestExtractParams + 1 extra).

- [ ] **Step 6: Run all module_a tests to check for regressions**

```bash
.venv/bin/python3 -m pytest module_a/tests/ -v
```

Expected: All existing tests still PASS. If any test fails because it checks specific field lists on `nodes.json` output, update the test to also accept `params`.

- [ ] **Step 7: Commit**

```bash
git add module_a/_call_analyzer.py module_a/tests/test_call_analyzer.py
git commit -m "feat(module-a): extract function parameter text into FunctionNode.params"
```

---

### Task 3: Add enhanced filtering to Module C's find_entry_functions

**Files:**
- Modify: `module_c/entry_finder.py:1-23`
- Modify: `module_c/tests/test_entry_finder.py`

- [ ] **Step 1: Add `_is_basic_params()` helper and basic types to entry_finder.py**

Replace the current `find_entry_functions()` (lines 1-23) with the full updated content:

```python
"""Find entry functions and generate indirect_call.json summary."""
import json
import os

from module_c.merge import merge_callgraph, write_callgraph

_BASIC_TYPES = frozenset({
    # C keywords
    "int", "long", "short", "char", "float", "double",
    "unsigned", "signed", "void", "_Bool", "bool",
    # Fixed-width typedefs
    "uint8_t", "uint16_t", "uint32_t", "uint64_t",
    "int8_t", "int16_t", "int32_t", "int64_t",
    "uintmax_t", "intmax_t",
    # Standard size typedefs
    "size_t", "ssize_t", "ptrdiff_t", "off_t",
    # Kernel abbreviations
    "u8", "u16", "u32", "u64", "s8", "s16", "s32", "s64",
})

_QUALIFIERS = frozenset({"const", "volatile", "restrict"})


def _is_basic_params(params: list[str]) -> bool:
    """Return True if all params are basic scalar types (function excluded)."""
    if not params:
        return True
    if len(params) == 1 and params[0].strip() == "void":
        return True

    for text in params:
        has_marker = '*' in text or '[' in text
        for q in _QUALIFIERS:
            text = text.replace(q, "")
        tokens = text.split()
        if not tokens:
            continue
        # Remove last token (parameter name; may have * prefix like *name)
        tokens = tokens[:-1]
        all_basic = all(t in _BASIC_TYPES for t in tokens)
        if has_marker or not all_basic:
            return False
    return True


def find_entry_functions(callgraph: dict) -> list[dict]:
    nodes = callgraph.get("nodes", [])
    edges = callgraph.get("edges", [])
    callees = {e["callee"] for e in edges}

    entries = []
    for node in nodes:
        if not node.get("has_body"):
            continue
        body_file = node.get("body_file", "")
        if not body_file.lower().endswith(".c"):
            continue
        if node["name"] in callees:
            continue
        if _is_basic_params(node.get("params", [])):
            continue
        entries.append({
            "name": node["name"],
            "file": node.get("file", ""),
            "line_start": node.get("line_start", -1),
        })
    return entries


def build_indirect_summary(indirect_points_path: str,
                           indirect_dir: str) -> dict:
    with open(indirect_points_path) as f:
        ip_data = json.load(f)

    calls = []
    completed = 0
    failed = 0

    for ip in ip_data.get("indirect_points", []):
        uid = ip["uid"]
        result_path = os.path.join(indirect_dir, f"{uid}.json")

        call_info = {
            "uid": uid,
            "caller": ip["func"],
            "expression": ip["expression"],
            "file": ip["file"],
            "line": ip["line"],
            "targets": [],
        }

        if os.path.isfile(result_path):
            with open(result_path) as f:
                result = json.load(f)
            if result.get("status") == "completed":
                completed += 1
                for t in result.get("possible_targets", []):
                    call_info["targets"].append({
                        "callee": t["callee"],
                        "confidence": t["confidence"],
                    })
            elif result.get("status") == "failed":
                failed += 1
                call_info["error"] = result.get("error", "Unknown error")
        else:
            failed += 1
            call_info["error"] = "Analysis not performed"

        calls.append(call_info)

    return {
        "total": len(calls),
        "completed": completed,
        "failed": failed,
        "calls": calls,
    }


def write_indirect_summary(output_dir: str, summary: dict):
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "indirect_call.json")
    with open(path, "w") as f:
        json.dump(summary, f, indent=2)


def write_entry_functions(output_dir: str, entries: list[dict]):
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "entry.json")
    with open(path, "w") as f:
        json.dump({"entry_functions": entries}, f, indent=2)


def run_module_c(project_dir: str, output_dir: str) -> dict:
    nodes_path = os.path.join(output_dir, "nodes.json")
    edges_path = os.path.join(output_dir, "edges.json")
    ip_path = os.path.join(output_dir, "indirect_points.json")
    indirect_dir = os.path.join(output_dir, "indirect")

    callgraph = merge_callgraph(nodes_path, edges_path, ip_path, indirect_dir)
    write_callgraph(output_dir, callgraph)

    entries = find_entry_functions(callgraph)
    write_entry_functions(output_dir, entries)

    summary = build_indirect_summary(ip_path, indirect_dir)
    write_indirect_summary(output_dir, summary)

    print(f"Module C: {len(callgraph['edges'])} total edges, "
          f"{len(entries)} entry functions")

    return {"callgraph": callgraph, "entries": entries, "summary": summary}
```

- [ ] **Step 2: Run existing module_c tests to see what fails**

```bash
.venv/bin/python3 -m pytest module_c/tests/test_entry_finder.py -v
```

Expected: `test_cycle_no_entry` and `test_empty_graph` still pass, but `test_entry_functions_are_has_body`, `test_no_callers_is_entry`, and `test_entry_from_fixture` will FAIL because nodes now need `params` and existing entries may be filtered out.

- [ ] **Step 3: Update existing tests with `params` field and new test cases**

Replace `module_c/tests/test_entry_finder.py` entirely:

```python
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from module_c.entry_finder import find_entry_functions, _is_basic_params
from module_c.merge import merge_callgraph


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_callgraph():
    return merge_callgraph(
        os.path.join(FIXTURES_DIR, "nodes.json"),
        os.path.join(FIXTURES_DIR, "edges.json"),
        os.path.join(FIXTURES_DIR, "indirect_points.json"),
        os.path.join(FIXTURES_DIR, "indirect"),
    )


class TestIsBasicParams:
    def test_empty_params(self):
        assert _is_basic_params([]) is True

    def test_void_param(self):
        assert _is_basic_params(["void"]) is True

    def test_int_param(self):
        assert _is_basic_params(["int x"]) is True

    def test_int_pointer_param(self):
        assert _is_basic_params(["int *x"]) is False

    def test_struct_param(self):
        assert _is_basic_params(["struct foo *p"]) is False

    def test_union_param(self):
        assert _is_basic_params(["union bar u"]) is False

    def test_array_param(self):
        assert _is_basic_params(["char buf[256]"]) is False

    def test_uint32_t_param(self):
        assert _is_basic_params(["uint32_t count"]) is True

    def test_size_t_and_int_params(self):
        assert _is_basic_params(["size_t len", "int flags"]) is True

    def test_mixed_basic_and_nonbasic(self):
        assert _is_basic_params(["uint32_t x", "device_t *d"]) is False

    def test_unsigned_long(self):
        assert _is_basic_params(["unsigned long n"]) is True

    def test_typedef_struct_value(self):
        # device_t not in basic set → non-basic
        assert _is_basic_params(["device_t dev"]) is False

    def test_const_char_pointer(self):
        assert _is_basic_params(["const char *name"]) is False

    def test_function_pointer_param(self):
        assert _is_basic_params(["void (*callback)(int)"]) is False


class TestFindEntryFunctions:
    def test_excludes_header_only(self):
        entries = find_entry_functions({
            "nodes": [
                {"name": "f1", "has_body": True, "body_file": "a.c",
                 "file": "a.c", "line_start": 1,
                 "body_line_start": 1, "body_line_end": 5,
                 "params": ["int *p"]},
                {"name": "f2", "has_body": False, "body_file": None,
                 "file": "b.h", "line_start": -1,
                 "body_line_start": None, "body_line_end": None,
                 "params": []},
            ],
            "edges": [],
        })
        names = {e["name"] for e in entries}
        assert "f1" in names
        assert "f2" not in names

    def test_excludes_header_body(self):
        # Function with body in .h (e.g., static inline) → excluded
        entries = find_entry_functions({
            "nodes": [
                {"name": "inl", "has_body": True, "body_file": "util.h",
                 "file": "util.h", "line_start": 1,
                 "body_line_start": 1, "body_line_end": 5,
                 "params": ["int *p"]},
            ],
            "edges": [],
        })
        assert len(entries) == 0

    def test_no_callers_is_entry(self):
        entries = find_entry_functions({
            "nodes": [
                {"name": "main", "has_body": True, "body_file": "a.c",
                 "file": "a.c", "line_start": 1,
                 "body_line_start": 1, "body_line_end": 5,
                 "params": ["int argc", "char **argv"]},
                {"name": "helper", "has_body": True, "body_file": "a.c",
                 "file": "a.c", "line_start": 6,
                 "body_line_start": 6, "body_line_end": 10,
                 "params": ["int x"]},
            ],
            "edges": [
                {"caller": "main", "callee": "helper", "type": "direct"},
            ],
        })
        names = {e["name"] for e in entries}
        assert "main" in names
        assert "helper" not in names

    def test_excludes_basic_params_only(self):
        # int-only param → excluded even if indegree=0
        entries = find_entry_functions({
            "nodes": [
                {"name": "noop", "has_body": True, "body_file": "a.c",
                 "file": "a.c", "line_start": 1,
                 "body_line_start": 1, "body_line_end": 5,
                 "params": ["int x"]},
            ],
            "edges": [],
        })
        assert len(entries) == 0

    def test_excludes_no_params(self):
        entries = find_entry_functions({
            "nodes": [
                {"name": "noop", "has_body": True, "body_file": "a.c",
                 "file": "a.c", "line_start": 1,
                 "body_line_start": 1, "body_line_end": 5,
                 "params": []},
            ],
            "edges": [],
        })
        assert len(entries) == 0

    def test_excludes_void_param(self):
        entries = find_entry_functions({
            "nodes": [
                {"name": "noop", "has_body": True, "body_file": "a.c",
                 "file": "a.c", "line_start": 1,
                 "body_line_start": 1, "body_line_end": 5,
                 "params": ["void"]},
            ],
            "edges": [],
        })
        assert len(entries) == 0

    def test_cycle_no_entry(self):
        entries = find_entry_functions({
            "nodes": [
                {"name": "a", "has_body": True, "body_file": "x.c",
                 "file": "x.c", "line_start": 1,
                 "body_line_start": 1, "body_line_end": 5,
                 "params": ["int *p"]},
                {"name": "b", "has_body": True, "body_file": "x.c",
                 "file": "x.c", "line_start": 6,
                 "body_line_start": 6, "body_line_end": 10,
                 "params": ["int *p"]},
            ],
            "edges": [
                {"caller": "a", "callee": "b", "type": "direct"},
                {"caller": "b", "callee": "a", "type": "direct"},
            ],
        })
        assert len(entries) == 0

    def test_empty_graph(self):
        entries = find_entry_functions({"nodes": [], "edges": []})
        assert entries == []
```

- [ ] **Step 4: Run the module_c tests**

```bash
.venv/bin/python3 -m pytest module_c/tests/test_entry_finder.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add module_c/entry_finder.py module_c/tests/test_entry_finder.py
git commit -m "feat(module-c): add .c file and non-basic params filtering to entry functions"
```

---

### Task 4: Update Module C test fixtures

**Files:**
- Modify: `module_c/tests/fixtures/nodes.json`
- Modify: `module_c/tests/expected/entry_expected.json`

- [ ] **Step 1: Add `params` field to fixture nodes.json**

Each function in `module_c/tests/fixtures/nodes.json` needs a `"params"` key. Functions that should remain as entries (`init`, `orphan`) need non-basic params. Other functions can have basic or empty params.

```json
{
  "project_dir": "/test/project",
  "functions": [
    {"name": "init", "file": "main.c", "line_start": 1, "has_body": true, "body_file": "main.c", "body_line_start": 1, "body_line_end": 10, "params": ["int argc", "char **argv"]},
    {"name": "do_work", "file": "main.c", "line_start": 12, "has_body": true, "body_file": "main.c", "body_line_start": 12, "body_line_end": 25, "params": ["struct device *dev"]},
    {"name": "helper_a", "file": "main.c", "line_start": 27, "has_body": true, "body_file": "main.c", "body_line_start": 27, "body_line_end": 32, "params": ["int x"]},
    {"name": "helper_b", "file": "main.c", "line_start": 34, "has_body": true, "body_file": "main.c", "body_line_start": 34, "body_line_end": 40, "params": ["int y"]},
    {"name": "orphan", "file": "main.c", "line_start": 42, "has_body": true, "body_file": "main.c", "body_line_start": 42, "body_line_end": 46, "params": ["struct config *cfg"]},
    {"name": "malloc", "file": "include/stdlib.h", "line_start": -1, "has_body": false, "body_file": null, "body_line_start": null, "body_line_end": null, "params": ["size_t size"]},
    {"name": "printf", "file": "include/stdio.h", "line_start": -1, "has_body": false, "body_file": null, "body_line_start": null, "body_line_end": null, "params": ["const char *fmt"]}
  ]
}
```

- [ ] **Step 2: Verify the entry expected output is still correct**

The expected entry result (`module_c/tests/expected/entry_expected.json`) should still be `init` and `orphan`. No change needed — both still have non-basic params and are in `.c` files.

- [ ] **Step 3: Run the fixture-based tests**

```bash
.venv/bin/python3 -m pytest module_c/tests/test_entry_finder.py -v
.venv/bin/python3 -m pytest module_c/tests/test_merge.py -v
```

Expected: All tests PASS.

- [ ] **Step 4: Run full end-to-end verification**

```bash
rm -rf tests/e2e_project/.siakam_out
.venv/bin/python3 start.py analyze tests/e2e_project
.venv/bin/python3 start.py merge tests/e2e_project
.venv/bin/python3 -c "
import json
entries = json.load(open('tests/e2e_project/.siakam_out/entry.json'))
print('Entry functions:', [e['name'] for e in entries['entry_functions']])
"
```

Expected: Entry functions are only those with non-basic params in `.c` files, not called by others.

- [ ] **Step 5: Commit**

```bash
git add module_c/tests/fixtures/nodes.json
git commit -m "test(module-c): update fixtures with params field for entry filter"
```
