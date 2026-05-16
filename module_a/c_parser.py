"""Parse C source files using tree-sitter to extract functions, direct calls,
and indirect call points."""
import sys
from tree_sitter import Language, Parser
import tree_sitter_c as tsc

from module_a.models import FunctionNode, DirectEdge, IndirectPoint
from module_a.uid_generator import compute_uid
from module_a.indirect_detector import is_indirect_call, extract_callee_name

C_LANGUAGE = Language(tsc.language())
PARSER = Parser(C_LANGUAGE)


def parse_file(filepath: str) -> dict:
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        source = f.read()

    source_bytes = source.encode()
    tree = PARSER.parse(source_bytes)
    root = tree.root_node

    if root.has_error:
        _report_errors(root, source, filepath)

    fnptr_names = set()
    fnptr_typedefs = set()
    _collect_fnptr_decls(root, source_bytes, fnptr_names, fnptr_typedefs)

    functions = []
    edges = []
    indirect_points = []

    _walk_ast(root, source_bytes, filepath, functions, edges, indirect_points,
              fnptr_names)

    return {
        "functions": [fn.to_dict() if isinstance(fn, FunctionNode) else fn
                      for fn in functions],
        "edges": [e.to_dict() if isinstance(e, DirectEdge) else e
                  for e in edges],
        "indirect_points": [ip.to_dict() if isinstance(ip, IndirectPoint) else ip
                            for ip in indirect_points],
    }


def _report_errors(root, source, filepath):
    for node in _iter_nodes(root):
        if node.type == "ERROR":
            line = node.start_point[0] + 1
            print(f"WARNING: {filepath}:{line}: syntax error, "
                  f"skipping affected code", file=sys.stderr)


def _iter_nodes(node):
    yield node
    for child in node.children:
        yield from _iter_nodes(child)


# ---- Function pointer declaration collection ----

def _collect_fnptr_decls(node, source_bytes, fnptr_names,
                          fnptr_typedefs=None):
    if fnptr_typedefs is None:
        fnptr_typedefs = set()
    if node.type == "declaration":
        _extract_fnptr_from_declaration(node, source_bytes, fnptr_names,
                                         fnptr_typedefs)
    elif node.type == "function_definition":
        declarator = node.child_by_field_name("declarator")
        if declarator:
            _extract_fnptr_params(declarator, source_bytes, fnptr_names,
                                  fnptr_typedefs)
    elif node.type == "type_definition":
        _extract_typedef_fnptr(node, source_bytes, fnptr_typedefs)
    for child in node.children:
        _collect_fnptr_decls(child, source_bytes, fnptr_names, fnptr_typedefs)


def _has_descendant(node, target_type):
    if node.type == target_type:
        return True
    for child in node.children:
        if _has_descendant(child, target_type):
            return True
    return False


def _extract_fnptr_from_declaration(decl_node, source_bytes, fnptr_names,
                                     fnptr_typedefs):
    for child in _iter_all(decl_node):
        if child.type == "init_declarator":
            if _has_descendant(child, "function_declarator"):
                name = _find_first_id(child, source_bytes)
                if name:
                    fnptr_names.add(name)
                    return
            # Check if the type is a known fnptr typedef
            type_name = _get_type_name(decl_node, source_bytes)
            if type_name and type_name in fnptr_typedefs:
                name = _find_first_id(child, source_bytes)
                if name:
                    fnptr_names.add(name)


def _extract_fnptr_params(func_declarator_node, source_bytes, fnptr_names,
                           fnptr_typedefs=None):
    if fnptr_typedefs is None:
        fnptr_typedefs = set()
    for child in _iter_all(func_declarator_node):
        if child.type == "parameter_declaration":
            if _has_descendant(child, "function_declarator"):
                name = _find_first_id(child, source_bytes)
                if name:
                    fnptr_names.add(name)
            else:
                # Check if parameter type is a known fnptr typedef
                type_name = _get_type_name(child, source_bytes)
                if type_name and type_name in fnptr_typedefs:
                    name = _find_first_id(child, source_bytes)
                    if name:
                        fnptr_names.add(name)


