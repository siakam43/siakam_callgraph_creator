# Module A Refactor Design

Date: 2026-05-17

## Scope

Module A internal refactor only. External interfaces unchanged:
- `run_analysis(project_dir, output_dir) -> dict` signature preserved
- Output files (`nodes.json`, `edges.json`, `indirect_points.json`) format preserved

## Goals

1. Fix the P0 monolith — split `c_parser.py` (380 lines) into focused modules, each <200 lines
2. Fix the P0 god function — `_walk_ast` (12 params) decomposed
3. Eliminate global mutable state (`C_LANGUAGE`, `PARSER`) — use dependency injection
4. Fix cross-file typedef/macro information loss — two-phase project-level pipeline
5. Introduce `logging` module instead of `print()`

## File Structure After Refactor

```
module_a/
├── __init__.py              # preserved
├── models.py                # preserved
├── analyzer.py              # rewritten: project-level orchestration
├── ignore_parser.py         # preserved
├── uid_generator.py         # preserved
│
├── _parser.py               # new: tree-sitter lifecycle + parse gate (~40 lines)
├── _project_scanner.py      # new: Phase 0 cross-file symbol collection (~130 lines)
├── _call_analyzer.py        # new: Phase 1+2 per-file call analysis (~200 lines)
├── _ast_helpers.py          # new: shared AST utility functions (~50 lines)
│
└── indirect_detector.py     # deleted, merged into _call_analyzer.py
```

## Architecture: Two-Phase Project-Level Pipeline

### Problem with Current Design

Each file is analyzed independently with empty symbol sets every time:

```python
# c_parser.py — current (broken)
fnptr_typedefs = set()        # reset per file
global_fnptr_names = set()    # reset per file
```

Consequence: typedefs and macros defined in one file are invisible to other files. Example:

- `types.h` defines `typedef void (*callback_t)(int);` and `#define CALL_DEBUG() debug_log(__func__)`
- `main.c` uses `callback_t handler = my_func;` and `CALL_DEBUG();`
- `main.c` cannot see `callback_t` as fnptr type, nor expand `CALL_DEBUG`

### New Design

Phase 0 is split into two sub-passes because detecting global fnptr variables
(Pass 0b) depends on knowing typedef fnptr names from other files (Pass 0a).
Macro collection has no such dependency and runs in Pass 0a alongside typedefs.

```
analyzer.run_analysis(project_dir, output_dir)
  │
  ├─ [Phase 0a: collect typedefs + macros (no cross-file dependency)]
  │   for each file:
  │     parser = _parser.create_parser()
  │     root, src = _parser.parse_file(parser, filepath)
  │     typedefs = _project_scanner.scan_typedefs(root, src)
  │     macros = _project_scanner.scan_macros(root, src)
  │   all_typedefs = union(typedefs)
  │   all_macros = merge(macros)
  │
  ├─ [Phase 0b: collect globals (with full typedef set)]
  │   for each file:
  │     parser = _parser.create_parser()
  │     root, src = _parser.parse_file(parser, filepath)
  │     fnptrs = _project_scanner.scan_global_fnptrs(root, src, all_typedefs)
  │   project_symbols = ProjectSymbols(all_typedefs, fnptrs, all_macros)
  │
  ├─ [Phase 1+2: per-file call analysis]
  │   for each file:
  │     parser = _parser.create_parser()
  │     root, src = _parser.parse_file(parser, filepath)
  │     analyzer = _call_analyzer.CallAnalyzer(project_symbols, filepath, src)
  │     funcs, edges, ips = analyzer.analyze(root)
  │     all_functions += funcs
  │     all_edges += edges
  │     all_indirect_points += ips
  │
  └─ [output]
      dedup → write nodes.json / edges.json / indirect_points.json
```

## ProjectSymbols Dataclass

```python
@dataclass
class ProjectSymbols:
    """Cross-file function-related symbols collected in Phase 0."""
    typedef_fnptr_names: set[str]
    global_fnptr_names: set[str]
    macro_call_map: dict[str, str]   # macro_name -> callee_name
```

Defined in `_project_scanner.py`. Passed from `analyzer` → `CallAnalyzer` for each file in Phase 1+2.

## Module Design

### _parser.py — tree-sitter Lifecycle (~40 lines)

```python
def create_parser() -> Parser:
    """Create a fresh tree-sitter Parser instance. No global state."""

def parse_file(parser: Parser, filepath: str) -> tuple[object, bytes]:
    """Parse a C source file.
    Returns (root_node, source_bytes).
    Reports syntax errors to stderr via logging module; does not interrupt.
    """
```

