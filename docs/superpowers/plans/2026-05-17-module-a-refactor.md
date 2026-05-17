# Module A Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor module_a: split c_parser.py monolith, eliminate global state, add project-wide cross-file symbol collection (typedef fnptr + macro expansion), introduce logging.

**Architecture:** Two-phase pipeline — Phase 0a collects project-wide typedefs + macros, Phase 0b collects global fnptr names using merged typedefs, Phase 1+2 runs per-file call analysis with shared ProjectSymbols. Test-only convenience `parse_file()` preserves single-file test ergonomics.

**Tech Stack:** Python 3.11, tree-sitter, tree-sitter-c, pytest, dataclasses, hashlib, logging

---

### Task 1: Create `_ast_helpers.py` — shared AST utility functions

**Files:**
- Create: `module_a/_ast_helpers.py`
- Reference: `module_a/c_parser.py:56-59,82-98,135-155,360-380`

Extract helper functions from `c_parser.py` into a new shared module. No behavioral changes.

- [ ] **Step 1: Write the file**

```python
"""Shared AST utility functions used by _project_scanner and _call_analyzer."""
from typing import Iterator


def iter_all(node) -> Iterator:
    """Yield node and all descendants."""
    yield node
    for child in node.children:
        yield from iter_all(child)


def has_descendant(node, target_type: str) -> bool:
    """Check if subtree contains a node of the given type."""
    if node.type == target_type:
        return True
    for child in node.children:
        if has_descendant(child, target_type):
            return True
    return False


def is_inside_param_list(node) -> bool:
    """Check if node has a parameter_list ancestor."""
    cur = node
    while cur is not None:
        if cur.type == "parameter_list":
            return True
        cur = cur.parent
    return False


def find_first_id(node, source_bytes) -> str | None:
    """Depth-first search for first identifier text in subtree."""
    if node.type == "identifier":
        return source_bytes[node.start_byte:node.end_byte].decode()
    for child in node.children:
        result = find_first_id(child, source_bytes)
        if result:
            return result
    return None


def get_type_name(decl_node, source_bytes) -> str | None:
    """Extract type_identifier name from a declaration node."""
    for child in decl_node.children:
        if child.type == "type_identifier":
            return source_bytes[child.start_byte:child.end_byte].decode()
    return None


def find_identifier(node, source_bytes) -> str | None:
    """Extract identifier from a function declarator node."""
    if node.type == "identifier":
        return source_bytes[node.start_byte:node.end_byte].decode()
    if node.type == "function_declarator":
        decl = node.child_by_field_name("declarator")
        if decl:
            return find_identifier(decl, source_bytes)
    for child in node.children:
        result = find_identifier(child, source_bytes)
        if result:
            return result
    return None
```

- [ ] **Step 2: Verify import**

Run: `.venv/bin/python3 -c "from module_a._ast_helpers import iter_all, has_descendant, is_inside_param_list, find_first_id, get_type_name, find_identifier; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add module_a/_ast_helpers.py
git commit -m "feat(module-a): extract _ast_helpers.py with shared AST utilities

Pulled from c_parser.py: _iter_all, _has_descendant, _is_inside_param_list,
_find_first_id, _get_type_name, _find_identifier. No behavioral changes.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: Create `_parser.py` — tree-sitter lifecycle management

**Files:**
- Create: `module_a/_parser.py`

Replaces the global `C_LANGUAGE` / `PARSER` with injectable factory + parse function. Error reporting uses `logging`.

- [ ] **Step 1: Write the file**

```python
"""tree-sitter C parser lifecycle. No global state."""
import logging
import sys
from tree_sitter import Language, Parser
import tree_sitter_c as tsc

from module_a._ast_helpers import iter_all

logger = logging.getLogger(__name__)


def create_parser() -> Parser:
    """Create a fresh tree-sitter Parser for C. Caller owns the instance."""
    lang = Language(tsc.language())
    return Parser(lang)


def parse_file(parser: Parser, filepath: str) -> tuple:
    """Parse a C source file. Returns (root_node, source_bytes).

    Reports syntax errors via logging; never raises on parse errors.
    """
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        source = f.read()

    source_bytes = source.encode()
    tree = parser.parse(source_bytes)
    root = tree.root_node

    if root.has_error:
        for node in iter_all(root):
            if node.type == "ERROR":
                line = node.start_point[0] + 1
                logger.warning("%s:%d: syntax error, skipping affected code",
                               filepath, line)

    return root, source_bytes
```

- [ ] **Step 2: Verify parsing works**

Run: `.venv/bin/python3 -c "
from module_a._parser import create_parser, parse_file
p = create_parser()
root, src = parse_file(p, 'module_a/tests/fixtures/macros/simple_macro/fixture.c')
print('root type:', root.type)
print('bytes:', len(src))
"` 
Expected: `root type: translation_unit` and `bytes: <positive integer>`

