"""Merge module A and module B results into callgraph.json and callgraph.dot."""
import json
import os


def merge_callgraph(nodes_path: str, edges_path: str,
                    indirect_points_path: str, indirect_dir: str) -> dict:
    with open(nodes_path) as f:
        nodes_data = json.load(f)
    with open(edges_path) as f:
        edges_data = json.load(f)
    with open(indirect_points_path) as f:
        ip_data = json.load(f)

    all_edges = []

    for e in edges_data.get("edges", []):
        all_edges.append({
            "caller": e["caller"],
            "callee": e["callee"],
            "type": "direct",
            "file": e["file"],
            "line": e["line"],
        })

    points_by_uid = {ip["uid"]: ip for ip in ip_data.get("indirect_points", [])}

    if os.path.isdir(indirect_dir):
        for uid, ip in points_by_uid.items():
            result_path = os.path.join(indirect_dir, f"{uid}.json")
            if not os.path.isfile(result_path):
                continue
            with open(result_path) as f:
                result = json.load(f)
            if result.get("status") != "completed":
                continue
            for target in result.get("possible_targets", []):
                all_edges.append({
                    "caller": ip["func"],
                    "callee": target["callee"],
                    "type": "indirect",
                    "uid": uid,
                    "confidence": target["confidence"],
                })

    return {
        "nodes": nodes_data.get("functions", []),
        "edges": all_edges,
    }


def generate_dot(callgraph: dict) -> str:
    lines = ["digraph callgraph {"]
    for edge in callgraph.get("edges", []):
        caller = edge["caller"]
        callee = edge["callee"]
        if edge["type"] == "direct":
            label = "direct"
        else:
            label = f"indirect\\nconf:{edge.get('confidence', 'unknown')}"
        lines.append(f'  "{caller}" -> "{callee}" [label="{label}"];')
    lines.append("}")
    return "\n".join(lines) + "\n"


def write_callgraph(output_dir: str, callgraph: dict):
    os.makedirs(output_dir, exist_ok=True)
    cg_path = os.path.join(output_dir, "callgraph.json")
    with open(cg_path, "w") as f:
        json.dump(callgraph, f, indent=2)
    dot_path = os.path.join(output_dir, "callgraph.dot")
    with open(dot_path, "w") as f:
        f.write(generate_dot(callgraph))
