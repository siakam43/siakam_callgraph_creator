# Module B: Orchestrator Tests

Validates `module_b/orchestrator.md` prompt for correct parallel dispatch and checkpoint recovery.

## Setup

Test data is in `module_b/tests/`:
- `mock_indirect_points.json` — 6 simulated indirect call points
- `pre_existing/uid00001.json` — pre-completed result (should be skipped)
- `pre_existing/uid00003.json` — pre-failed result (should be retried once)

## Procedure

### Step 1: Set up test environment

1. Copy `mock_indirect_points.json` to a test project's `.siakam_out/indirect_points.json`
2. Copy `pre_existing/*.json` to `.siakam_out/indirect/`
3. Create stub C source files for each uid (e.g., `test.c` with simple functions)

### Step 2: Run the orchestrator

Apply the `orchestrator.md` prompt. It should:

1. Read `.siakam_out/indirect_points.json` to get the 6 uids
2. Check each uid against `.siakam_out/indirect/<uid>.json`
3. Identify uid00001 (completed) as skip candidate
4. Identify uid00003 (failed) as retry candidate — delete old file and re-add to pending
5. Add uid00002, uid00004, uid00005, uid00006, and retried uid00003 to pending list

### Step 3: Verify checkpoint recovery

- [ ] uid00001 is **skipped** (already `status: "completed"`)
- [ ] uid00003 is **retried** (old `status: "failed"` file deleted, re-added as pending)
- [ ] uid00002, uid00003, uid00004, uid00005, uid00006 appear in the pending list

### Step 4: Verify batch splitting

Check that the 5 pending uids are split into batches:
- Each batch has ≤ 5 uids
- All 5 uids are assigned to at least one batch
- No uid appears in multiple batches

### Step 5: Verify parallel dispatch

The orchestrator should dispatch subagents in **one message with multiple Agent tool calls** (parallel), not sequentially.

### Step 6: Verify task tracking checklist

The orchestrator should maintain a checklist in the format:
```
[ ] uid00002 — test_func2 @ test.c:20 (ptr->cb2)
[ ] uid00003 — test_func3 @ test.c:30 ((*fp3)())
[ ] uid00004 — test_func4 @ test.c:40 (arr[i]())
[ ] uid00005 — test_func5 @ test.c:50 (ops->run)
[ ] uid00006 — test_func6 @ test.c:60 (dlsym_func)
```

### Step 7: Verify result integrity

After all subagents complete:
- [ ] All 6 uids have result files in `.siakam_out/indirect/`
- [ ] uid00001 retains its original content (not overwritten)
- [ ] uid00003 is **overwritten** by the retry (new result replaces pre-existing `status: "failed"`)
- [ ] uid00002, uid00003, uid00004, uid00005, uid00006 contain valid Module B output format
- [ ] Each result file has a valid `uid`, `status`, and non-null content

### Step 8: Verify aggregation

After completion, the orchestrator should report:
- `total 5 pending → 5 completed, 0 failed, 1 retried`
- No uids remain unprocessed