- [ ] **Step 3: Commit**

```bash
git add module_a/_parser.py
git commit -m "feat(module-a): add _parser.py with injectable tree-sitter lifecycle

Replaces global C_LANGUAGE/PARSER. parse_file() takes parser as parameter,
reports errors via logging.warning() instead of print().

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: Create `_project_scanner.py` — Phase 0 symbol collection

**Files:**
- Create: `module_a/_project_scanner.py`

Contains `ProjectSymbols` dataclass and three scanner functions. Extracts logic from `c_parser.py` lines 64-184.

- [ ] **Step 1: Write the file**

```python
"""Phase 0: project-wide symbol collection for cross-file analysis."""
import re
from dataclasses import dataclass

from module_a._ast_helpers import (
    iter_all, has_descendant, is_inside_param_list,
    find_first_id, get_type_name,
)

# C keywords that can appear as identifier(args) in macro bodies
_C_KEYWORDS = frozenset({"if", "while", "for", "switch", "void", "return", "sizeof"})


@dataclass
class ProjectSymbols:
    """Cross-file function-related symbols collected in Phase 0."""
    typedef_fnptr_names: set[str]
    global_fnptr_names: set[str]
    macro_call_map: dict[str, str]  # macro_name -> callee_name


# ---- Pass 0a: typedef fnptr names ----


def scan_typedefs(root, source_bytes) -> set[str]:
    """Collect typedef names that are function pointer types.

    Handles:
      typedef void (name)(params);        -- function_declarator wrapping type_identifier
      typedef void (*name)(params);       -- pointer_declarator with function_declarator
      typedef ret *(*name)(params);       -- nested pointer_declarator with fnptr
    """
    names = set()
    _scan_typedefs_inner(root, source_bytes, names)
    return names


def _scan_typedefs_inner(node, source_bytes, names):
    if node.type == "type_definition":
        _extract_typedef_fnptr(node, source_bytes, names)
    for child in node.children:
        _scan_typedefs_inner(child, source_bytes, names)


def _extract_typedef_fnptr(type_def_node, source_bytes, names):
    if not has_descendant(type_def_node, "function_declarator"):
        return

    for child in iter_all(type_def_node):
        if child.type == "parenthesized_declarator":
            for sub in iter_all(child):
                if sub.type in ("type_identifier", "identifier"):
                    name = source_bytes[sub.start_byte:sub.end_byte].decode()
                    names.add(name)
                    return

        if child.type == "pointer_declarator":
            if has_descendant(child, "function_declarator"):
                for sub in iter_all(child):
                    if sub.type in ("type_identifier", "identifier"):
                        if not is_inside_param_list(sub):
                            name = source_bytes[sub.start_byte:sub.end_byte].decode()
                            names.add(name)
                            return


# ---- Pass 0a: function-like macro call map ----


def scan_macros(root, source_bytes) -> dict[str, str]:
    """Collect function-like macro --> first callee mapping.

    tree-sitter does NOT parse the preproc_arg body into AST, so we use
    regex text matching on the body text.
    """
    macros = {}
    for node in iter_all(root):
        if node.type != "preproc_function_def":
            continue

        macro_name = None
        body = None
        param_names = set()

        for child in node.children:
            if child.type == "identifier" and macro_name is None:
                macro_name = source_bytes[child.start_byte:child.end_byte].decode()
            elif child.type == "preproc_params":
                params_text = source_bytes[child.start_byte:child.end_byte].decode()
                param_names = set(re.findall(r'\b(\w+)\b', params_text))
            elif child.type == "preproc_arg":
                body = source_bytes[child.start_byte:child.end_byte].decode()

        if macro_name and body:
            body_clean = re.sub(r'^do\s*\{?\s*', '', body.strip())
            call_match = re.search(r'(\w+)\s*\(', body_clean)
            if call_match:
                callee = call_match.group(1)
                if callee not in param_names and callee not in _C_KEYWORDS:
                    macros[macro_name] = callee

    return macros


# ---- Pass 0b: global fnptr variable names ----


def scan_global_fnptrs(root, source_bytes, typedef_fnptr_names: set[str]) -> set[str]:
    """Collect global (file-scope) fnptr variable names.

    Does NOT recurse into function_definition bodies -- function-scoped
    fnptr params/locals are detected in Phase 1+2 by _call_analyzer.
    """
    names = set()
    _scan_globals_inner(root, source_bytes, typedef_fnptr_names, names)
    return names


def _scan_globals_inner(node, source_bytes, typedef_fnptr_names, names):
    # Stop at function bodies -- those are handled in Phase 1+2
    if node.type == "function_definition":
        return
    if node.type == "compound_statement":
        return

    if node.type == "declaration":
        _extract_fnptr_from_declaration(node, source_bytes, names, typedef_fnptr_names)

    for child in node.children:
        _scan_globals_inner(child, source_bytes, typedef_fnptr_names, names)