Key:
- `parser` injected as parameter — testable, no shared state
- Pure parsing only, zero analysis logic
- Returns both `root_node` and `source_bytes` (needed by both phases for identifier text decoding)
- Error reporting via `logging.warning()` instead of `print()`

### _ast_helpers.py — Shared AST Utilities (~50 lines)

```python
def find_first_identifier(node, source_bytes) -> str | None:
    """Depth-first search for first identifier in subtree."""

def has_descendant(node, target_type: str) -> bool:
    """Check if subtree contains a node of the given type."""

def find_identifier(node, source_bytes) -> str | None:
    """Extract identifier from function declarator nodes."""

def get_type_name(decl_node, source_bytes) -> str | None:
    """Extract type_identifier name from a declaration."""

def iter_all(node) -> Iterator:
    """Yield node and all descendants."""

def is_inside_param_list(node) -> bool:
    """Check if node has a parameter_list ancestor."""
```

These are extracted directly from current `c_parser.py` helper functions. Used by both `_project_scanner.py` and `_call_analyzer.py`.

### _project_scanner.py — Phase 0 (~160 lines)

Three functions, mapped to the two sub-passes:

```python
def scan_typedefs(root, source_bytes) -> set[str]:
    """Pass 0a: collect typedef fnptr names. No cross-file dependency."""

def scan_macros(root, source_bytes) -> dict[str, str]:
    """Pass 0a: collect function-like macro → first callee mapping. No cross-file dependency."""

def scan_global_fnptrs(root, source_bytes,
                        typedef_fnptr_names: set[str]) -> set[str]:
    """Pass 0b: collect global fnptr variable names.
    Requires the complete typedef set from Pass 0a for correct fnptr detection.
    """
```

#### Symbol 1: typedef fnptr names

Migrated from current `_extract_typedef_fnptr`. Handles:

```c
typedef void (name)(params);          // function_declarator wrapping type_identifier
typedef void (*name)(params);         // pointer_declarator with function_declarator
typedef ret *(*name)(params);         // nested pointer_declarator with fnptr
```

Semantics: `name` becomes a known fnptr type identifier.

#### Symbol 2: global fnptr variable names

Migrated from current `_extract_fnptr_from_declaration`. Handles:

```c
typedef_name var;                          // variable of known fnptr typedef type
void (*var)(params);                      // inline function pointer declaration
void (*var)(params) = init;               // inline fnptr with initializer
typedef_name *var = init;                 // typedef fnptr pointer with init
```

**Scope constraint**: scans only top-level (file-scope) AST nodes. Does NOT recurse into
`function_definition` bodies — function-scoped fnptr parameters and local variables are
detected in Phase 1+2 by `_walk`/`_expand_local_fnptr_names`, not here. This fixes a
current-code subtlety where `_extract_fnptr_params` (called in Phase 0) incorrectly
leaks parameter names into the global set.

Implementation: recurse into `declaration`, `type_definition`, `preproc_def`,
`preproc_function_def` children of `translation_unit`, but stop at `function_definition`
and `compound_statement` boundaries.

Function parameters (handled in `_walk`, Phase 1+2):
```c
void foo(void (*cb)(int));                // fnptr parameter → detected in _walk
void foo(typedef_name cb);                // typedef fnptr parameter → detected in _walk
```

#### Symbol 3: function-like macro call map

Scans `preproc_function_def` nodes. For each function-like macro definition:

```c
#define NAME(...) body
```

Extract the callee of the first function call found in the macro body text.

**Strategy**: tree-sitter does NOT parse the `preproc_arg` body into AST nodes — it is raw text.
Use a regex on the body text to find the first `identifier(args)` pattern:

```c
#define CALL_DEBUG()   debug_log(__func__)       // → {"CALL_DEBUG": "debug_log"}
#define REGISTER(fn)   register_handler(fn)      // → {"REGISTER": "register_handler"}
#define WRAP(a, b)     a(); b()                  // → {"WRAP": "a"} (first only)
```

Implementation outline:
```python
body = source_bytes[preproc_arg.start_byte:preproc_arg.end_byte].decode()
body_clean = re.sub(r'^do\s*\{?\s*', '', body.strip())
match = re.search(r'(\w+)\s*\(', body_clean)
if match:
    callee = match.group(1)
    if callee not in param_names and callee not in C_KEYWORDS:
        macros[macro_name] = callee
```

