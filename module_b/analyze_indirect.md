# Analyze Indirect Call

You are analyzing a single indirect call site (function pointer call) in a C codebase. Determine the possible target functions (callees) that could be called at this site.

## Input

```json
{
  "uid": "<hash string>",
  "func": "<caller function name>",
  "file": "<relative path to source file>",
  "line": <line number>,
  "expression": "<the function pointer expression, e.g. ops->read>"
}
```

## Analysis Steps

### 1. Locate the Call Site
Read the source file at `file`, navigate to `line`, verify the `expression`.

### 2. Determine the Function Pointer Type
- `ptr->member`: find the struct/union definition, identify the member's type
- `(*ptr)()` or direct variable: find its declaration
- Parameter name: trace back through the caller's parameters

### 3. Trace the Assignment
Within function `func`:
- Direct assignment: `ptr = target;`
- Struct field: `obj.ops = &some_ops;` then `obj.ops->read(...)`
- Parameter: pointer passed as argument; trace back to callers of `func`
- Global variable: check global scope for the initialization

### 4. Identify Target Functions
- For each possible value, identify the concrete function name
- Consider ALL code paths (if/else, switch cases)
- Consider global struct/array initializers
- For dynamic resolution (dlsym), note the symbol name

### 5. Assess Confidence
- `high`: Single unambiguous assignment in same file
- `medium`: Multiple targets, or traced across 1-2 files
- `low`: Complex tracing, runtime-dynamic resolution

## Output

Write to `.siakam_out/indirect/<uid>.json`:

```json
{
  "uid": "<uid>",
  "status": "completed",
  "possible_targets": [
    {
      "callee": "<function name>",
      "file": "<relative path>",
      "confidence": "high|medium|low",
      "reasoning": "<brief explanation>"
    }
  ]
}
```

If no targets found: `"status": "completed", "possible_targets": []`.
If analysis fails: `"status": "failed", "error": "<description>"`.

## Rules
1. **Write immediately** — write `<uid>.json` as soon as analysis is complete
2. **Use tools** — Read/Glob/Grep to explore code
3. **Caller scope** — only report callees with implementations in the project
4. **Be honest** — empty targets rather than guessing
5. **One uid per invocation** — analyze exactly one indirect call point