def _extract_fnptr_from_declaration(decl_node, source_bytes, names, typedef_names):
    for child in iter_all(decl_node):
        if child.type == "init_declarator":
            if has_descendant(child, "function_declarator"):
                name = find_first_id(child, source_bytes)
                if name:
                    names.add(name)
                    return
            type_name = get_type_name(decl_node, source_bytes)
            if type_name and type_name in typedef_names:
                name = find_first_id(child, source_bytes)
                if name:
                    names.add(name)
```

- [ ] **Step 2: Smoke test — scan typedefs**

Run: `.venv/bin/python3 -c "
import os, sys
sys.path.insert(0, '.')
from module_a._parser import create_parser, parse_file
from module_a._project_scanner import scan_typedefs

p = create_parser()
root, src = parse_file(p, 'module_a/tests/fixtures/cross_file/example_1_typedef/types.h')
names = scan_typedefs(root, src)
print('typedefs:', names)
assert 'callback_t' in names, f'expected callback_t, got {names}'
print('PASS')
"` 
Expected: `typedefs: {'callback_t'}` then `PASS`

- [ ] **Step 3: Smoke test — scan macros**

Run: `.venv/bin/python3 -c "
import os, sys
sys.path.insert(0, '.')
from module_a._parser import create_parser, parse_file
from module_a._project_scanner import scan_macros

p = create_parser()
root, src = parse_file(p, 'module_a/tests/fixtures/cross_file/example_2_macro/api.h')
macros = scan_macros(root, src)
print('macros:', macros)
assert macros.get('CALL_API') == 'do_api_call', f'expected CALL_API->do_api_call, got {macros}'
print('PASS')
"` 
Expected: `macros: {'CALL_API': 'do_api_call'}` then `PASS`

- [ ] **Step 4: Smoke test — scan global fnptrs with cross-file typedefs**

Run: `.venv/bin/python3 -c "
import os, sys
sys.path.insert(0, '.')
from module_a._parser import create_parser, parse_file
from module_a._project_scanner import scan_global_fnptrs

p = create_parser()
root, src = parse_file(p, 'module_a/tests/fixtures/cross_file/example_1_typedef/main.c')
names = scan_global_fnptrs(root, src, {'callback_t'})
print('globals:', names)
assert 'handler' in names, f'expected handler in globals, got {names}'
print('PASS')
"` 
Expected: `globals: {'handler'}` then `PASS`

- [ ] **Step 5: Commit**

```bash
git add module_a/_project_scanner.py
git commit -m "feat(module-a): add _project_scanner.py for Phase 0 cross-file symbol collection

ProjectSymbols dataclass + scan_typedefs/scan_macros (Pass 0a, no cross-file deps)
+ scan_global_fnptrs (Pass 0b, needs merged typedef set). Scope-constrained:
does not recurse into function bodies for global scan.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: Create `_call_analyzer.py` — Phase 1+2 per-file call analysis

**Files:**
- Create: `module_a/_call_analyzer.py`

Combines `indirect_detector.py` logic + `_walk_ast` + `_expand_local_fnptr_names` + convenience `parse_file()`.
Extracted from `c_parser.py` lines 187-380 and all of `indirect_detector.py`.

- [ ] **Step 1: Write the file**

```python
"""Phase 1+2: per-file call analysis using project-wide symbols."""
import logging

from module_a.models import FunctionNode, DirectEdge, IndirectPoint
from module_a.uid_generator import compute_uid
from module_a._project_scanner import ProjectSymbols
from module_a._ast_helpers import (
    iter_all, has_descendant, find_first_id, get_type_name, find_identifier,
)

logger = logging.getLogger(__name__)

# Merged from indirect_detector.py
_INDIRECT_CALLEE_TYPES = frozenset({
    "field_expression",
    "pointer_expression",
    "subscript_expression",
    "cast_expression",
    "call_expression",
    "parenthesized_expression",
    "conditional_expression",
})


