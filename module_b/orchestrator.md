# Module B: Indirect Call Analysis Orchestrator

Coordinate the analysis of ALL indirect call points using parallel subagents.

## Input
- `.siakam_out/indirect_points.json` — indirect call points (Module A output)
- `.siakam_out/indirect/` — directory for per-uid analysis results

## Process

### Step 1: Load Task List
Read `indirect_points.json` to get the full list.

### Step 2: Checkpoint Recovery
For each uid:
- `indirect/<uid>.json` exists with `status: "completed"` → **SKIP**
- `indirect/<uid>.json` exists with `status: "failed"` → **SKIP** (do not retry)
- `indirect/<uid>.json` does NOT exist → **ADD to pending**

### Step 3: Create Tracking Checklist
```
[ ] <uid1> — <func> @ <file>:<line> (<expression>)
[ ] <uid2> — <func> @ <file>:<line> (<expression>)
...
```

### Step 4: Split into Batches
Group pending uids into batches of **≤ 5 per batch**.

### Step 5: Dispatch Parallel Subagents
For each batch, launch a subagent (use Agent tool with parallel tool calls):

```
Read module_b/analyze_indirect.md and follow it.

BATCH to analyze:
- uid: <uid1>, func: <func1>, file: <file1>, line: <line1>, expression: <expr1>
- uid: <uid2>, func: <func2>, file: <file2>, line: <line2>, expression: <expr2>
...

FOR EACH:
1. Read the source file and locate the call site
2. Determine function pointer type
3. Trace assignment to find target functions
4. Write result to .siakam_out/indirect/<uid>.json IMMEDIATELY

IMPORTANT:
- Write each result immediately (do not batch writes)
- Before analyzing, create <uid>.json with status: "in_progress"
- Use Read/Glob/Grep to explore code
- Only report targets with implementations within the project
```

### Step 6: Aggregate
After all subagents complete:
1. Verify every pending uid has a result file
2. Re-run batches where uids are missing
3. Report summary: total pending, completed, failed

## Rules
1. **Checkpoint first** — always check existing results before dispatching
2. **No duplicate work** — never re-analyze completed uids
3. **Parallel dispatch** — launch all batches simultaneously
4. **Checklist discipline** — track every uid explicitly
5. **Write-lock** — create file with `status: "in_progress"` before analysis
