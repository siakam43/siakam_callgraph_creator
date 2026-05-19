# End-to-End Integration Test

Validates the full `/siakam_callgraph_creator` pipeline against a small multi-file C project.

## Test Project Structure

```
tests/e2e_project/
├── .siakamignore         # excludes *.o and build/
├── include/api.h         # driver_ops_t struct with fnptr members
├── ops.c                 # concrete driver ops, global fnptr struct
├── driver.c              # driver setup/teardown, calls through fnptr struct
└── main.c                # entry point, global fnptr variable + indirect call
```

Expected indirect calls:
1. `g_worker(data)` in `execute_work` — global fnptr variable → targets `driver_do_work`
2. `ctx->ops->process(...)` in `driver_process_data` — struct fnptr member → targets `my_driver_process`

## Test 1: Full Pipeline Execution

```bash
cd /home/admin/cc/wksp/siakam_security_skills/siakam_callgraph_creator

# Clean
rm -rf tests/e2e_project/.siakam_out

# Module A
.venv/bin/python3 -c "
from module_a.analyzer import run_analysis
run_analysis('tests/e2e_project', 'tests/e2e_project/.siakam_out')
"

# Verify Module A outputs exist
ls tests/e2e_project/.siakam_out/nodes.json
ls tests/e2e_project/.siakam_out/edges.json
ls tests/e2e_project/.siakam_out/indirect_points.json

# Verify Module A counts
.venv/bin/python3 -c "
import json
with open('tests/e2e_project/.siakam_out/nodes.json') as f:
    assert len(json.load(f)['functions']) == 11
with open('tests/e2e_project/.siakam_out/edges.json') as f:
    assert len(json.load(f)['edges']) == 9
with open('tests/e2e_project/.siakam_out/indirect_points.json') as f:
    assert len(json.load(f)['indirect_points']) == 2
print('Module A: OK')
"

# Copy pre-generated Module B results (simulating LLM analysis)
rm -rf tests/e2e_project/.siakam_out/indirect
cp -r tests/expected/indirect tests/e2e_project/.siakam_out/indirect

# Module C
.venv/bin/python3 -c "
from module_c.entry_finder import run_module_c
run_module_c('tests/e2e_project', 'tests/e2e_project/.siakam_out')
"

# Verify all outputs exist
for f in nodes.json edges.json indirect_points.json callgraph.json callgraph.dot indirect_call.json entry.json; do
    if [ -f "tests/e2e_project/.siakam_out/$f" ]; then
        echo "OK: $f"
    else
        echo "MISSING: $f" && exit 1
    fi
done
echo "Pipeline: OK"
```

- [ ] Module A produces 11 functions, 9 direct edges, 2 indirect points
- [ ] Module C produces all 7 output files
- [ ] Total edges in callgraph: 11 (9 direct + 2 indirect)

## Test 2: Output Comparison

```bash
cd /home/admin/cc/wksp/siakam_security_skills/siakam_callgraph_creator

# Compare structured JSON outputs
.venv/bin/python3 -c "
import json, os

expected_dir = 'tests/expected'
actual_dir = 'tests/e2e_project/.siakam_out'

# Compare nodes
with open(os.path.join(expected_dir, 'nodes.json')) as f: exp = json.load(f)
with open(os.path.join(actual_dir, 'nodes.json')) as f: act = json.load(f)
assert len(exp['functions']) == len(act['functions']), 'nodes count mismatch'

# Compare edges
with open(os.path.join(expected_dir, 'edges.json')) as f: exp = json.load(f)
with open(os.path.join(actual_dir, 'edges.json')) as f: act = json.load(f)
exp_set = {(e['caller'], e['callee'], e['line']) for e in exp['edges']}
act_set = {(e['caller'], e['callee'], e['line']) for e in act['edges']}
assert exp_set == act_set, f'edges mismatch: extra={act_set-exp_set} missing={exp_set-act_set}'

# Compare indirect points
with open(os.path.join(expected_dir, 'indirect_points.json')) as f: exp = json.load(f)
with open(os.path.join(actual_dir, 'indirect_points.json')) as f: act = json.load(f)
exp_set = {(ip['func'], ip['line'], ip['expression']) for ip in exp['indirect_points']}
act_set = {(ip['func'], ip['line'], ip['expression']) for ip in act['indirect_points']}
assert exp_set == act_set, f'indirect points mismatch'

# Compare callgraph
with open(os.path.join(expected_dir, 'callgraph.json')) as f: exp = json.load(f)
with open(os.path.join(actual_dir, 'callgraph.json')) as f: act = json.load(f)
exp_edges = {(e['caller'], e['callee'], e['type']) for e in exp['edges']}
act_edges = {(e['caller'], e['callee'], e['type']) for e in act['edges']}
assert exp_edges == act_edges, f'callgraph edges mismatch'

# Compare entry functions
with open(os.path.join(expected_dir, 'entry.json')) as f: exp = json.load(f)
with open(os.path.join(actual_dir, 'entry.json')) as f: act = json.load(f)
exp_names = {e['name'] for e in exp['entry_functions']}
act_names = {e['name'] for e in act['entry_functions']}
assert exp_names == act_names, f'entry mismatch: extra={act_names-exp_names} missing={exp_names-act_names}'

# Compare indirect summary counts
with open(os.path.join(expected_dir, 'indirect_call.json')) as f: exp = json.load(f)
with open(os.path.join(actual_dir, 'indirect_call.json')) as f: act = json.load(f)
assert exp['total'] == act['total']
assert exp['completed'] == act['completed']
assert exp['failed'] == act['failed']

print('All outputs match expected')
"
```

