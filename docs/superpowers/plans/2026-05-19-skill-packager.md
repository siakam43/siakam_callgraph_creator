# Skill Packager Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `package_skill.sh` that assembles a distributable `siakam-callgraph-creator/` folder via whitelist copying.

**Architecture:** Single shell script in project root. Uses `SCRIPT_DIR` for all path resolution (no absolute paths). Whitelist-copies each source file explicitly. Removes stale output before creating fresh.

**Tech Stack:** bash, cp, rm, mkdir

---

### Task 1: Write package_skill.sh

**Files:**
- Create: `package_skill.sh`

- [ ] **Step 1: Write the script**

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="$SCRIPT_DIR/siakam-callgraph-creator"

# Clean
rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR/module_a" "$OUT_DIR/module_b" "$OUT_DIR/module_c"

# Root files
cp "$SCRIPT_DIR/SKILL.md"         "$OUT_DIR/"
cp "$SCRIPT_DIR/siakam_start.py"  "$OUT_DIR/"
cp "$SCRIPT_DIR/requirements.txt" "$OUT_DIR/"

# module_a (whitelist .py files, no tests/)
MODULE_A_FILES=(
  __init__.py
  models.py
  analyzer.py
  uid_generator.py
  ignore_parser.py
  _parser.py
  _project_scanner.py
  _ast_helpers.py
  _call_analyzer.py
)
for f in "${MODULE_A_FILES[@]}"; do
  cp "$SCRIPT_DIR/module_a/$f" "$OUT_DIR/module_a/"
done

# module_b (whitelist .md files)
MODULE_B_FILES=(
  analyze_indirect.md
  orchestrator.md
)
for f in "${MODULE_B_FILES[@]}"; do
  cp "$SCRIPT_DIR/module_b/$f" "$OUT_DIR/module_b/"
done

# module_c (whitelist .py files, no tests/)
MODULE_C_FILES=(
  __init__.py
  entry_finder.py
  merge.py
)
for f in "${MODULE_C_FILES[@]}"; do
  cp "$SCRIPT_DIR/module_c/$f" "$OUT_DIR/module_c/"
done

echo "Packaged: $OUT_DIR"
find "$OUT_DIR" -type f | sort
echo "Total files: $(find "$OUT_DIR" -type f | wc -l)"
```

- [ ] **Step 2: Make executable and run**

```bash
chmod +x package_skill.sh && ./package_skill.sh
```

- [ ] **Step 3: Verify output contents**

```bash
# Check expected count: SKILL.md + siakam_start.py + requirements.txt + 9 module_a + 2 module_b + 3 module_c = 17 files
find siakam-callgraph-creator -type f | wc -l
# Should output: 17

# Verify no tests leaked
find siakam-callgraph-creator -path '*/test*' -o -path '*/tests/*' | wc -l
# Should output: 0

# Verify no __pycache__ leaked
find siakam-callgraph-creator -name '__pycache__' | wc -l
# Should output: 0
```

- [ ] **Step 4: Commit**

```bash
git add package_skill.sh
git commit -m "feat: add package_skill.sh for skill distribution assembly"
```
