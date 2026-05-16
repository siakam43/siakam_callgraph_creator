#!/usr/bin/env python3
"""Generate module A ground truth files for all 104 test_bench fixtures.

For each fixture.c, uses tree-sitter to extract:
- ground_truth_nodes.json: function definitions
- ground_truth_edges.json: direct call edges
- ground_truth_indirect.json: indirect call points with uid

Enhanced: tracks function pointer variable/parameter declarations so calls
through function pointers by name (e.g. `callback(args)`) are correctly
classified as indirect.
"""
import hashlib
import json
import os
import sys

from tree_sitter import Language, Parser
import tree_sitter_c as tsc

TEST_BENCH = "/home/admin/cc/wksp/siakam_security_skills/test_bench"
MODULE_A_FIXTURES = "/home/admin/cc/wksp/siakam_security_skills/siakam_callgraph_creator/module_a/tests/fixtures"

C_LANGUAGE = Language(tsc.language())
PARSER = Parser(C_LANGUAGE)


def compute_uid(file, func, line, expression):
    raw = f"{file}:{func}:{line}:{expression}"
    return hashlib.sha256(raw.encode()).hexdigest()[:8]


def parse_fixture(filepath, filename):
    """Parse a single C fixture, return (functions, edges, indirect_points)."""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        source = f.read()

    source_bytes = source.encode()
    tree = PARSER.parse(source_bytes)
    root = tree.root_node

    functions = []
    edges = []
    indirect_points = []
    fnptr_names = set()  # names known to be function pointers

    # Pass 1: collect function pointer declarations (global + function-local)
    _collect_fnptr_decls(root, source_bytes, fnptr_names)

    # Pass 2: walk functions, collecting nodes, edges, indirects
    _walk(root, source_bytes, filename, functions, edges, indirect_points,
          fnptr_names)

    return functions, edges, indirect_points


def _collect_fnptr_decls(node, source_bytes, fnptr_names):
    """Pre-scan: collect names that are function pointer variables or parameters.

    Detects:
    - void (*ptr)(int) = ...;  (global/local variable)
    - void func(void (*cb)(int));  (parameter declaration)
    - ret_type (*name)(params);  (any function pointer declaration)
    """
    if node.type == "declaration":
        _extract_fnptr_from_declaration(node, source_bytes, fnptr_names)
    elif node.type == "function_definition":
        declarator = node.child_by_field_name("declarator")
        if declarator:
            _extract_fnptr_params(declarator, source_bytes, fnptr_names)

    for child in node.children:
        _collect_fnptr_decls(child, source_bytes, fnptr_names)


def _has_descendant(node, target_type):
    """Check if node has a descendant of target_type."""
    if node.type == target_type:
        return True
    for child in node.children:
        if _has_descendant(child, target_type):
            return True
    return False


def _extract_fnptr_from_declaration(decl_node, source_bytes, fnptr_names):
    """Extract function pointer variable names from a declaration node.

    Pattern: declaration containing init_declarator containing function_declarator.
    The identifier is the function pointer variable name.
    """
    for child in _iter_all(decl_node):
        if child.type == "init_declarator":
            if _has_descendant(child, "function_declarator"):
                # Extract the identifier - it's the variable name
                def _find_first_id(n):
                    if n.type == "identifier":
                        return source_bytes[n.start_byte:n.end_byte].decode()
                    for c in n.children:
                        result = _find_first_id(c)
                        if result:
                            return result
                    return None
                name = _find_first_id(child)
                if name:
                    fnptr_names.add(name)


def _extract_fnptr_params(func_declarator_node, source_bytes, fnptr_names):
    """Extract function pointer parameter names from a function declarator.

    Pattern: parameter_declaration containing function_declarator.
    The identifier inside is the parameter name.
    """
    for child in _iter_all(func_declarator_node):
        if child.type == "parameter_declaration":
            if _has_descendant(child, "function_declarator"):
                def _find_first_id(n):
                    if n.type == "identifier":
                        return source_bytes[n.start_byte:n.end_byte].decode()
                    for c in n.children:
                        result = _find_first_id(c)
                        if result:
                            return result
                    return None
                name = _find_first_id(child)
                if name:
                    fnptr_names.add(name)


def _iter_all(node):
    """Yield all descendant nodes depth-first."""
    yield node
    for child in node.children:
        yield from _iter_all(child)


