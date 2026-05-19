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

# module_a — whitelist .py files, excludes tests/
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

# module_b — whitelist .md files
MODULE_B_FILES=(
  analyze_indirect.md
  orchestrator.md
)
for f in "${MODULE_B_FILES[@]}"; do
  cp "$SCRIPT_DIR/module_b/$f" "$OUT_DIR/module_b/"
done

# module_c — whitelist .py files, excludes tests/
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
echo ""
echo "Total files: $(find "$OUT_DIR" -type f | wc -l)"