class CallAnalyzer:
    """Per-file call graph analysis using project-wide symbols."""

    def __init__(self, symbols: ProjectSymbols, filepath: str,
                 source_bytes: bytes):
        self._symbols = symbols
        self._filepath = filepath
        self._source = source_bytes
        self.functions: list[FunctionNode] = []
        self.edges: list[DirectEdge] = []
        self.indirect_points: list[IndirectPoint] = []

    def analyze(self, root) -> tuple[list, list, list]:
        """Walk the AST and return (functions, edges, indirect_points)."""
        self._walk(root)
        return self.functions, self.edges, self.indirect_points

    # ---- internal ----

    def _walk(self, node, current_func=None, local_fnptr_names=None):
        if node.type == "function_definition":
            func_name = find_identifier(
                node.child_by_field_name("declarator") or node,
                self._source,
            )
            if func_name and node.has_error:
                logger.warning("%s:%d: syntax error in function '%s', skipping",
                               self._filepath, node.start_point[0] + 1, func_name)
                for child in node.children:
                    self._walk(child, current_func, local_fnptr_names)
                return

            func_name = find_identifier(
                node.child_by_field_name("declarator") or node,
                self._source,
            )
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
                self.functions.append(fn)

                func_local_names = set(self._symbols.global_fnptr_names)

                declarator = node.child_by_field_name("declarator")
                if declarator:
                    param_names = set()
                    _extract_fnptr_params(declarator, self._source, param_names,
                                          self._symbols.typedef_fnptr_names)
                    func_local_names.update(param_names)

                body = node.child_by_field_name("body")
                if body:
                    self._expand_local_fnptr_names(body, func_local_names)

                for child in node.children:
                    self._walk(child, func_name, func_local_names)
                return

        elif node.type == "call_expression" and current_func:
            callee_node = node.child_by_field_name("function")
            if callee_node:
                line = node.start_point[0] + 1
                self._classify_call(callee_node, current_func, local_fnptr_names, line)

        for child in node.children:
            self._walk(child, current_func, local_fnptr_names)

    def _classify_call(self, callee_node, current_func, local_fnptr_names,
                       line) -> None:
        callee_text = self._source[callee_node.start_byte:callee_node.end_byte].decode()

        # Priority 1: macro expansion
        if callee_node.type == "identifier" and callee_text in self._symbols.macro_call_map:
            self.edges.append(DirectEdge(
                caller=current_func,
                callee=self._symbols.macro_call_map[callee_text],
                file=self._filepath,
                line=line,
            ))
            return

        # Priority 2: indirect call by AST type
        if callee_node.type in _INDIRECT_CALLEE_TYPES:
            self._add_indirect_point(current_func, callee_node, line)
            return

        # Priority 3: indirect call by known fnptr name
        effective_names = (local_fnptr_names if local_fnptr_names is not None
                           else self._symbols.global_fnptr_names)
        if callee_node.type == "identifier" and callee_text in effective_names:
            self._add_indirect_point(current_func, callee_node, line)
            return

        # Priority 4: direct call
        if callee_node.type == "identifier":
            self.edges.append(DirectEdge(
                caller=current_func,
                callee=callee_text,
                file=self._filepath,
                line=line,
            ))

    def _add_indirect_point(self, func, callee_node, line):
        expression = self._source[callee_node.start_byte:callee_node.end_byte].decode()
        uid = compute_uid(self._filepath, func, line, expression)
        self.indirect_points.append(IndirectPoint(
            uid=uid, func=func, file=self._filepath,
            line=line, expression=expression,
        ))

    # ---- local fnptr expansion ----

    def _expand_local_fnptr_names(self, body_node, local_names):
        """Iteratively expand local_names from assignments in function body.

        Stops when the set stabilizes (typically 1-3 iterations).
        """
        changed = True
        while changed:
            changed = False
            new_names = set()
            for node in iter_all(body_node):
                names = _extract_names_from_assignment(
                    node, self._source, local_names,
                    self._symbols.typedef_fnptr_names,
                )
                for name in names:
                    if name not in local_names and name not in new_names:
                        new_names.add(name)
                        changed = True
            local_names.update(new_names)


def _extract_fnptr_params(func_declarator_node, source_bytes, names, typedef_names):
    """Extract fnptr parameter names from a function declarator."""
    for child in iter_all(func_declarator_node):
        if child.type == "parameter_declaration":
            if has_descendant(child, "function_declarator"):
                name = find_first_id(child, source_bytes)
                if name:
                    names.add(name)
            else:
                type_name = get_type_name(child, source_bytes)
                if type_name and type_name in typedef_names:
                    name = find_first_id(child, source_bytes)
                    if name:
                        names.add(name)


def _extract_names_from_assignment(node, source_bytes, local_names, typedef_names):
    """Extract new fnptr names from a declaration or assignment node."""
    found = []

    # Pattern 1: declaration with init_declarator
    if node.type == "declaration":
        type_name = get_type_name(node, source_bytes)
        if type_name and type_name in typedef_names:
            for child in iter_all(node):
                if child.type == "init_declarator":
                    name = find_first_id(child, source_bytes)
                    if name:
                        found.append(name)

        for child in iter_all(node):
            if child.type == "init_declarator":
                if has_descendant(child, "function_declarator"):
                    name = find_first_id(child, source_bytes)
                    if name:
                        found.append(name)

    # Pattern 2: assignment_expression
    elif node.type == "assignment_expression":
        lhs = node.child_by_field_name("left")
        rhs = node.child_by_field_name("right")
        if lhs and rhs:
            rhs_text = source_bytes[rhs.start_byte:rhs.end_byte].decode()
            rhs_involves_fnptr = False

            if rhs.type == "identifier" and rhs_text in local_names:
                rhs_involves_fnptr = True
            elif rhs.type == "field_expression":
                rhs_involves_fnptr = True
            elif rhs.type == "cast_expression":
                for sub in iter_all(rhs):
                    if sub.type == "identifier" and \
                       source_bytes[sub.start_byte:sub.end_byte].decode() in local_names:
                        rhs_involves_fnptr = True
                        break

            if rhs_involves_fnptr:
                lhs_name = find_first_id(lhs, source_bytes)
                if lhs_name:
                    found.append(lhs_name)

    # Pattern 3: expression_statement containing assignment
    elif node.type == "expression_statement":
        for child in node.children:
            found.extend(_extract_names_from_assignment(
                child, source_bytes, local_names, typedef_names))

    return found


