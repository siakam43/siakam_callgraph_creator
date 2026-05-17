# Module A Architecture Analysis

Date: 2026-05-17

## Data Flow Overview

```
analyzer.run_analysis()
  ├─ ignore_parser.parse_siakamignore() → patterns
  ├─ os.walk + should_exclude() → file list
  └─ for each file:
       └─ c_parser.parse_file()
            ├─ tree-sitter parse AST
            ├─ Phase 0: _collect_typedefs_and_globals()
            ├─ Phase 1+2: _walk_ast() [recursive, 12 params]
            │    ├─ function definition → FunctionNode
            │    ├─ call expression → DirectEdge / IndirectPoint
            │    └─ _expand_local_fnptr_names() [iterative scan]
            └─ return {functions, edges, indirect_points}
```

## Module A File Map

| File | Lines | Responsibility |
|------|-------|----------------|
| `__init__.py` | 1 | Empty |
| `models.py` | 61 | Three dataclasses: FunctionNode, DirectEdge, IndirectPoint |
| `analyzer.py` | 101 | Orchestrator: file discovery, parsing orchestration, dedup, JSON I/O |
| `c_parser.py` | 380 | Core: tree-sitter parsing, AST walk, call classification, fnptr expansion |
| `uid_generator.py` | 7 | SHA256-based UID generation |
| `ignore_parser.py` | 46 | `.siakamignore` parsing |
| `indirect_detector.py` | 36 | Indirect call type classification |

## Architecture Issues

### P0 — c_parser.py is a monolith (380 lines)

This single file handles: tree-sitter parser lifecycle (global state), syntax error reporting, typedef/global fnptr collection (Phase 0), recursive AST traversal, function definition extraction, call classification (direct vs indirect), local fnptr name expansion, and assignment pattern matching (3 patterns). By the Single Responsibility Principle, this should be at least 3-4 separate modules.

### P0 — _walk_ast is a god function (12 parameters)

```python
def _walk_ast(node, source_bytes, filepath, functions, edges, indirect_points,
              global_fnptr_names, fnptr_typedefs, current_func=None,
              local_fnptr_names=None):
```

AST traversal, function extraction, call classification, and indirect call detection are all coupled in one recursive traversal. The `local_fnptr_names=None` default also means the function has two distinct behavioral modes (inside vs. outside a function body), making it harder to reason about.

### P1 — Module boundary between analyzer.py and c_parser.py is blurred

`analyzer.py` handles: file discovery, ignore-rule application, path relativization (lines 53-61), parsing dispatch, deduplication, and JSON serialization. The path relativization logic is embedded in the parsing loop and tightly coupled to file iteration. The orchestrator knows too much about the internal structure of parsing results.

### P1 — Output format schema is implicit

Module A's output (`nodes.json`, `edges.json`, `indirect_points.json`) is the contract consumed by modules B and C. But this contract is defined implicitly through `to_dict()` methods and hand-built dict structures. If the output format changes, all three modules need to be audited.

### P2 — Global mutable state (c_parser.py:11-12)

```python
C_LANGUAGE = Language(tsc.language())
PARSER = Parser(C_LANGUAGE)
```

Module-level global objects mean: unsafe for multi-threaded use, parser instances cannot be substituted in tests, and parser state could leak between invocations.

### P2 — _deduplicate_functions strategy is incomplete

```python
elif fn.get("has_body") and not by_name[name].get("has_body"):
    by_name[name] = fn
```

Only checks `has_body`. If the same function has two definitions with bodies (e.g., platform-specific implementations via `#ifdef`), one is silently discarded. The decision to keep the first body-bearing definition over a second one is arbitrary.

### P2 — Indirect call detection logic split across two files

`indirect_detector.py` defines `INDIRECT_CALLEE_TYPES` and basic classification logic, but the actual call classification (when to produce DirectEdge vs IndirectPoint) lives in `c_parser.py:241-267`. Understanding or modifying indirect call detection requires reading both files.

### P3 — Uses print() instead of logging module

`analyzer.py:82-84` and `c_parser.py:52-53,196-198` use `print()` directly. The Python `logging` module would allow controlling log levels and output destinations during testing.

### P3 — Defensive isinstance checks hint at data flow uncertainty

```python
"functions": [fn.to_dict() if isinstance(fn, FunctionNode) else fn
              for fn in functions],
```

`parse_file` always produces `FunctionNode` objects internally, so this isinstance check is unreachable defensive code. It suggests uncertainty about the data flow contract.

### P3 — No real error recovery for syntax errors

The requirements specify: "skip errored parts, do not affect analysis of other parts." The current implementation checks `root.has_error` at the top level and `node.has_error` for individual functions, but only prints a warning—it does not actually skip call analysis within errored function nodes.

## Severity Summary

| Priority | Issue | Impact |
|----------|-------|--------|
| P0 | c_parser.py monolith | Poor maintainability, high risk for new features |
| P0 | _walk_ast god function | Hard to test, understand, modify |
| P1 | Blurred module boundary | analyzer and parser responsibilities overlap |
| P1 | Implicit output schema | Fragile cross-module coupling |
| P2 | Global state | Limited testability |
| P2 | Incomplete dedup strategy | Edge-case data loss |
| P2 | Split indirect detection logic | Knowledge scattered across files |
| P3 | print() instead of logging | Hard to control output in tests |
| P3 | Defensive isinstance checks | Code smell |
| P3 | Weak error recovery | Doesn't fully meet requirements |
