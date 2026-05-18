# Entry Function Filter: Parameter Type and File Extension Constraints

Date: 2026-05-18

## Motivation

`find_entry_functions()` in Module C currently identifies entry functions by two rules: function has a body (`has_body=True`), and function has no incoming call edges (indegree=0). Add two more constraints to narrow the results to meaningful entry points.

## New Constraints

1. **`.c` file**: Function body must reside in a `.c` file. Header-only declarations with `has_body=False` or `body_file` ending in `.h` are excluded.
2. **Non-trivial parameters**: A function is excluded only when all of its parameters are basic scalar types. Functions with no parameters (or only `void`) are excluded. Functions with at least one non-basic parameter (pointer, struct, union, array, typedef, or any unrecognized type keyword) are retained.

## Design

### Module A changes — capture parameter types

`FunctionNode` (module_a/models.py) gets a new field:

```python
params: list[str] = field(default_factory=list)
```

In `_call_analyzer.py`, when parsing a `function_definition`, walk the `parameter_list` children (if present). For each `parameter_declaration`, extract the **full text** of the node from source bytes. Store the list of parameter text strings in `FunctionNode.params` and serialize via `to_dict()`.

Example: `void func(int x, struct device *dev)` → `params = ["int x", "struct device *dev"]`

`nodes.json` gains a `"params"` key per function.

### Module C changes — enhanced filtering

`find_entry_functions()` in module_c/entry_finder.py adds:

1. Check `body_file` ends with `.c` (case-insensitive). Nodes with missing `body_file` or ending in `.h` are skipped.
2. Check `params`: if empty, or the sole element is `"void"`, the function takes no arguments → excluded.
3. For each param text, strip the parameter name (innermost identifier), remove `const`/`volatile`/`restrict` qualifiers, then check whether the remaining tokens are all in the basic-types set below. If ALL params are basic → excluded.

**Basic type tokens** (function excluded only when every param consists entirely of these):

| Category | Tokens |
|----------|--------|
| C keywords | `int`, `long`, `short`, `char`, `float`, `double`, `unsigned`, `signed`, `void`, `_Bool`, `bool` |
| Fixed-width typedefs | `uint8_t`, `uint16_t`, `uint32_t`, `uint64_t`, `int8_t`, `int16_t`, `int32_t`, `int64_t`, `uintmax_t`, `intmax_t` |
| Standard size typedefs | `size_t`, `ssize_t`, `ptrdiff_t`, `off_t` |
| Kernel abbreviations | `u8`, `u16`, `u32`, `u64`, `s8`, `s16`, `s32`, `s64` |

**Examples**:

```
"int x"              → basic, excluded if all params like this
"int x, int *y"      → * is not in basic set → retained
"unsigned long n"    → basic, excluded if all params like this
"uint32_t count"     → basic
"size_t len"         → basic
"device_t dev"       → device_t not in basic set → retained
"struct foo *p"      → struct, * not in basic set → retained
"union bar u"        → union not in basic set → retained
```

A helper function `_is_basic_params(params)` encapsulates this logic.

## Tests

- Module A: verify `FunctionNode.params` populated correctly for parameterized functions, empty for no-arg functions, `["void"]` for `void` param.
- Module C:
  - Function in `.h` excluded even if params qualify
  - Function in `.c` with only `int` params → excluded
  - Function in `.c` with `int *` param → retained
  - Function in `.c` with `struct foo` param → retained
  - Function in `.c` with `char buf[256]` param → retained
  - Function in `.c` with `uint32_t x, size_t y` → excluded (all params basic)
  - Function in `.c` with `uint32_t x, device_t *d` → retained
  - Function in `.c` with zero params → excluded
  - Function in `.c` with `void` param → excluded
  - Existing expected fixtures updated with `params` field