def _iter_all(node):
    yield node
    for child in node.children:
        yield from _iter_all(child)


def _find_first_id(node, source_bytes):
    if node.type == "identifier":
        return source_bytes[node.start_byte:node.end_byte].decode()
    for child in node.children:
        result = _find_first_id(child, source_bytes)
        if result:
            return result
    return None


def _get_type_name(decl_node, source_bytes):
    """Get the type name from a declaration node (type_identifier or primitive_type)."""
    for child in decl_node.children:
        if child.type == "type_identifier":
            return source_bytes[child.start_byte:child.end_byte].decode()
    return None


def _extract_typedef_fnptr(type_def_node, source_bytes, fnptr_typedefs):
    """Extract typedef names that are function pointer types.

    Handles:
    - typedef void (name)(params);  — function_declarator with parenthesized type_identifier
    - typedef void (*name)(params); — pointer_declarator containing function_declarator
    - typedef ret_type (*name)(params); — pointer_declarator with function_declarator child
    """
    if not _has_descendant(type_def_node, "function_declarator"):
        return

    # The typedef name is the identifier or type_identifier inside the
    # function declarator / pointer declarator structure, but NOT inside
    # a parameter_list.
    for child in _iter_all(type_def_node):
        if child.type == "parenthesized_declarator":
            for sub in _iter_all(child):
                if sub.type in ("type_identifier", "identifier"):
                    name = source_bytes[sub.start_byte:sub.end_byte].decode()
                    fnptr_typedefs.add(name)
                    return
        if child.type == "pointer_declarator":
            if _has_descendant(child, "function_declarator"):
                for sub in _iter_all(child):
                    if sub.type == "identifier" and sub.parent and \
                       sub.parent.type != "parameter_list":
                        name = source_bytes[sub.start_byte:sub.end_byte].decode()
                        fnptr_typedefs.add(name)
                        return


# ---- AST walking for functions, edges, indirect points ----

def _walk_ast(node, source_bytes, filepath, functions, edges, indirect_points,
              fnptr_names, current_func=None):
    if node.type == "function_definition":
        func_name = _get_func_name(node, source_bytes)
        if func_name and node.has_error:
            line = node.start_point[0] + 1
            print(f"WARNING: {filepath}:{line}: syntax error in function "
                  f"'{func_name}', skipping", file=sys.stderr)
            # Still walk children for potential other functions (error recovery)
            for child in node.children:
                _walk_ast(child, source_bytes, filepath, functions, edges,
                         indirect_points, fnptr_names, current_func)
            return

        func_name = _get_func_name(node, source_bytes)
        if func_name:
            fn = FunctionNode(
                name=func_name,
                file=filepath,
                line_start=node.start_point[0] + 1,
                has_body=node.child_by_field_name("body") is not None,
                body_file=filepath,
                body_line_start=node.start_point[0] + 1,
                body_line_end=node.end_point[0] + 1,
            )
            functions.append(fn)
            for child in node.children:
                _walk_ast(child, source_bytes, filepath, functions, edges,
                         indirect_points, fnptr_names, func_name)
            return

    elif node.type == "call_expression" and current_func:
        callee_node = node.child_by_field_name("function")
        if callee_node:
            indirect, expr_text = is_indirect_call(callee_node, source_bytes,
                                                    fnptr_names)
            line = node.start_point[0] + 1
            if indirect:
                uid = compute_uid(filepath, current_func, line, expr_text)
                ip = IndirectPoint(
                    uid=uid,
                    func=current_func,
                    file=filepath,
                    line=line,
                    expression=expr_text,
                )
                indirect_points.append(ip)
            else:
                callee_name = extract_callee_name(callee_node, source_bytes)
                if callee_name:
                    edge = DirectEdge(
                        caller=current_func,
                        callee=callee_name,
                        file=filepath,
                        line=line,
                    )
                    edges.append(edge)

    for child in node.children:
        _walk_ast(child, source_bytes, filepath, functions, edges,
                 indirect_points, fnptr_names, current_func)


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
