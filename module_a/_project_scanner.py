"""Phase 0: project-wide symbol collection for cross-file analysis."""
import re

from module_a.models import ProjectSymbols
from module_a._ast_helpers import (
    iter_all, has_descendant, is_inside_param_list,
    find_first_id, get_type_name,
)

# C keywords that can appear as identifier(args) in macro bodies
_C_KEYWORDS = frozenset({"if", "while", "for", "switch", "void", "return", "sizeof"})


# ---- Pass 0a: typedef fnptr names ----


def scan_typedefs(root, source_bytes) -> set[str]:
    """Collect typedef names that are function pointer types.

    Handles:
      typedef void (name)(params);        -- function_declarator wrapping type_identifier
      typedef void (*name)(params);       -- pointer_declarator with function_declarator
      typedef ret *(*name)(params);       -- nested pointer_declarator with fnptr
    """
    names = set()
    _scan_typedefs_inner(root, source_bytes, names)
    return names


def _scan_typedefs_inner(node, source_bytes, names):
    if node.type == "type_definition":
        _extract_typedef_fnptr(node, source_bytes, names)
    for child in node.children:
        _scan_typedefs_inner(child, source_bytes, names)


def _extract_typedef_fnptr(type_def_node, source_bytes, names):
    if not has_descendant(type_def_node, "function_declarator"):
        return

    for child in iter_all(type_def_node):
        if child.type == "parenthesized_declarator":
            for sub in iter_all(child):
                if sub.type in ("type_identifier", "identifier"):
                    name = source_bytes[sub.start_byte:sub.end_byte].decode()
                    names.add(name)
                    return

        if child.type == "pointer_declarator":
            if has_descendant(child, "function_declarator"):
                for sub in iter_all(child):
                    if sub.type in ("type_identifier", "identifier"):
                        if not is_inside_param_list(sub):
                            name = source_bytes[sub.start_byte:sub.end_byte].decode()
                            names.add(name)
                            return


# ---- Pass 0a: function-like macro call map ----


def scan_macros(root, source_bytes) -> dict[str, str]:
    """Collect function-like macro --> first callee mapping.

    tree-sitter does NOT parse the preproc_arg body into AST, so we use
    regex text matching on the body text.
    """
    macros = {}
    for node in iter_all(root):
        if node.type != "preproc_function_def":
            continue

        macro_name = None
        body = None
        param_names = set()

        for child in node.children:
            if child.type == "identifier" and macro_name is None:
                macro_name = source_bytes[child.start_byte:child.end_byte].decode()
            elif child.type == "preproc_params":
                params_text = source_bytes[child.start_byte:child.end_byte].decode()
                param_names = set(re.findall(r'\b(\w+)\b', params_text))
            elif child.type == "preproc_arg":
                body = source_bytes[child.start_byte:child.end_byte].decode()

        if macro_name and body:
            body_clean = re.sub(r'^do\s*\{', '', body.strip())
            call_match = re.search(r'(\w+)\s*\(', body_clean)
            if call_match:
                callee = call_match.group(1)
                if callee not in param_names and callee not in _C_KEYWORDS:
                    macros[macro_name] = callee

    return macros


# ---- Pass 0b: global fnptr variable names ----


def scan_global_fnptrs(root, source_bytes, typedef_fnptr_names: set[str]) -> set[str]:
    """Collect global (file-scope) fnptr variable names.

    Does NOT recurse into function_definition bodies -- function-scoped
    fnptr params/locals are detected in Phase 1+2 by _call_analyzer.
    """
    names = set()
    _scan_globals_inner(root, source_bytes, typedef_fnptr_names, names)
    return names


def _scan_globals_inner(node, source_bytes, typedef_fnptr_names, names):
    # Stop at function bodies -- those are handled in Phase 1+2
    if node.type == "function_definition":
        return
    if node.type == "compound_statement":
        return

    if node.type == "declaration":
        _extract_fnptr_from_declaration(node, source_bytes, names, typedef_fnptr_names)

    for child in node.children:
        _scan_globals_inner(child, source_bytes, typedef_fnptr_names, names)


def _extract_fnptr_from_declaration(decl_node, source_bytes, names, typedef_names):
    # Pattern 1: plain declaration "typedef_name var;"
    # tree-sitter produces direct identifier child (no init_declarator when no init)
    type_name = get_type_name(decl_node, source_bytes)
    if type_name and type_name in typedef_names:
        for child in decl_node.children:
            if child.type == "identifier":
                names.add(source_bytes[child.start_byte:child.end_byte].decode())
                return

    # Pattern 2: init_declarator (with optional initialization)
    # "typedef_name var = init;" or "type (*var)(params) = init;"
    for child in iter_all(decl_node):
        if child.type == "init_declarator":
            if has_descendant(child, "function_declarator"):
                name = find_first_id(child, source_bytes)
                if name:
                    names.add(name)
                    return
            if type_name and type_name in typedef_names:
                name = find_first_id(child, source_bytes)
                if name:
                    names.add(name)
