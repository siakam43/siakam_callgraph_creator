# Analyze Indirect Call

You are analyzing indirect call sites (function pointer calls) in a C codebase. Determine the possible target functions (callees) that could be called at each site. Process the given uids one at a time, in sequence.

## Hard Constraint: No Code Generation

**You MUST NOT write, generate, or execute any scripts, programs, or code** to assist with the analysis. This includes but is not limited to Python scripts, shell scripts (beyond single-command grep/find), awk/sed programs, or any automated analysis tooling.

All analysis MUST be performed by you — the LLM — reading source code and reasoning about it directly. The only tools permitted are:
- **Read** — read source files, headers, and existing results
- **Grep** — search for symbols, patterns, definitions (single commands only, no scripts)
- **Glob** — discover files by pattern
- **Write** — write result JSON files (output only)

The reasoning chain is: you read the code with Read/Grep, you understand the C semantics in your own analysis, and you write the result. No intermediate code generation or automation is allowed.

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

First, classify the call expression. Work through each applicable path:

**3a. Expression involves a macro**
- **Grep** for the macro name in headers to find its `#define`
- Expand the macro to see the actual dereference pattern, then apply the matching case below
- Example: `STREAM_READ(x, y)` → after expansion `streamer_hooks.read(x, y)` — treat as struct member access (3b)

**3b. `ptr->member` (single-level struct member access)**
- **Grep** for `struct\s+\w*\s*\{` in headers to find the struct/union definition
- Identify the member's declared type (function pointer or typedef)
- If the member type is a **typedef**: **Grep** for the typedef to find the actual function signature
- If the variable is a **pointer to the struct** (declared `struct foo *ptr`), find what concrete struct instance it points to
- Also check `typedef struct { ... } name_t;` patterns

**3c. `ptr->mid->member` (multi-level struct member access)**
- Resolve recursively: find the type of `ptr`, then the type of its `mid` member, then the `member` function pointer
- **Grep** for each intermediate struct definition in sequence
- Example: `pkey->ameth->pkey_security_bits` — find `pkey`'s struct → find `ameth` member's struct type → find `pkey_security_bits` field in that struct

**3d. `(*ptr)(...)` or direct variable call**
- **Grep** for the variable's declaration in the current function and at file scope
- Distinguish: **function pointer** (`void (*fn)(int)`) vs **pointer-to-function-pointer** (`void (**fn)(int)`)
- If declared with a typedef: find the typedef definition for the actual signature
- If the variable was **loaded from a struct field** (e.g., `block128_f block = ctx->block;` then `(*block)(...)`): the target resolves through the struct field — continue to Step 4m

**3e. Parameter name (function pointer passed as argument)**
- Check the caller function's parameter list to identify the parameter's declared type
- Resolve any typedefs in the parameter declaration
- The target will come from callers — defer to Step 4d

**3f. Global struct pointer dereference**
- If the expression is `global_ptr->member(...)` where `global_ptr` is a global variable:
  - Find the global pointer's declaration and its assigned value (often `&global_struct_instance`)
  - Resolve the concrete struct instance, then apply 3b

### 4. Trace the Assignment

Work through each applicable assignment path. For each path that yields a concrete function name, record it as a candidate target. Continue until all paths are exhausted or a stop condition is met. Check all applicable sub-steps — a single call site may have targets from multiple paths.

**4a. Direct assignment (same function)**
- `ptr = target;` or `ptr = &target;` → record `target`

**4b. Direct assignment with cast**
- `ptr = (cast_type)target;` or `ptr = (cast_type)(void (*)(void))target;`
- **The cast does not hide the target** — strip the cast and record `target`
- Macro-wrapped casts: `CURLX_FUNCTION_CAST(type, func)` → find the `#define`, expand it, identify `func`
- **Grep** for `=\s*\(.*\)\s*\w+\s*;` near the call site to find cast assignments