# ---- convenience: single-file test helper ----


def parse_file(filepath: str) -> dict:
    """Parse a single C file with empty project symbols.

    Replaces the old c_parser.parse_file() for single-file tests.
    Uses empty ProjectSymbols to reproduce file-local-only behavior.
    Signature and return format match the old function.
    """
    from module_a._parser import create_parser as _create_parser
    from module_a._parser import parse_file as _parse_file

    parser = _create_parser()
    root, src = _parse_file(parser, filepath)
    symbols = ProjectSymbols(set(), set(), {})
    a = CallAnalyzer(symbols, filepath, src)
    funcs, edges, ips = a.analyze(root)
    return {
        "functions": [f.to_dict() for f in funcs],
        "edges": [e.to_dict() for e in edges],
        "indirect_points": [ip.to_dict() for ip in ips],
    }
```

- [ ] **Step 2: Test parse_file() against a fixture**

Run: `.venv/bin/python3 -c "
import os, sys
sys.path.insert(0, '.')
from module_a._call_analyzer import parse_file
result = parse_file('module_a/tests/fixtures/macros/simple_macro/fixture.c')
print('functions:', len(result['functions']))
print('edges:', result['edges'])
print('indirect:', result['indirect_points'])
assert len(result['functions']) == 2
assert any(e['callee'] == 'debug_log' and e['caller'] == 'do_work' for e in result['edges'])
print('PASS')
"` 
Expected: 2 functions, edge with `do_work → debug_log`, then `PASS`

- [ ] **Step 3: Commit**

```bash
git add module_a/_call_analyzer.py
git commit -m "feat(module-a): add _call_analyzer.py for Phase 1+2 per-file call analysis

CallAnalyzer class with _walk, _classify_call (4 priority levels: macro
expansion, AST-type indirect, fnptr-name indirect, direct), _add_indirect_point,
_expand_local_fnptr_names. Includes convenience parse_file() for test use.
Merges logic from c_parser.py + indirect_detector.py.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5: Rewrite `analyzer.py` — project-level orchestrator

**Files:**
- Modify: `module_a/analyzer.py` (full rewrite)

Uses the new modules for two-phase pipeline. Preserves `run_analysis()` signature and output format.

- [ ] **Step 1: Write the rewritten analyzer.py**

```python
"""Module A orchestrator: two-phase pipeline for cross-file call graph analysis."""
import json
import logging
import os

from module_a.ignore_parser import parse_siakamignore, should_exclude
from module_a._parser import create_parser, parse_file
from module_a._project_scanner import (
    ProjectSymbols, scan_typedefs, scan_macros, scan_global_fnptrs,
)
from module_a._call_analyzer import CallAnalyzer

logger = logging.getLogger(__name__)

C_EXTENSIONS = {".c", ".h"}


def run_analysis(project_dir: str, output_dir: str) -> dict:
    os.makedirs(output_dir, exist_ok=True)

    patterns = parse_siakamignore(project_dir)
    files = _discover_files(project_dir, patterns)

    # Phase 0: project-wide symbol collection
    project_symbols = _run_phase0(files)

    # Phase 1+2: per-file call analysis
    all_functions, all_edges, all_indirect_points = _run_phase12(
        files, project_symbols, project_dir)

    # Output
    deduped = _deduplicate_functions(all_functions)
    _write_output(output_dir, project_dir, deduped, all_edges, all_indirect_points)

    logger.info("Module A: %d functions, %d direct edges, %d indirect points",
                len(deduped), len(all_edges), len(all_indirect_points))

    return {
        "functions": deduped,
        "edges": all_edges,
        "indirect_points": all_indirect_points,
    }


# ---- file discovery ----

