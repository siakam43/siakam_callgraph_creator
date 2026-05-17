"""Shared AST utility functions used by _project_scanner and _call_analyzer."""
from typing import Iterator


def iter_all(node) -> Iterator:
    """Yield node and all descendants."""
    yield node
    for child in node.children:
        yield from iter_all(child)


def has_descendant(node, target_type: str) -> bool:
    """Check if subtree contains a node of the given type."""
    if node.type == target_type:
        return True
    for child in node.children:
        if has_descendant(child, target_type):
            return True
    return False


def is_inside_param_list(node) -> bool:
    """Check if node has a parameter_list ancestor."""
    cur = node
    while cur is not None:
        if cur.type == "parameter_list":
            return True
        cur = cur.parent
    return False


def find_first_id(node, source_bytes) -> str | None:
    """Depth-first search for first identifier text in subtree."""
    if node.type == "identifier":
        return source_bytes[node.start_byte:node.end_byte].decode()
    for child in node.children:
        result = find_first_id(child, source_bytes)
        if result:
            return result
    return None


def get_type_name(decl_node, source_bytes) -> str | None:
    """Extract type_identifier name from a declaration node."""
    for child in decl_node.children:
        if child.type == "type_identifier":
            return source_bytes[child.start_byte:child.end_byte].decode()
    return None


def find_identifier(node, source_bytes) -> str | None:
    """Extract identifier from a function declarator node."""
    if node.type == "identifier":
        return source_bytes[node.start_byte:node.end_byte].decode()
    if node.type == "function_declarator":
        decl = node.child_by_field_name("declarator")
        if decl:
            return find_identifier(decl, source_bytes)
    for child in node.children:
        result = find_identifier(child, source_bytes)
        if result:
            return result
    return None