Where `param_names` is extracted from `preproc_params` text, and `C_KEYWORDS` = `{'if', 'while', 'for', 'switch', 'void', 'return', 'sizeof'}`.

Edge cases:
- If body has no function call (e.g., `#define X y`), no map entry is created — the macro call falls through to direct edge with macro name as callee (existing behavior).
- Multiple calls in body (`do { a(); b(); } while(0)`): only first captured. Complex cases are for Module B (LLM).
- Callee matches a macro parameter name: excluded, no map entry — prevents `#define INVOKE(h) h(0)` from incorrectly mapping `INVOKE → h`.
- Object-like macros (`#define X y`) are `preproc_def` nodes without `preproc_params` — skipped.
- Same macro name defined in multiple files: keep first occurrence (same `#define` from shared header).

#### Merging Across Files

After Pass 0a and 0b, merge across all files:

```python
# Pass 0a: typedefs + macros (no cross-file dependency)
all_typedefs = set()
all_macros = {}
for fp in files:
    root, src = parse_file(parser, fp)
    all_typedefs |= scan_typedefs(root, src)
    for k, v in scan_macros(root, src).items():
        if k not in all_macros:
            all_macros[k] = v

# Pass 0b: global fnptr names (needs full typedef set)
all_fnptrs = set()
for fp in files:
    root, src = parse_file(parser, fp)
    all_fnptrs |= scan_global_fnptrs(root, src, all_typedefs)

project_symbols = ProjectSymbols(all_typedefs, all_fnptrs, all_macros)
```

This two-pass design solves: `types.h` defines `typedef void (*callback_t)(int);`, then `main.c` declares `callback_t handler;`. Pass 0a collects `callback_t` from `types.h`. Pass 0b uses it when scanning `main.c` to correctly detect `handler` as a fnptr variable.

### _call_analyzer.py — Phase 1+2 (~220 lines)

```python
_INDIRECT_CALLEE_TYPES = {
    "field_expression",
    "pointer_expression",
    "subscript_expression",
    "cast_expression",
    "call_expression",
    "parenthesized_expression",
    "conditional_expression",
}


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
        self._walk(root)
        return self.functions, self.edges, self.indirect_points


def parse_file(filepath: str) -> dict:
    """Convenience: parse a single file with empty project symbols.

    Replaces the old c_parser.parse_file() for single-file tests.
    Uses fresh parser + empty ProjectSymbols to reproduce file-local-only behavior.
    """
    from module_a._parser import create_parser, parse_file as _parse
    parser = create_parser()
    root, src = _parse(parser, filepath)
    symbols = ProjectSymbols(set(), set(), {})
    a = CallAnalyzer(symbols, filepath, src)
    funcs, edges, ips = a.analyze(root)
    return {
        "functions": [f.to_dict() for f in funcs],
        "edges": [e.to_dict() for e in edges],
        "indirect_points": [ip.to_dict() for ip in ips],
    }
```

#### _walk Recursive Algorithm

```
_walk(node, current_func=None, local_fnptr_names=None)
  │
  ├─ function_definition
  │    ├─ if node.has_error → log warning, recurse children, return
  │    │   (no FunctionNode created — errored function is skipped)
  │    ├─ extract func_name → FunctionNode → self.functions
  │    ├─ build func_local_names:
  │    │     = self._symbols.global_fnptr_names
  │    │       ∪ fnptr params of this function
  │    │       ∪ names discovered by _expand_local_fnptr_names(body)
  │    └─ recurse children with (current_func=func_name,
  │                               local_fnptr_names=func_local_names)
  │
  ├─ call_expression (if current_func is set)
  │    └─ dispatch via _classify_call()
  │
  └─ recurse children (children are always traversed)
```

#### _classify_call Logic

```python
def _classify_call(self, callee_node, current_func, local_fnptr_names,
                   line) -> None:
    """Classify a call_expression's target and append to edges or indirect_points."""

    # Priority 1: macro expansion
    callee_text = self._source[callee_node.start_byte:callee_node.end_byte].decode()
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
    effective_names = local_fnptr_names if local_fnptr_names is not None \
                      else self._symbols.global_fnptr_names
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
```

#### _add_indirect_point

```python
def _add_indirect_point(self, func: str, callee_node, line: int) -> None:
    expression = self._source[callee_node.start_byte:callee_node.end_byte].decode()
    uid = compute_uid(self._filepath, func, line, expression)
    self.indirect_points.append(IndirectPoint(
        uid=uid, func=func, file=self._filepath,
        line=line, expression=expression,
    ))
```

