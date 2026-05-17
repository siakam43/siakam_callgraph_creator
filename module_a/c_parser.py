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

    fnptr_typedefs = set()
    global_fnptr_names = set()
    _collect_typedefs_and_globals(root, source_bytes, global_fnptr_names,
                                  fnptr_typedefs)

    functions = []
    edges = []
    indirect_points = []

    _walk_ast(root, source_bytes, filepath, functions, edges, indirect_points,
              global_fnptr_names, fnptr_typedefs)

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


# ============ Phase 0: typedef + global fnptr collection ============

def _collect_typedefs_and_globals(node, source_bytes, global_fnptr_names,
                                   fnptr_typedefs):
    """File-level scan: collect typedef→fnptr mappings and global fnptr names."""
    if node.type == "declaration":
        _extract_fnptr_from_declaration(node, source_bytes, global_fnptr_names,
                                        fnptr_typedefs)
    elif node.type == "function_definition":
        declarator = node.child_by_field_name("declarator")
        if declarator:
            _extract_fnptr_params(declarator, source_bytes, global_fnptr_names,
                                  fnptr_typedefs)
    elif node.type == "type_definition":
        _extract_typedef_fnptr(node, source_bytes, fnptr_typedefs)
    for child in node.children:
        _collect_typedefs_and_globals(child, source_bytes, global_fnptr_names,
                                      fnptr_typedefs)


def _has_descendant(node, target_type):
    if node.type == target_type:
        return True
    for child in node.children:
        if _has_descendant(child, target_type):
            return True
    return False


def _is_inside_param_list(node):
    """Check if node has a parameter_list ancestor."""
    cur = node
    while cur is not None:
        if cur.type == "parameter_list":
            return True
        cur = cur.parent
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
    for child in decl_node.children:
        if child.type == "type_identifier":
            return source_bytes[child.start_byte:child.end_byte].decode()
    return None


def _extract_typedef_fnptr(type_def_node, source_bytes, fnptr_typedefs):
    """Extract typedef names that are function pointer types.

    Handles:
    - typedef void (name)(params);  — function_declarator wrapping type_identifier
    - typedef void (*name)(params); — pointer_declarator with function_declarator
    - typedef ret *(*name)(params); — nested pointer_declarator with fnptr
    """
    if not _has_descendant(type_def_node, "function_declarator"):
        return

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
                    if sub.type in ("type_identifier", "identifier"):
                        if not _is_inside_param_list(sub):
                            name = source_bytes[sub.start_byte:sub.end_byte].decode()
                            fnptr_typedefs.add(name)
                            return


# ============ Phase 1+2: function-scoped walk with local expansion ============

def _walk_ast(node, source_bytes, filepath, functions, edges, indirect_points,
              global_fnptr_names, fnptr_typedefs, current_func=None,
              local_fnptr_names=None):
    if node.type == "function_definition":
        func_name = _get_func_name(node, source_bytes)
        if func_name and node.has_error:
            line = node.start_point[0] + 1
            print(f"WARNING: {filepath}:{line}: syntax error in function "
                  f"'{func_name}', skipping", file=sys.stderr)
            for child in node.children:
                _walk_ast(child, source_bytes, filepath, functions, edges,
                         indirect_points, global_fnptr_names, fnptr_typedefs,
                         current_func, local_fnptr_names)
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

            # Build function-scoped fnptr name set
            func_local_names = set(global_fnptr_names)

            # Add this function's own fnptr parameters
            declarator = node.child_by_field_name("declarator")
            if declarator:
                param_names = set()
                _extract_fnptr_params(declarator, source_bytes, param_names,
                                      fnptr_typedefs)
                func_local_names.update(param_names)

            # Iterative expansion: scan body for assignments to new fnptr names
            body = node.child_by_field_name("body")
            if body:
                _expand_local_fnptr_names(body, source_bytes, func_local_names,
                                          fnptr_typedefs)

            # Walk children with function-scoped names
            for child in node.children:
                _walk_ast(child, source_bytes, filepath, functions, edges,
                         indirect_points, global_fnptr_names, fnptr_typedefs,
                         func_name, func_local_names)
            return

    elif node.type == "call_expression" and current_func:
        callee_node = node.child_by_field_name("function")
        if callee_node:
            effective_names = local_fnptr_names if local_fnptr_names is not None else global_fnptr_names
            indirect, expr_text = is_indirect_call(callee_node, source_bytes,
                                                    effective_names)
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
                 indirect_points, global_fnptr_names, fnptr_typedefs,
                 current_func, local_fnptr_names)


def _expand_local_fnptr_names(body_node, source_bytes, local_names,
                               fnptr_typedefs):
    """Iteratively expand local_names by scanning assignments in the function body.
    Stops when the set stabilizes (typically 1-3 iterations).
    """
    changed = True
    while changed:
        changed = False
        new_names = set()
        for node in _iter_all(body_node):
            names = _extract_names_from_assignment(node, source_bytes,
                                                    local_names, fnptr_typedefs)
            for name in names:
                if name not in local_names and name not in new_names:
                    new_names.add(name)
                    changed = True
        local_names.update(new_names)


def _extract_names_from_assignment(node, source_bytes, local_names,
                                    fnptr_typedefs):
    """Extract new fnptr names from a declaration or assignment node.

    Returns list of new names introduced by this node.
    """
    found = []

    # Pattern 1: declaration with init_declarator
    # "typedef_name var = init;" or "typedef_name *var = init;"
    if node.type == "declaration":
        type_name = _get_type_name(node, source_bytes)
        if type_name and type_name in fnptr_typedefs:
            for child in _iter_all(node):
                if child.type == "init_declarator":
                    name = _find_first_id(child, source_bytes)
                    if name:
                        found.append(name)

        # Also check for direct fnptr: "type (*var)(params) = init;"
        for child in _iter_all(node):
            if child.type == "init_declarator":
                if _has_descendant(child, "function_declarator"):
                    name = _find_first_id(child, source_bytes)
                    if name:
                        found.append(name)

    # Pattern 2: assignment_expression
    # "a = known_name;" or "a = ptr->member;"
    elif node.type == "assignment_expression":
        lhs = node.child_by_field_name("left")
        rhs = node.child_by_field_name("right")
        if lhs and rhs:
            # Check if RHS references a known fnptr
            rhs_text = source_bytes[rhs.start_byte:rhs.end_byte].decode()
            rhs_involves_fnptr = False

            # Direct reference: rhs is known fnptr name
            if rhs.type == "identifier" and rhs_text in local_names:
                rhs_involves_fnptr = True
            # Struct extraction: rhs is field_expression like ptr->member
            elif rhs.type == "field_expression":
                rhs_involves_fnptr = True
            # Cast expression wrapping a fnptr: (type)known_name
            elif rhs.type == "cast_expression":
                for sub in _iter_all(rhs):
                    if sub.type == "identifier" and \
                       source_bytes[sub.start_byte:sub.end_byte].decode() in local_names:
                        rhs_involves_fnptr = True
                        break

            if rhs_involves_fnptr:
                lhs_name = _find_first_id(lhs, source_bytes)
                if lhs_name:
                    found.append(lhs_name)

    # Pattern 3: init_declarator inside declaration (handled above via declaration)
    # Pattern 4: "a = known_name;" as expression_statement
    elif node.type == "expression_statement":
        for child in node.children:
            found.extend(_extract_names_from_assignment(
                child, source_bytes, local_names, fnptr_typedefs))

    return found


# ============ AST helpers ============

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
