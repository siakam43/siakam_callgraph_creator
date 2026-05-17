"""Module A orchestrator: two-phase pipeline for cross-file call graph analysis."""
import json
import logging
import os

from module_a.ignore_parser import parse_siakamignore, should_exclude
from module_a.models import ProjectSymbols
from module_a._parser import _FileParser
from module_a._project_scanner import (
    scan_typedefs, scan_macros, scan_global_fnptrs,
)
from module_a._call_analyzer import CallAnalyzer

logger = logging.getLogger(__name__)

C_EXTENSIONS = {".c", ".h"}


def run_analysis(project_dir: str, output_dir: str) -> dict:
    os.makedirs(output_dir, exist_ok=True)

    patterns = parse_siakamignore(project_dir)
    files = _discover_files(project_dir, patterns)

    file_parser = _FileParser()

    # Phase 0: project-wide symbol collection
    project_symbols = _run_phase0(files, file_parser)

    # Phase 1+2: per-file call analysis
    all_functions, all_edges, all_indirect_points = _run_phase12(
        files, project_symbols, project_dir, file_parser)

    file_parser.clear()

    # Deduplicate before serialization (operates on typed objects)
    deduped_functions = _deduplicate_functions(all_functions)

    # Single serialization boundary: model objects → JSON-serializable dicts
    func_dicts, edge_dicts, ip_dicts = _serialize_results(
        deduped_functions, all_edges, all_indirect_points)

    _write_output(output_dir, project_dir, func_dicts, edge_dicts, ip_dicts)

    logger.info("Module A: %d functions, %d direct edges, %d indirect points",
                len(func_dicts), len(edge_dicts), len(ip_dicts))

    return {
        "functions": func_dicts,
        "edges": edge_dicts,
        "indirect_points": ip_dicts,
    }


# ---- file discovery ----

def _discover_files(project_dir, patterns):
    files = []
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
            files.append(filepath)
    return files


# ---- Phase 0 ----

def _run_phase0(files, file_parser):
    # Pass 0a: typedefs + macros (no cross-file dependency)
    all_typedefs = set()
    all_macros = {}
    for fp in files:
        root, src = file_parser.parse(fp)
        all_typedefs |= scan_typedefs(root, src)
        for k, v in scan_macros(root, src).items():
            if k not in all_macros:
                all_macros[k] = v

    # Pass 0b: global fnptr names (needs full typedef set, ASTs cached from 0a)
    all_fnptrs = set()
    for fp in files:
        root, src = file_parser.parse(fp)
        all_fnptrs |= scan_global_fnptrs(root, src, all_typedefs)

    return ProjectSymbols(
        typedef_fnptr_names=all_typedefs,
        global_fnptr_names=all_fnptrs,
        macro_call_map=all_macros,
    )


# ---- Phase 1+2 ----

def _run_phase12(files, symbols, project_dir, file_parser):
    functions, edges, ips = [], [], []
    for fp in files:
        root, src = file_parser.parse(fp)
        a = CallAnalyzer(symbols, fp, src)
        funcs, edgs, inds = a.analyze(root)
        _relativize_paths(funcs, edgs, inds, fp, project_dir)
        functions.extend(funcs)
        edges.extend(edgs)
        ips.extend(inds)
    return functions, edges, ips


# ---- path relativization ----

def _relativize_paths(funcs, edgs, ips, filepath, project_dir):
    """Convert full paths to project_dir-relative paths (mutates objects in place)."""
    for fn in funcs:
        fn.file = os.path.relpath(fn.file, project_dir)
        if fn.body_file:
            fn.body_file = os.path.relpath(fn.body_file, project_dir)
    for e in edgs:
        e.file = os.path.relpath(e.file, project_dir)
    for ip in ips:
        ip.file = os.path.relpath(ip.file, project_dir)


# ---- deduplication ----

def _deduplicate_functions(functions):
    """Deduplicate functions: per name, keep the one with has_body=True if available."""
    by_name = {}
    for fn in functions:
        if fn.name not in by_name:
            by_name[fn.name] = fn
        elif fn.has_body and not by_name[fn.name].has_body:
            by_name[fn.name] = fn
    return list(by_name.values())


# ---- serialization ----

def _serialize_results(functions, edges, indirect_points):
    """Convert model objects to JSON-serializable dicts.

    This is the single serialization boundary for the Module A pipeline.
    All pipeline internals operate on typed objects (FunctionNode, DirectEdge,
    IndirectPoint); dict conversion happens here, just before I/O.
    """
    return (
        [f.to_dict() for f in functions],
        [e.to_dict() for e in edges],
        [ip.to_dict() for ip in indirect_points],
    )


# ---- output ----

def _write_output(output_dir, project_dir, functions, edges, indirect_points):
    """Write nodes.json, edges.json, indirect_points.json."""
    nodes_path = os.path.join(output_dir, "nodes.json")
    with open(nodes_path, "w") as f:
        json.dump({"project_dir": project_dir, "functions": functions}, f, indent=2)

    edges_path = os.path.join(output_dir, "edges.json")
    with open(edges_path, "w") as f:
        json.dump({"edges": edges}, f, indent=2)

    indirect_path = os.path.join(output_dir, "indirect_points.json")
    with open(indirect_path, "w") as f:
        json.dump({"indirect_points": indirect_points}, f, indent=2)


# ---- single-file convenience ----

def analyze_single_file(filepath: str) -> dict:
    """Run the full Module A pipeline on a single C file.

    Self-populates project symbols from the file itself (typedefs, macros,
    global fnptrs) so file-local macro expansion and fnptr detection work
    correctly. Returns dicts with keys "functions", "edges", "indirect_points".
    """
    from module_a._project_scanner import (
        scan_typedefs, scan_macros, scan_global_fnptrs,
    )

    file_parser = _FileParser()
    root, src = file_parser.parse(filepath)
    file_parser.clear()

    typedefs = scan_typedefs(root, src)
    macros = scan_macros(root, src)
    fnptrs = scan_global_fnptrs(root, src, typedefs)

    symbols = ProjectSymbols(typedefs, fnptrs, macros)
    a = CallAnalyzer(symbols, filepath, src)
    funcs, edges, ips = a.analyze(root)
    _relativize_paths(funcs, edges, ips, filepath, os.path.dirname(filepath))
    return {
        "functions": [f.to_dict() for f in funcs],
        "edges": [e.to_dict() for e in edges],
        "indirect_points": [ip.to_dict() for ip in ips],
    }