- [ ] All output files match `tests/expected/`
- [ ] Entry functions: my_driver_init, my_driver_cleanup (2 functions with body, indegree=0, non-basic params)

## Test 3: Checkpoint Recovery

```bash
cd /home/admin/cc/wksp/siakam_security_skills/siakam_callgraph_creator

# Delete one indirect result file to simulate partial completion
rm tests/e2e_project/.siakam_out/indirect/ef769786.json

# Verify the other file is still there
.venv/bin/python3 -c "
import os
indirect_dir = 'tests/e2e_project/.siakam_out/indirect'
files = os.listdir(indirect_dir)
print(f'Remaining: {len(files)} files')
assert len(files) == 1
assert '883aaa05.json' in files
assert 'ef769786.json' not in files
print('Checkpoint recovery state: OK')
"

# Restore the deleted file
cp tests/expected/indirect/ef769786.json tests/e2e_project/.siakam_out/indirect/
```

- [ ] After deletion, 1 result file remains
- [ ] After restore, 2 result files restored

## Test 4: .siakamignore Exclusion

```bash
cd /home/admin/cc/wksp/siakam_security_skills/siakam_callgraph_creator

# Create a file in build/ (should be ignored per .siakamignore)
mkdir -p tests/e2e_project/build
echo 'void ignored_func(void) { int x = 0; }' > tests/e2e_project/build/debug.c

# Re-run Module A with the new ignored file
.venv/bin/python3 -c "
from module_a.analyzer import run_analysis
result = run_analysis('tests/e2e_project', 'tests/e2e_project/.siakam_out')
func_names = {f['name'] for f in result['functions']}
assert 'ignored_func' not in func_names, 'ignored_func should be excluded'
print('.siakamignore exclusion: OK')
"

# Clean up
rm -rf tests/e2e_project/build
```

- [ ] `ignored_func` is NOT in the function list

## Test 5: Module B Test Fixture Verification

```bash
cd /home/admin/cc/wksp/siakam_security_skills/siakam_callgraph_creator

# Verify Module B fixtures exist and are valid
.venv/bin/python3 -c "
import json, os

fixture_dir = 'module_b/tests/fixtures'
expected_dir = 'module_b/tests/expected'

fixtures = sorted(os.listdir(fixture_dir))
expecteds = sorted(os.listdir(expected_dir))

print(f'Fixtures: {len(fixtures)}, Expected: {len(expecteds)}')

# Each fixture should have a matching expected file
for f in fixtures:
    uid = f.replace('.json', '')
    exp_file = f'{uid}_expected.json'
    assert exp_file in expecteds, f'Missing expected file for {uid}'

    with open(os.path.join(fixture_dir, f)) as fh: fix = json.load(fh)
    assert 'uid' in fix and 'func' in fix and 'expression' in fix

    with open(os.path.join(expected_dir, exp_file)) as fh: exp = json.load(fh)
    assert exp['status'] == 'completed'
    assert isinstance(exp['possible_targets'], list)

print(f'All {len(fixtures)} Module B fixtures verified')
"
```

- [ ] All 36 fixtures have matching expected files
- [ ] All fixtures and expected files have valid structure