**4c. Struct field assignment**
- `obj.field = &some_ops;` then later `obj.field->member(...)` — find the struct instance's field initialization
- Check for **designated initializers**: `.field = target` in struct literals and static initializers
- Check for **compound literals**: `fn(&(struct foo){.field = target})`
- If a struct is **passed by value** to the caller, trace back to the original global/static struct instance

**4d. Parameter tracing**
- Function pointer was passed as an argument to the caller
- **Grep** for callers of `func` across the project
- For each call site, identify what expression is passed for this parameter position
- Trace each distinct passed value — it may be a function name, another parameter, or a struct member

**4e. Global variable assignment**
- **Grep** for the global variable name across the project
- Check its **declaration initializer**: `type var = target;` at file scope
- Check all **writes** to it: `var = target;` at file scope or in init functions
- If uninitialized at declaration, find all assignment sites in functions that run before the caller

**4f. Global struct/array initializers**
- **Grep** for the struct variable name or array name
- Check its static initializer — enumerate ALL entries in the initializer list
- For **arrays of structs with fnptr members**: check every entry's designated initializers for the relevant member
- For **sparse arrays**: skip NULL entries (no call is made through them), only record non-NULL targets
- For **large arrays** (>20 entries): systematically enumerate, don't sample — every slot could be a target

**4g. Switch/case or if/else assignment**
- Search within the function (and init functions it calls) for control-flow that assigns different targets to the same fnptr
- Each branch may assign a different function — record ALL of them
- **CPU-architecture cascades**: default C impl → SSE2 → AVX → FMA3 (each overwrites in sequence). Record ALL targets, don't stop at the first

**4h. Setter / registration functions**
- When assignment happens through an API function:
  - `set_field(obj, target);` — e.g., `DSA_meth_set_bn_mod_exp(dsa->meth, BN_mod_exp_mont)`
  - `register_callback(obj, cb);` — e.g., `channel_register_filter(c, sys_tun_infilter)`
- **Grep** for calls to these setter/registration functions across the project
- The function-pointer argument is typically the first or second parameter
- Trace all call sites of the setter to find all registered targets

**4i. Lookup / selector functions**
- When a function returns a struct pointer that determines the fnptr value:
  - `ops = impl_get();` — returns one of several ops struct instances
  - then `ops->member(...)` — which function this calls depends on the return value
- **Read** the selector function to enumerate all possible return values
- For each return value, identify the concrete struct instance and extract its fnptr members
- Example: `fletcher_4_impl_get()` returns `&scalar_ops`, `&superscalar_ops`, or `&superscalar4_ops` — all three must be enumerated

**4j. va_arg extraction from variadic arguments**
- **Grep** for `va_arg` near the call site to find fnptr extraction from `...`
- Trace `va_start` to identify the parameter position, then trace callers for that argument
- Apply 4d (parameter tracing) from the caller that passed the variadic argument

**4k. dlsym / dlopen dynamic resolution**
- Record the symbol name string passed to `dlsym`
- **Grep** the project for a function definition matching the symbol name
- If found in project sources → record as a candidate with `confidence: "low"`
- If a **dual-path** exists (static assignment + dlsym fallback), trace BOTH paths
- Do NOT report external library functions resolved via dlsym

**4l. Decorator / callback chain**
- When the assignment saves an old callback and installs a new one:
  ```c
  old = obj->cb;          // capture old callback
  obj->cb = new_handler;  // install decorator
  // later: old(...)       // delegate to original
  ```
- Trace what the captured field (`obj->cb`) held BEFORE the capture — that is the actual target
- **Grep** for the initial assignment to the captured field (often in an init function)

**4m. Fnptr loaded from struct field**
- When a local fnptr variable was loaded from a struct member (e.g., `fn = obj->member;`):
  trace the struct member's assignment using 4c (struct field assignment)
- Once the concrete struct instance is found, apply 3b/3c to identify the fnptr member's value

### 5. Identify Target Functions

Collect all candidate targets from Step 4. Then apply the following to produce the final list:

