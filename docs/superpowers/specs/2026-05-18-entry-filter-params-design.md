# Entry Function Filter: Parameter Type and File Extension Constraints

Date: 2026-05-18

## Motivation

`find_entry_functions()` in Module C currently identifies entry functions by two rules: function has a body (`has_body=True`), and function has no incoming call edges (indegree=0). Add two more constraints to narrow the results to meaningful entry points.

## New Constraints

1. **`.c` file**: Function body must reside in a `.c` file. Header-only declarations with `has_body=False` or `body_file` ending in `.h` are excluded.
2. **Qualifying parameters**: Function must have at least one parameter whose type text contains a pointer (`*`), struct keyword (`struct`), or array subscript (`[`). Functions with zero parameters or only basic scalar types (`int`, `long`, `char`, etc.) are excluded.

## Design

### Module A changes — capture parameter types

`FunctionNode` (module_a/models.py) gets a new field:

```python
params: list[str] = field(default_factory=list)
```

In `_call_analyzer.py`, when parsing a function definition, extract the type text of each parameter declaration from the AST `parameter_list` child. Store in `FunctionNode.params` and serialize via `to_dict()`.

Parameter type extraction walks `parameter_declaration` nodes inside the `function_declarator`, collects the text of the type sub-node (everything except the parameter name identifier).

`nodes.json` output gains a `"params"` key per function, e.g. `"params": ["int *", "struct device *"]` or `"params": []`.

### Module C changes — enhanced filtering

`find_entry_functions()` in module_c/entry_finder.py adds:

1. Check `body_file` ends with `.c` (case-insensitive). Nodes missing `body_file` or ending in `.h` are skipped.
2. Check `params` list: at least one element contains `*`, `struct`, or `[`. Empty `params` means the function takes no arguments → excluded.

A helper function `_has_qualifying_params(params)` encapsulates the type-matching logic.

## Tests

- Module A unit test: verify `FunctionNode.params` is populated for functions with parameters, empty for parameterless functions.
- Module C:
  - Function in `.h` with body excluded even if it qualifies on params
  - Function in `.c` with only `int` params excluded
  - Function in `.c` with `int *` param included
  - Function in `.c` with `struct foo` param included
  - Function in `.c` with `char buf[256]` param included
  - Function in `.c` with zero params excluded
  - Existing expected fixtures updated with `params` field
