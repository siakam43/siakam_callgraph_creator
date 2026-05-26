# Module B: Indirect Call Analysis Orchestrator

Coordinate the analysis of ALL indirect call points using parallel subagents.

**Hard Constraint: No code generation.** You MUST NOT write scripts, programs, or automated analysis code. All orchestration (checkpoint checking, batch splitting, result verification) must be done through your own reasoning and direct tool use (Read, Write, Bash for single commands). Subagents follow the same constraint per `analyze_indirect.md`.

## Input
- `.siakam_out/indirect_points.json` — indirect call points (Module A output)
- `.siakam_out/indirect/` — directory for per-uid analysis results

## Configuration

- `max_concurrency: 2` — maximum number of subagents to run simultaneously

## Process

### Step 1: Load Task List
Read `indirect_points.json` to get the full list.

### Step 2: Checkpoint Recovery
For each uid:
- `indirect/<uid>.json` exists with `status: "completed"` → **SKIP**
- `indirect/<uid>.json` exists with `status: "in_progress"` → **DELETE and ADD to pending** (interrupted mid-analysis, stale write-lock)
- `indirect/<uid>.json` exists with `status: "failed"` → **RETRY ONCE** (delete old file, re-analyze)
- `indirect/<uid>.json` does NOT exist → **ADD to pending**

If a uid failed twice (the retry also produced `status: "failed"`), leave it and report in summary.

### Step 3: Create Tracking Checklist
Use a concrete format listing every pending uid:

```
[ ] a1b2c3d4 — init_driver @ drivers/core.c:42 (ops->probe)
[ ] e5f6g7h8 — handle_irq @ irq/chip.c:108 (handler)
[ ] i9j0k1l2 — send_packet @ net/tx.c:215 (tx_ops->send)
```

### Step 4: Split into Batches
Group pending uids into batches of **≤ 5 per batch**.

### Step 5: Dispatch Subagents in Waves

Send batches in waves of `max_concurrency` at a time.

1. Divide the pending batch list into waves: each wave contains at most `max_concurrency` batches
2. For each wave, launch all its batches in parallel (Agent tool with parallel tool calls)
3. **Wait for ALL subagents in the current wave to complete** before launching the next wave
4. Continue until all waves are processed

Each subagent receives the following prompt:

```
Read module_b/analyze_indirect.md and follow it.

ANALYZE these indirect call points (in sequence, one at a time):
- uid: <uid1>, func: <func1>, file: <file1>, line: <line1>, expression: <expr1>
- uid: <uid2>, func: <func2>, file: <file2>, line: <line2>, expression: <expr2>
...
```

### Step 6: Aggregate Results
After all subagents complete:
1. Verify every pending uid has a result file
2. For any missing uids, re-dispatch (one retry only)
3. If a subagent itself failed (no output at all), re-dispatch its batch once with a fresh agent
4. Report summary: `total N pending → M completed, F failed, R retried`

## Rules
1. **Checkpoint first** — always check existing results before dispatching
2. **Retry once** — failed uids get exactly one retry, no more
3. **Wave dispatch** — launch batches in waves of `max_concurrency`, wait for each wave to complete before the next
4. **Checklist discipline** — track every uid explicitly, update checklist as results arrive
5. **Write-lock** — subagents create `<uid>.json` with `status: "in_progress"` before analysis
