"""Module A orchestrator: coordinates .siakamignore parsing and C file analysis
to produce nodes.json, edges.json, and indirect_points.json."""
import json
import os
import sys

from module_a.ignore_parser import parse_siakamignore, should_exclude
from module_a.c_parser import parse_file

C_EXTENSIONS = {".c", ".h"}


def run_analysis(project_dir: str, output_dir: str) -> dict:
    os.makedirs(output_dir, exist_ok=True)

    patterns = parse_siakamignore(project_dir)

    files_to_analyze = []
    for root, dirs, filenames in os.walk(project_dir):
        if ".siakam_out" in dirs:
            dirs.remove(".siakam_out")
        rel_root = os.path.relpath(root, project_dir)
        if rel_root == ".":
            rel_root = ""

        dirs_to_remove = []
        for d in dirs:
            rel_dir = os.path.join(rel_root, d) if rel_root else d
            if should_exclude(patterns, rel_dir + "/"):
                dirs_to_remove.append(d)
        for d in dirs_to_remove:
            dirs.remove(d)

        for filename in sorted(filenames):
            ext = os.path.splitext(filename)[1].lower()
            if ext not in C_EXTENSIONS:
                continue
            filepath = os.path.join(root, filename)
            rel_path = os.path.relpath(filepath, project_dir)
            if should_exclude(patterns, rel_path):
                continue
            files_to_analyze.append(filepath)

    all_functions = []
    all_edges = []
    all_indirect_points = []

    for filepath in files_to_analyze:
        rel_path = os.path.relpath(filepath, project_dir)
        result = parse_file(filepath)

        for fn in result["functions"]:
            fn["file"] = os.path.relpath(fn["file"], project_dir)
            if fn.get("body_file"):
                fn["body_file"] = os.path.relpath(fn["body_file"], project_dir)

        for e in result["edges"]:
            e["file"] = os.path.relpath(e["file"], project_dir)

        for ip in result["indirect_points"]:
            ip["file"] = os.path.relpath(ip["file"], project_dir)

        all_functions.extend(result["functions"])
        all_edges.extend(result["edges"])
        all_indirect_points.extend(result["indirect_points"])

    deduped_functions = _deduplicate_functions(all_functions)

    nodes_path = os.path.join(output_dir, "nodes.json")
    with open(nodes_path, "w") as f:
        json.dump({"project_dir": project_dir, "functions": deduped_functions},
                  f, indent=2)

    edges_path = os.path.join(output_dir, "edges.json")
    with open(edges_path, "w") as f:
        json.dump({"edges": all_edges}, f, indent=2)

    indirect_path = os.path.join(output_dir, "indirect_points.json")
    with open(indirect_path, "w") as f:
        json.dump({"indirect_points": all_indirect_points}, f, indent=2)

    print(f"Module A: {len(deduped_functions)} functions, "
          f"{len(all_edges)} direct edges, "
          f"{len(all_indirect_points)} indirect points")

    return {
        "functions": deduped_functions,
        "edges": all_edges,
        "indirect_points": all_indirect_points,
    }


def _deduplicate_functions(functions: list[dict]) -> list[dict]:
    by_name = {}
    for fn in functions:
        name = fn["name"]
        if name not in by_name:
            by_name[name] = fn
        elif fn.get("has_body") and not by_name[name].get("has_body"):
            by_name[name] = fn
    return list(by_name.values())