def _walk(node, source_bytes, filename, functions, edges, indirects,
          fnptr_names, current_func=None):
    if node.type == "function_definition":
        func_name = _get_func_name(node, source_bytes)
        if func_name:
            fn = {
                "name": func_name,
                "file": filename,
                "line_start": node.start_point[0] + 1,
                "has_body": node.child_by_field_name("body") is not None,
                "body_file": filename,
                "body_line_start": node.start_point[0] + 1,
                "body_line_end": node.end_point[0] + 1,
            }
            functions.append(fn)
            for child in node.children:
                _walk(child, source_bytes, filename, functions, edges,
                     indirects, fnptr_names, func_name)
            return

    elif node.type == "call_expression" and current_func:
        callee_node = node.child_by_field_name("function")
        if callee_node:
            expr_text = source_bytes[callee_node.start_byte:callee_node.end_byte].decode()
            is_indirect = _is_indirect(callee_node, expr_text, fnptr_names)
            line = node.start_point[0] + 1

            if is_indirect:
                uid = compute_uid(filename, current_func, line, expr_text)
                indirects.append({
                    "uid": uid,
                    "func": current_func,
                    "file": filename,
                    "line": line,
                    "expression": expr_text,
                })
            else:
                callee_name = _get_callee_name(callee_node, source_bytes)
                if callee_name:
                    edges.append({
                        "caller": current_func,
                        "callee": callee_name,
                        "file": filename,
                        "line": line,
                    })

    for child in node.children:
        _walk(child, source_bytes, filename, functions, edges, indirects,
              fnptr_names, current_func)


INDIRECT_CALLEE_TYPES = {
    "field_expression",       # ops->read or ops.read
    "pointer_expression",     # (*fp)
    "subscript_expression",   # arr[i]
    "call_expression",        # get_handler()(args)
    "parenthesized_expression",  # (fnptr)(args)
    "cast_expression",        # (type)expr(args)
    "conditional_expression", # cond ? a : b
}


def _is_indirect(callee_node, expr_text, fnptr_names):
    """Check if the callee of a call_expression is a function pointer call."""
    # AST structural patterns
    if callee_node.type in INDIRECT_CALLEE_TYPES:
        return True

    # Identifier: check if it's a known function pointer name
    if callee_node.type == "identifier":
        if expr_text in fnptr_names:
            return True

    return False


def _get_callee_name(callee_node, source_bytes):
    if callee_node.type == "identifier":
        return source_bytes[callee_node.start_byte:callee_node.end_byte].decode()
    return None


def _get_func_name(func_def_node, source_bytes):
    declarator = func_def_node.child_by_field_name("declarator")
    if not declarator:
        return None
    return _find_identifier(declarator, source_bytes)


def _find_identifier(node, source_bytes):
    if node.type == "identifier":
        return source_bytes[node.start_byte:node.end_byte].decode()
    if node.type == "function_declarator":
        decl = node.child_by_field_name("declarator")
        if decl:
            return _find_identifier(decl, source_bytes)
    for child in node.children:
        result = _find_identifier(child, source_bytes)
        if result:
            return result
    return None


def main():
    total_functions = 0
    total_edges = 0
    total_indirect = 0

    for category in sorted(os.listdir(TEST_BENCH)):
        cat_path = os.path.join(TEST_BENCH, category)
        if not os.path.isdir(cat_path):
            continue
        for example in sorted(os.listdir(cat_path)):
            example_path = os.path.join(cat_path, example)
            fixture_path = os.path.join(example_path, "fixture.c")
            if not os.path.exists(fixture_path):
                continue

            ma_dir = os.path.join(MODULE_A_FIXTURES, category, example)
            os.makedirs(ma_dir, exist_ok=True)

            functions, edges, indirects = parse_fixture(fixture_path, "fixture.c")

            with open(os.path.join(ma_dir, "ground_truth_nodes.json"), "w") as f:
                json.dump({"functions": functions}, f, indent=2)
            with open(os.path.join(ma_dir, "ground_truth_edges.json"), "w") as f:
                json.dump({"edges": edges}, f, indent=2)
            with open(os.path.join(ma_dir, "ground_truth_indirect.json"), "w") as f:
                json.dump({"indirect_points": indirects}, f, indent=2)

            total_functions += len(functions)
            total_edges += len(edges)
            total_indirect += len(indirects)

    print(f"Generated ground truth for all fixtures:")
    print(f"  Total functions: {total_functions}")
    print(f"  Total direct edges: {total_edges}")
    print(f"  Total indirect points: {total_indirect}")


if __name__ == "__main__":
    main()