#### Local Fnptr Name Expansion

```python
def _expand_local_fnptr_names(self, body_node, local_names) -> None:
    """Iterative expansion: scan function body for fnptr assignments.

    Same algorithm as current _expand_local_fnptr_names. 3 patterns:
      1. declaration: "typedef_name var = init;"
         → requires self._symbols.typedef_fnptr_names to recognize typedef_name as fnptr type
      2. assignment_expression: "a = known_name;" / "a = ptr->member;"
         → uses local_names (fnptr variable propagation)
      3. expression_statement: delegate to children
    Iterate until stable (typically 1-3 rounds).
    """
```

### analyzer.py — Rewritten Orchestrator (~120 lines)

```python
import logging

logger = logging.getLogger(__name__)


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

    logger.info("Module A: %d functions, %d edges, %d indirect points",
                len(deduped), len(all_edges), len(all_indirect_points))

    return {"functions": deduped, "edges": all_edges,
            "indirect_points": all_indirect_points}
```

#### _discover_files

Extracted from current `analyzer.py` os.walk loop (lines 18-42). Same logic, same behavior with `.siakamignore`.

#### _run_phase0

```python
def _run_phase0(files: list[str]) -> ProjectSymbols:
    # Pass 0a: typedefs + macros (no cross-file dependency)
    all_typedefs = set()
    all_macros = {}
    for fp in files:
        parser = _parser.create_parser()
        root, src = _parser.parse_file(parser, fp)
        all_typedefs |= _project_scanner.scan_typedefs(root, src)
        for k, v in _project_scanner.scan_macros(root, src).items():
            if k not in all_macros:
                all_macros[k] = v

    # Pass 0b: global fnptr names (needs full typedef set)
    all_fnptrs = set()
    for fp in files:
        parser = _parser.create_parser()
        root, src = _parser.parse_file(parser, fp)
        all_fnptrs |= _project_scanner.scan_global_fnptrs(root, src, all_typedefs)

    return ProjectSymbols(
        typedef_fnptr_names=all_typedefs,
        global_fnptr_names=all_fnptrs,
        macro_call_map=all_macros,
    )
```

#### _run_phase12

```python
def _run_phase12(files, symbols, project_dir):
    functions, edges, ips = [], [], []
    for fp in files:
        parser = _parser.create_parser()
        root, src = _parser.parse_file(parser, fp)
        analyzer = CallAnalyzer(symbols, fp, src)
        funcs, edgs, inds = analyzer.analyze(root)
        _relativize_paths(funcs, edgs, inds, fp, project_dir)
        functions.extend(funcs)
        edges.extend(edgs)
        ips.extend(inds)
    return functions, edges, ips
```

#### _deduplicate_functions

Same algorithm as current `_deduplicate_functions`. Notably keeps the existing behavior (prefer `has_body=True`) as documented in the analysis, with a future note about handling multiple body-bearing definitions.

## Module Dependencies

```
analyzer.py
  ├── ignore_parser.py
  ├── _parser.py
  ├── _project_scanner.py
  │     └── _ast_helpers.py
  └── _call_analyzer.py
        ├── _ast_helpers.py
        ├── models.py
        └── uid_generator.py
```

All `_`-prefixed modules are private to module_a. No circular dependencies.

Note: `_expand_local_fnptr_names` in `_call_analyzer.py` accesses
`self._symbols.typedef_fnptr_names` for Pattern 1 (typedef-based fnptr declarations).
This means `_call_analyzer` depends on `ProjectSymbols` being fully populated by Phase 0.

### Performance Note

Each file is parsed by tree-sitter 3 times (Phase 0a, 0b, 1+2). For typical C projects
(hundreds to low thousands of files), this is acceptable because tree-sitter parses in C
at high speed. A future optimization could cache `(root, source_bytes)` tuples across
phases, trading memory for CPU.

## Call Classification Priority Summary

| Priority | Condition | Result |
|----------|-----------|--------|
| 1 | callee identifier in `macro_call_map` | DirectEdge with expanded callee |
| 2 | callee AST type in `_INDIRECT_CALLEE_TYPES` | IndirectPoint |
| 3 | callee identifier in `local_fnptr_names` | IndirectPoint |
| 4 | callee identifier (plain function call) | DirectEdge |
| — | fallback (unknown structure) | dropped (not reported) |

## What Changes vs. Current

