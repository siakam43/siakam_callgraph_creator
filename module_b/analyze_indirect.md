# Analyze Indirect Call

You are analyzing indirect call sites (function pointer calls) in a C codebase. Determine the possible target functions (callees) that could be called at each site. Process the given uids one at a time, in sequence.

## Input

A list of indirect call points. Process each one:

```json
{
  "uid": "<hash string>",
  "func": "<caller function name>",
  "file": "<relative path to source file>",
  "line": <line number>,
  "expression": "<the function pointer expression, e.g. ops->read>"
}
```

## Analysis Steps (per uid)

### 1. Write Lock
Immediately create `.siakam_out/indirect/<uid>.json`:
```json
{"uid": "<uid>", "status": "in_progress"}
```

### 2. Locate the Call Site
Read `file`, navigate to `line`, verify the `expression` matches.

### 3. Determine the Function Pointer Type
- `ptr->member`: find the struct/union definition, identify the member's function signature
  - **Grep** for `struct\s+\w*\s*\{` in headers to find the struct definition
  - If the struct uses a **typedef**, also check `typedef struct { ... } name_t;` patterns
- `(*ptr)()` or direct variable: find its declaration with **Grep** for the variable name
- Parameter name: trace back through the caller's parameters
- **Macros**: if the expression involves macros, expand mentally — `CALLBACK(x)` might expand to a function pointer dereference

### 4. Trace the Assignment
Search within `func` and related files:
- Direct assignment: `ptr = target;` or `ptr = &target;`
- Struct field: `obj.ops = &some_ops;` then `obj.ops->read(...)` — find the struct instance's initialization
- Parameter: pointer passed as argument — **Grep** for callers of `func`, check what they pass
- Global variable: **Grep** for the variable name across the project, check global initializers
- Array of structs: `ops_table[i] = {...}` — check all entries in the initializer

**Stop conditions:**
- Found a concrete function name with an implementation in the project → record as target
- Traced beyond 2 levels of caller indirection → stop and report `confidence: "low"`
- Hit a project boundary (external library, system call) → stop, do not report external functions
- Hit a `dlsym`/`dlsym`-like dynamic resolution → report the symbol name with `confidence: "low"`

### 5. Identify Target Functions
- For each possible value path (if/else branches, switch cases), identify the concrete function name
- Include global struct/array initializers (common for ops tables)
- For dynamic resolution (`dlsym`, `GetProcAddress`), note the symbol name string

### 6. Assess Confidence
- `high`: Single unambiguous assignment traceable within the same file
- `medium`: Multiple targets found, or traced across 1-2 files
- `low`: Complex tracing, runtime-dynamic resolution, or trace exceeded depth limit

### 7. Write Result
Overwrite `.siakam_out/indirect/<uid>.json` with the final result.

## Output Format

```json
{
  "uid": "<uid>",
  "status": "completed",
  "possible_targets": [
    {
      "callee": "<function name>",
      "file": "<relative path>",
      "confidence": "high|medium|low",
      "reasoning": "<brief: assignment source, struct type, or call chain>"
    }
  ]
}
```

If no targets found: `"status": "completed", "possible_targets": []`.
If analysis fails: `"status": "failed", "error": "<description>"`.

## Example

**Input:**
```json
{"uid": "abc123", "func": "register_device", "file": "drivers/core.c", "line": 88, "expression": "drv->probe"}
```

**Trace:**
1. Grep for `struct.*device_driver` → found in `include/driver.h:12`, field `probe` is `int (*probe)(struct device *)`
2. Grep for `drv->probe\s*=` in `drivers/core.c` → line 45: `drv->probe = &platform_probe;`
3. Grep for `platform_probe` definition → `drivers/platform.c:30`: `int platform_probe(struct device *d) { ... }`
4. Single target, same project → confidence: high

**Output:**
```json
{
  "uid": "abc123",
  "status": "completed",
  "possible_targets": [
    {
      "callee": "platform_probe",
      "file": "drivers/platform.c",
      "confidence": "high",
      "reasoning": "direct assignment drv->probe = &platform_probe at drivers/core.c:45"
    }
  ]
}
```

## Rules
1. **Write lock first** — create `<uid>.json` with `status: "in_progress"` before analysis
2. **Write result immediately** — overwrite file as soon as analysis of that uid is complete
3. **Use tools effectively** — Grep for symbols/structs, Read for definitions, Glob for file discovery
4. **Project scope only** — only report callees with implementations found within the project
5. **Be honest** — empty targets rather than guessing; `status: "failed"` rather than fabricating
6. **Trace depth limit** — stop at 2 levels of caller indirection; report `confidence: "low"` if unresolved
