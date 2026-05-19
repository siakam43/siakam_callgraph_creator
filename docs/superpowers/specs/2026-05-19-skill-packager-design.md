# Skill Packager Script Design

## Overview

A shell script that assembles the `siakam-callgraph-creator` skill into a standalone distributable folder by whitelist-copying source files and excluding tests/docs/artifacts.

## Script

`package_skill.sh` in project root. Run: `./package_skill.sh`

## Output

`./siakam-callgraph-creator/` with the following structure:

```
siakam-callgraph-creator/
├── SKILL.md              # skill entry point
├── siakam_start.py       # CLI entry script
├── requirements.txt      # Python dependencies
├── module_a/             # static analysis (all .py, no tests/)
│   ├── __init__.py
│   ├── models.py
│   ├── analyzer.py
│   ├── uid_generator.py
│   ├── ignore_parser.py
│   ├── _parser.py
│   ├── _project_scanner.py
│   ├── _ast_helpers.py
│   └── _call_analyzer.py
├── module_b/             # LLM prompts
│   ├── analyze_indirect.md
│   └── orchestrator.md
└── module_c/             # merge/output (all .py, no tests/)
    ├── __init__.py
    ├── entry_finder.py
    └── merge.py
```

## Implementation

- **Whitelist approach**: each file and directory is explicitly listed; nothing is copied by wildcard
- **Removable old output** before copying to ensure clean state
- **Excluded**: `tests/`, `__pycache__/`, `*.pyc`, `docs/`, `.omc/`, `.git/`, `.venv/`, `.pytest_cache/`, `original_requirements.md`, `.gitignore`, `*.ipynb`, any `.json` config files
- **Relative paths only**: all paths relative to script's own directory (project root). No hardcoded absolute paths. Use `SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"` to locate source files

## Acceptance Criteria

- Script runs without errors
- Output folder contains exactly the files listed above (no tests, no docs, no artifacts)
- `find siakam-callgraph-creator -type f` count matches expected