def _discover_files(project_dir, patterns):
    files = []
    for root, dirs, filenames in os.walk(project_dir):
        if ".siakam_out" in dirs:
            dirs.remove(".siakam_out")
        rel_root = os.path.relpath(root, project_dir)
        if rel_root == ".":
            rel_root = ""

        dirs_to_remove = []
        for d in dirs:
            rel_dir = os.path.join(rel_root, d) if rel_root else d
            if should_exclude(patterns, rel_dir + "/"):
                dirs_to_remove.append(d)
        for d in dirs_to_remove:
            dirs.remove(d)

        for filename in sorted(filenames):
            ext = os.path.splitext(filename)[1].lower()
            if ext not in C_EXTENSIONS:
                continue
            filepath = os.path.join(root, filename)
            rel_path = os.path.relpath(filepath, project_dir)
            if should_exclude(patterns, rel_path):
                continue
            files.append(filepath)
    return files


# ---- Phase 0 ----

def _run_phase0(files):
    # Pass 0a: typedefs + macros (no cross-file dependency)
    all_typedefs = set()
    all_macros = {}
    for fp in files:
        parser = create_parser()
        root, src = parse_file(parser, fp)
        all_typedefs |= scan_typedefs(root, src)
        for k, v in scan_macros(root, src).items():
            if k not in all_macros:
                all_macros[k] = v

    # Pass 0b: global fnptr names (needs full typedef set)
    all_fnptrs = set()
    for fp in files:
        parser = create_parser()
        root, src = parse_file(parser, fp)
        all_fnptrs |= scan_global_fnptrs(root, src, all_typedefs)

    return ProjectSymbols(
        typedef_fnptr_names=all_typedefs,
        global_fnptr_names=all_fnptrs,
        macro_call_map=all_macros,
    )


# ---- Phase 1+2 ----

def _run_phase12(files, symbols, project_dir):
    functions, edges, ips = [], [], []
    for fp in files:
        parser = create_parser()
        root, src = parse_file(parser, fp)
        a = CallAnalyzer(symbols, fp, src)
        funcs, edgs, inds = a.analyze(root)
        _relativize_paths(funcs, edgs, inds, fp, project_dir)
        functions.extend(funcs)
        edges.extend(edgs)
        ips.extend(inds)
    return functions, edges, ips


# ---- path relativization ----

def _relativize_paths(funcs, edgs, ips, filepath, project_dir):
    """Convert full paths to project_dir-relative paths (mutates objects in place)."""
    for fn in funcs:
        fn.file = os.path.relpath(fn.file, project_dir)
        if fn.body_file:
            fn.body_file = os.path.relpath(fn.body_file, project_dir)
    for e in edgs:
        e.file = os.path.relpath(e.file, project_dir)
    for ip in ips:
        ip.file = os.path.relpath(ip.file, project_dir)


# ---- deduplication ----

def _deduplicate_functions(functions):
    """Deduplicate functions: per name, keep the one with has_body=True if available."""
    by_name = {}
    for fn in functions:
        name = fn.name if hasattr(fn, 'name') else fn["name"]
        if name not in by_name:
            by_name[name] = fn
        else:
            existing = by_name[name]
            fn_has_body = fn.has_body if hasattr(fn, 'has_body') else fn.get("has_body")
            ex_has_body = existing.has_body if hasattr(existing, 'has_body') else existing.get("has_body")
            if fn_has_body and not ex_has_body:
                by_name[name] = fn
    result = []
    for fn in by_name.values():
        if hasattr(fn, 'to_dict'):
            result.append(fn.to_dict())
        else:
            result.append(fn)
    return result


# ---- output ----

def _write_output(output_dir, project_dir, functions, edges, indirect_points):
    """Write nodes.json, edges.json, indirect_points.json."""
    nodes_path = os.path.join(output_dir, "nodes.json")
    with open(nodes_path, "w") as f:
        json.dump({"project_dir": project_dir, "functions": functions}, f, indent=2)

    edges_path = os.path.join(output_dir, "edges.json")
    with open(edges_path, "w") as f:
        json.dump({"edges": edges}, f, indent=2)

    indirect_path = os.path.join(output_dir, "indirect_points.json")
    with open(indirect_path, "w") as f:
        json.dump({"indirect_points": indirect_points}, f, indent=2)
```

- [ ] **Step 2: Run end-to-end smoke test**

Run: `.venv/bin/python3 -c "
import os, sys, tempfile, json
sys.path.insert(0, '.')
from module_a.analyzer import run_analysis

with tempfile.TemporaryDirectory() as tmpdir:
    result = run_analysis('module_a/tests/fixtures/cross_file/example_3_both', tmpdir)
    print('functions:', len(result['functions']))
    print('edges:', len(result['edges']))
    print('indirect:', len(result['indirect_points']))

    # Check nodes.json exists
    with open(os.path.join(tmpdir, 'nodes.json')) as f:
        nodes = json.load(f)
    assert len(nodes['functions']) == 2  # send_notification, run

    # Check edges exist
    with open(os.path.join(tmpdir, 'edges.json')) as f:
        edges_data = json.load(f)
    callees = {(e['caller'], e['callee']) for e in edges_data['edges']}
    assert ('send_notification', 'printf') in callees
    assert ('run', 'send_notification') in callees  # macro expansion

    # Check indirect points
    with open(os.path.join(tmpdir, 'indirect_points.json')) as f:
        ip_data = json.load(f)
    assert len(ip_data['indirect_points']) == 1

    print('PASS')
