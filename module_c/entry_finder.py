"""Find entry functions and generate indirect_call.json summary."""
import json
import os

from module_c.merge import merge_callgraph, write_callgraph

_BASIC_TYPES = frozenset({
    "int", "long", "short", "char", "float", "double",
    "unsigned", "signed", "void", "_Bool", "bool",
    "uint8_t", "uint16_t", "uint32_t", "uint64_t",
    "int8_t", "int16_t", "int32_t", "int64_t",
    "uintmax_t", "intmax_t",
    "size_t", "ssize_t", "ptrdiff_t", "off_t",
    "u8", "u16", "u32", "u64", "s8", "s16", "s32", "s64",
})

_QUALIFIERS = frozenset({"const", "volatile", "restrict"})


def _is_basic_params(params: list[str]) -> bool:
    """Return True if all params are basic scalar types (function excluded)."""
    if not params:
        return True
    if len(params) == 1 and params[0].strip() == "void":
        return True

    for text in params:
        has_marker = '*' in text or '[' in text
        for q in _QUALIFIERS:
            text = text.replace(q, "")
        tokens = text.split()
        if not tokens:
            continue
        tokens = tokens[:-1]
        all_basic = all(t in _BASIC_TYPES for t in tokens)
        if has_marker or not all_basic:
            return False
    return True


def find_entry_functions(callgraph: dict) -> list[dict]:
    nodes = callgraph.get("nodes", [])
    edges = callgraph.get("edges", [])
    callees = {e["callee"] for e in edges}

    entries = []
    for node in nodes:
        if not node.get("has_body"):
            continue
        body_file = node.get("body_file", "")
        if not body_file.lower().endswith(".c"):
            continue
        if node["name"] in callees:
            continue
        if _is_basic_params(node.get("params", [])):
            continue
        entries.append({
            "name": node["name"],
            "file": node.get("file", ""),
            "line_start": node.get("line_start", -1),
        })
    return entries


def build_indirect_summary(indirect_points_path: str,
                           indirect_dir: str) -> dict:
    with open(indirect_points_path) as f:
        ip_data = json.load(f)

    calls = []
    completed = 0
    failed = 0

    for ip in ip_data.get("indirect_points", []):
        uid = ip["uid"]
        result_path = os.path.join(indirect_dir, f"{uid}.json")

        call_info = {
            "uid": uid,
            "caller": ip["func"],
            "expression": ip["expression"],
            "file": ip["file"],
            "line": ip["line"],
            "targets": [],
        }

        if os.path.isfile(result_path):
            with open(result_path) as f:
                result = json.load(f)
            if result.get("status") == "completed":
                completed += 1
                for t in result.get("possible_targets", []):
                    call_info["targets"].append({
                        "callee": t["callee"],
                        "confidence": t["confidence"],
                    })
            elif result.get("status") == "failed":
                failed += 1
                call_info["error"] = result.get("error", "Unknown error")
        else:
            failed += 1
            call_info["error"] = "Analysis not performed"

        calls.append(call_info)

    return {
        "total": len(calls),
        "completed": completed,
        "failed": failed,
        "calls": calls,
    }


def write_indirect_summary(output_dir: str, summary: dict):
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "indirect_call.json")
    with open(path, "w") as f:
        json.dump(summary, f, indent=2)


def write_entry_functions(output_dir: str, entries: list[dict]):
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "entry.json")
    with open(path, "w") as f:
        json.dump({"entry_functions": entries}, f, indent=2)


def run_module_c(project_dir: str, output_dir: str) -> dict:
    nodes_path = os.path.join(output_dir, "nodes.json")
    edges_path = os.path.join(output_dir, "edges.json")
    ip_path = os.path.join(output_dir, "indirect_points.json")
    indirect_dir = os.path.join(output_dir, "indirect")

    callgraph = merge_callgraph(nodes_path, edges_path, ip_path, indirect_dir)
    write_callgraph(output_dir, callgraph)

    entries = find_entry_functions(callgraph)
    write_entry_functions(output_dir, entries)

    summary = build_indirect_summary(ip_path, indirect_dir)
    write_indirect_summary(output_dir, summary)

    print(f"Module C: {len(callgraph['edges'])} total edges, "
          f"{len(entries)} entry functions")

    return {"callgraph": callgraph, "entries": entries, "summary": summary}