| Aspect | Current | Refactored |
|--------|---------|------------|
| Phase 0 scope | per-file, empty sets each time | project-wide, shared across files |
| Macro handling | none — macro call treated as DirectEdge to macro name | expanded to actual callee via macro_call_map |
| typedef fnptr | file-local only | project-wide |
| Parser instances | 1 global `PARSER` | `create_parser()` factory, injected |
| `_walk_ast` params | 12 | 3 (`node`, `current_func`, `local_fnptr_names`) |
| Error reporting | `print()` | `logging` module |
| `indirect_detector.py` | separate file | merged into `_call_analyzer.py` |

## What Does Not Change

- `models.py`: no changes
- `uid_generator.py`: no changes
- `ignore_parser.py`: no changes
- `_deduplicate_functions` algorithm: preserved (now operates on `FunctionNode` attributes instead of dict keys)
- Output file format (`nodes.json`, `edges.json`, `indirect_points.json`): preserved
- External API (`run_analysis`): preserved

## Migration Notes

### Test imports

Existing tests use `from module_a.c_parser import parse_file`. Since `c_parser.py` is deleted,
tests update the import to the convenience function in `_call_analyzer.py`:

```python
# Before
from module_a.c_parser import parse_file

# After
from module_a._call_analyzer import parse_file
# — function signature and return format unchanged
```

The convenience `parse_file()` uses empty `ProjectSymbols`, reproducing the old
file-local-only behavior. For the new cross-file feature, tests use `run_analysis()` directly.

### _relativize_paths

Extracted from the current `analyzer.py` inline loop (lines 52-61) into a private helper.
Converts full paths in `FunctionNode`, `DirectEdge`, `IndirectPoint` objects to paths relative
to `project_dir`.

### _write_output

Extracted from the current `analyzer.py` inline JSON writes (lines 69-80) into a private helper.
Handles `os.makedirs` + `json.dump` for all three output files.

## Testing Strategy

Existing tests in `module_a/tests/` continue to pass because:
- `c_parser.parse_file()` is replaced by `_parser.parse_file()` + `CallAnalyzer.analyze()`, but the combined output shape is identical
- `_ast_helpers` functions are verbatim copies from current `c_parser.py`

### Updated Fixtures (macro expansion changes callee)

The following 11 existing fixtures had their `ground_truth_edges.json` updated — callee changed from macro name to expanded target:

| Fixture | Change |
|---------|--------|
| `macros/simple_macro` | `do_work → CALL_DEBUG` → `do_work → debug_log` |
| `fnptr-callback/example_5` | `→ unlikely` → `→ __builtin_expect` |
| `fnptr-callback/example_6` | `→ unlikely` → `→ __builtin_expect` |
| `fnptr-cast/example_5` | `→ ASSERT` → `→ assert`; `→ GMP_ASPRINTF_T_INIT` → `→ malloc` |
| `fnptr-cast/example_7` | `→ ASSERT` → `→ assert` |
| `fnptr-global-struct/example_9` | `→ stream_read_tree` → `→ read_tree` |
| `fnptr-global-struct-array/example_7` | `→ likely` → `→ __builtin_expect` |
| `fnptr-library/example_2` | `→ G` → `→ mref` |
| `fnptr-library/example_10` | `→ X509_STORE_set_lookup_crls_cb` → `→ X509_STORE_set_lookup_crls` |
| `fnptr-only/example_6` | `→ unlikely` (2处) → `→ __builtin_expect` |
| `fnptr-struct/example_9` | `→ BIO_printf` → `→ fprintf` |

### New Fixtures Added

**macro_expansion/** — single-file fixtures. Follow same `fixture.c` + `ground_truth_*.json` pattern, auto-discovered by existing `test_direct_edges.py` and `test_indirect_detection.py`:
| Fixture | Tests |
|---------|-------|
| `example_1_simple` | `CALL_DEBUG()` expands to `debug_log` → direct edge |
| `example_2_multi_call` | multi-call macro body `{log(); send();}` → first call (`log`) extracted |

**cross_file/** — multi-file fixtures, require new project-level test `test_cross_file.py` calling `run_analysis()`:
| Fixture | Tests |
|---------|-------|
| `example_1_typedef` | typedef in `types.h`, fnptr variable in `main.c` → indirect point detected |
| `example_2_macro` | macro in `api.h`, call in `main.c` → macro expansion to direct edge |
| `example_3_both` | typedef + macro from two headers used in `main.c` → both features together |

New tests to add:
1. `test_cross_file.py` — project-level integration test using `run_analysis()` on cross_file fixture dirs
2. `test_parser_no_global_state` — verify `create_parser()` returns independent instances