"` 
Expected: 2 functions, 2 edges, 1 indirect point, then `PASS`

- [ ] **Step 3: Commit**

```bash
git add module_a/analyzer.py
git commit -m "feat(module-a): rewrite analyzer.py with two-phase project-level pipeline

Phase 0a: project-wide typedef + macro collection
Phase 0b: global fnptr names using merged typedef set
Phase 1+2: per-file call analysis with shared ProjectSymbols
Extracted helpers: _discover_files, _relativize_paths, _write_output
Switched from print() to logging module

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 6: Delete old files and update tests

**Files:**
- Delete: `module_a/c_parser.py`
- Delete: `module_a/indirect_detector.py`
- Modify: `module_a/tests/test_direct_edges.py`
- Modify: `module_a/tests/test_indirect_detection.py`
- Modify: `module_a/tests/test_function_detection.py`
- Modify: `module_a/tests/test_macro_handling.py`
- Modify: `module_a/tests/test_syntax_error.py`

- [ ] **Step 1: Delete old source files**

```bash
git rm module_a/c_parser.py module_a/indirect_detector.py
```

- [ ] **Step 2: Update test imports — test_direct_edges.py**

Read the file first, then apply the single-line import change.

Edit `module_a/tests/test_direct_edges.py`, change line 8:
```python
# Before
from module_a.c_parser import parse_file

# After
from module_a._call_analyzer import parse_file
```

- [ ] **Step 3: Update test imports — test_indirect_detection.py**

Edit `module_a/tests/test_indirect_detection.py`, change line 8:
```python
# Before
from module_a.c_parser import parse_file

# After
from module_a._call_analyzer import parse_file
```

- [ ] **Step 4: Update test imports — test_function_detection.py**

Read the file, then change its import:
```python
# After
from module_a._call_analyzer import parse_file
```

- [ ] **Step 5: Update test imports — test_macro_handling.py**

Change line 6:
```python
# Before
from module_a.c_parser import parse_file

# After
from module_a._call_analyzer import parse_file
```

- [ ] **Step 6: Update test imports — test_syntax_error.py**

Change the import:
```python
# After
from module_a._call_analyzer import parse_file
```

- [ ] **Step 7: Run existing test suite**

Run: `.venv/bin/python3 -m pytest module_a/tests/ -v 2>&1 | tail -60`
Expected: All tests pass. The 11 updated fixtures and 2 new macro_expansion fixtures produce correct results.

- [ ] **Step 8: Commit**

```bash
git add module_a/tests/
git commit -m "refactor(module-a): remove c_parser.py, indirect_detector.py; update test imports

Tests now use from module_a._call_analyzer import parse_file.
The convenience parse_file() preserves the old function's interface.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 7: Add `test_cross_file.py` — integration test for cross-file features

**Files:**
- Create: `module_a/tests/test_cross_file.py`

Tests `run_analysis()` on the cross_file fixture directories.

- [ ] **Step 1: Write the test file**

```python
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from module_a.analyzer import run_analysis


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "cross_file")


def discover_cross_file_fixtures():
    fixtures = []
    for example in sorted(os.listdir(FIXTURES_DIR)):
        example_path = os.path.join(FIXTURES_DIR, example)
        if not os.path.isdir(example_path):
            continue
        fixtures.append((example, example_path))
    return fixtures


@pytest.mark.parametrize("example,fixture_dir", discover_cross_file_fixtures())
def test_cross_file_nodes(example, fixture_dir):
    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_analysis(fixture_dir, tmpdir)

        nodes_path = os.path.join(fixture_dir, "ground_truth_nodes.json")
        if os.path.exists(nodes_path):
            with open(nodes_path) as f:
                expected = json.load(f)
            result_funcs = {(f["name"], f["file"]) for f in result["functions"]}
            expected_funcs = {(f["name"], f["file"]) for f in expected["functions"]}
            assert result_funcs == expected_funcs, \
                f"{example} nodes mismatch:\nExtra: {result_funcs - expected_funcs}\nMissing: {expected_funcs - result_funcs}"


@pytest.mark.parametrize("example,fixture_dir", discover_cross_file_fixtures())
def test_cross_file_edges(example, fixture_dir):
    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_analysis(fixture_dir, tmpdir)

        edges_path = os.path.join(fixture_dir, "ground_truth_edges.json")
        if os.path.exists(edges_path):
            with open(edges_path) as f:
                expected = json.load(f)
            result_edges = {(e["caller"], e["callee"], e["line"]) for e in result["edges"]}
            expected_edges = {(e["caller"], e["callee"], e["line"]) for e in expected["edges"]}
            assert result_edges == expected_edges, \
                f"{example} edges mismatch:\nExtra: {result_edges - expected_edges}\nMissing: {expected_edges - result_edges}"


@pytest.mark.parametrize("example,fixture_dir", discover_cross_file_fixtures())
def test_cross_file_indirect(example, fixture_dir):
    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_analysis(fixture_dir, tmpdir)

        indirect_path = os.path.join(fixture_dir, "ground_truth_indirect.json")
        if os.path.exists(indirect_path):
            with open(indirect_path) as f:
                expected = json.load(f)

            def normalize(ip):
                return (ip["func"], ip["file"], ip["line"], ip["expression"])

            result_points = {normalize(ip) for ip in result["indirect_points"]}
            expected_points = {normalize(ip) for ip in expected["indirect_points"]}
            assert result_points == expected_points, \
                f"{example} indirect mismatch:\nExtra: {result_points - expected_points}\nMissing: {expected_points - result_points}"

            for ip in result["indirect_points"]:
                assert len(ip["uid"]) == 8
                assert all(c in "0123456789abcdef" for c in ip["uid"])


def test_cross_file_example_3_output_files():
    """Verify that run_analysis writes correct output files for example_3_both."""
    fixture_dir = os.path.join(FIXTURES_DIR, "example_3_both")
    with tempfile.TemporaryDirectory() as tmpdir:
        run_analysis(fixture_dir, tmpdir)

        for filename in ["nodes.json", "edges.json", "indirect_points.json"]:
            path = os.path.join(tmpdir, filename)
            assert os.path.isfile(path), f"Missing output file: {filename}"
```