**5a. Enumerate all distinct concrete function names**
- For direct assignments and casts (4a, 4b): use the function name after stripping casts
- For struct field assignments (4c): extract from field initializers, designated initializers, and compound literals
- For global struct/array initializers (4f): iterate every array entry; skip NULL entries; **deduplicate** — same function at multiple array indices counts as ONE target
- For switch/if-else assignments (4g): collect targets from ALL branches (don't assume only one branch is reachable)
- For setter functions (4h): enumerate all distinct target functions passed to the setter across all call sites

**5b. Handle multi-struct dispatch**
- When the active fnptr depends on which ops struct is selected (4i):
  - Enumerate each distinct ops struct that the selector can return
  - For each ops struct, extract the relevant function pointer member's value
  - Each (struct, member) combination yields one target

**5c. Handle large dispatch tables**
- For arrays with >10 entries:
  - If the array index comes from a bounded enum or range-checked integer: enumerate all valid indices
  - Check for **sentinel entries** (NULL name or NULL function marking end-of-table) and stop at the sentinel
  - For **strcmp-matched tables**: enumerate all entries in the array, each is a possible target
  - For **loop-driven indexing** with NULL guards: enumerate only non-NULL entries
  - Do NOT sample or pick a representative subset — record every distinct target

**5d. Handle dual parallel arrays**
- When two arrays are conditionally selected (e.g., by an `rtz` flag at the call site):
  - Enumerate targets from BOTH arrays
  - Deduplicate across them (many entries may be identical between the two arrays)

**5e. Resolve dlsym targets**
- **Grep** for the symbol name string in the project — if a function with that name exists in project sources, record it
- If the symbol name matches a known external API, do NOT report it
- If dual-path (static + dlsym), include both the static target and the dlsym-resolved target

### 6. Assess Confidence

- `high`: Assignment(s) are DIRECTLY VISIBLE within the same file — even if multiple targets exist, each target's assignment is unambiguous (static initializers, direct assignments, designated initializers, setter/registration calls, switch cases all in the same file). Per-target confidence, not per-call-site. Also: self-referential calls.
- `medium`: Targets whose assignment was traced across files (interprocedural), or through deeply nested init chains
- `low`: Runtime-dynamic resolution (dlsym/dlopen/GetProcAddress), or trace exceeded depth limit

### 7. Write Result
Overwrite `.siakam_out/indirect/<uid>.json` with the final result.

## Stop Conditions

Apply these throughout Steps 3-5:

1. **Concrete target found** → record and continue searching for other paths (one call site may have multiple targets)
2. **Traced beyond 2 levels of caller indirection** → stop that path, report `confidence: "low"`
3. **Hit a project boundary** (external library, system call) → stop tracing that path. You may still report an external function as a target if its name was identified through a visible assignment in the project (e.g., `ptr = &external_func`), but do not trace into external libraries to discover new targets or speculate about their internals.

   A function is outside the project boundary if its definition or implementation file lies outside `project_dir` — do not search for or read files outside `project_dir` to continue tracing.
4. **Hit dlsym / dlopen / GetProcAddress** → report symbol name with `confidence: "low"`; continue searching for other paths (dual-path may exist)
5. **Function pointer is NULL-guarded** (`if (fn) fn(...)`) → if NULL is the only value on some path, that path yields no target (not an error)
6. **Self-referential** (function calls itself through a fnptr) → record as a target with `confidence: "high"`, note the self-referential pattern in reasoning

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
3. **LLM analysis only, no code generation** — Use ONLY Read, Grep (single commands), Glob, and Write tools. NEVER write or execute scripts, programs, or automated analysis code. All type resolution, assignment tracing, and target identification must be done through your own code reading and reasoning.
4. **Check all applicable paths in Step 4** — a single call site may match multiple sub-steps (4a through 4m). Apply every one that fits, collect all candidate targets.
5. **Be honest** — empty targets rather than guessing; `status: "failed"` rather than fabricating
6. **Trace depth limit** — stop at 2 levels of caller indirection; report `confidence: "low"` if unresolved
7. **Enumerate exhaustively** — for arrays/dispatch tables, check ALL entries; for switch/if-else, check ALL branches. Do not stop at the first match.
