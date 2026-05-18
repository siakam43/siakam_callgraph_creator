---
name: siakam_callgraph_creator
description: Generate call graph for C projects. Analyze function calls including indirect (function pointer) calls using Python tree-sitter parsing and LLM-powered analysis. Outputs callgraph.json, callgraph.dot, indirect_call.json, and entry.json.
triggers:
  - /siakam_callgraph_creator
  - siakam_callgraph_creator
---

# siakam_callgraph_creator

Generate a high-accuracy call graph for C-language projects, including resolution of indirect (function pointer) calls.

## Usage

```
/siakam_callgraph_creator <project_dir>
```

- `project_dir`: Path to the C project to analyze. Defaults to current directory if not specified.
- If `.siakamignore` exists in `project_dir`, files matching its patterns (gitignore syntax) are excluded.

## Environment Setup

Required: Python 3.9+, plus the packages listed in `requirements.txt`:

- tree-sitter >= 0.21.0
- tree-sitter-c >= 0.21.0

Install with:

```bash
pip install -r requirements.txt
```

## Prerequisites

Required permissions: **Bash**, **Read**, **Glob**, **Write**.

## Pipeline

`siakam_start.py` is located in the same directory as this SKILL.md file. Use its absolute path when invoking commands below.

### Phase 1: Module A — Static Analysis (Python)

Run the tree-sitter-based C parser to extract functions, direct calls, and indirect call points:

```bash
python3 siakam_start.py analyze <project_dir>
```

Output: `nodes.json`, `edges.json`, `indirect_points.json`.

### Phase 2: Module B — Indirect Call Resolution (LLM)

Read `module_b/orchestrator.md` and follow its instructions to:
1. Load `indirect_points.json`, check existing results in `.siakam_out/indirect/`
2. Split pending calls into batches (≤5 per batch)
3. Dispatch parallel subagents using `module_b/analyze_indirect.md`
4. Each subagent writes results to `.siakam_out/indirect/<uid>.json`

### Phase 3: Module C — Merge and Output (Python)

```bash
python3 siakam_start.py merge <project_dir>
```

Final outputs: `callgraph.json`, `callgraph.dot`, `indirect_call.json`, `entry.json`.

## Error Recovery

If interrupted, re-run. Module B skips completed uids (checkpoint recovery).