- [ ] **Step 2: Run cross-file tests**

Run: `.venv/bin/python3 -m pytest module_a/tests/test_cross_file.py -v`
Expected: 10 tests pass (3 parametrized × 3 fixtures + 1 output check)

- [ ] **Step 3: Commit**

```bash
git add module_a/tests/test_cross_file.py
git commit -m "test(module-a): add test_cross_file.py for cross-file feature integration

Parametric tests over cross_file fixtures (example_1_typedef,
example_2_macro, example_3_both) covering nodes, edges, indirect points.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 8: Add `test_parser_no_global_state` — global state elimination verification

**Files:**
- Create: `module_a/tests/test_parser_isolation.py`

- [ ] **Step 1: Write the test file**

```python
"""Verify _parser has no global mutable state."""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from module_a._parser import create_parser, parse_file


FIXTURE = os.path.join(
    os.path.dirname(__file__), "fixtures", "macros", "simple_macro", "fixture.c"
)


def test_create_parser_returns_independent_instances():
    p1 = create_parser()
    p2 = create_parser()
    assert p1 is not p2, "create_parser() should return distinct instances"


def test_parsers_do_not_share_state():
    p1 = create_parser()
    p2 = create_parser()

    root1, src1 = parse_file(p1, FIXTURE)
    root2, src2 = parse_file(p2, FIXTURE)

    # Both should produce a valid translation_unit
    assert root1.type == "translation_unit"
    assert root2.type == "translation_unit"

    # Source bytes should be identical for same file
    assert src1 == src2


def test_parser_reuse_produces_same_result():
    """Calling parse_file twice with the same parser on the same file
    should produce equivalent results."""
    p = create_parser()
    root1, _ = parse_file(p, FIXTURE)
    root2, _ = parse_file(p, FIXTURE)
    assert root1.type == root2.type == "translation_unit"
```

- [ ] **Step 2: Run isolation tests**

Run: `.venv/bin/python3 -m pytest module_a/tests/test_parser_isolation.py -v`
Expected: 3 tests pass

- [ ] **Step 3: Commit**

```bash
git add module_a/tests/test_parser_isolation.py
git commit -m "test(module-a): add test_parser_isolation.py for parser global state verification

Verify create_parser() returns independent instances and parsers
do not share state across invocations.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 9: Final verification — full test suite

- [ ] **Step 1: Run complete module_a test suite**

Run: `.venv/bin/python3 -m pytest module_a/tests/ -v 2>&1`
Expected: All tests pass with no failures or errors.

- [ ] **Step 2: Run module_c integration test (if any)**

Run: `.venv/bin/python3 -m pytest module_c/tests/ -v 2>&1`
Expected: All tests pass.

- [ ] **Step 3: Run e2e integration test**

Run: `.venv/bin/python3 -m pytest tests/ -v 2>&1`
Expected: All tests pass.

- [ ] **Step 4: Verify old files are fully removed**

Run: `ls module_a/c_parser.py module_a/indirect_detector.py 2>&1`
Expected: `No such file or directory`

- [ ] **Step 5: Final commit (if any cleanup needed)**

```bash
git status
# If clean, done. If any straggling references need cleanup:
git add -A
git commit -m "chore(module-a): final cleanup after refactor"
```
