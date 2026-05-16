"""Detect indirect (function pointer) calls in C AST."""

INDIRECT_CALLEE_TYPES = {
    "field_expression",
    "pointer_expression",
    "subscript_expression",
    "cast_expression",
    "call_expression",
    "parenthesized_expression",
    "conditional_expression",
}


def is_indirect_call(callee_node, source_bytes, fnptr_names: set) -> tuple:
    """Determine if a call_expression's function child is an indirect call.

    Returns (is_indirect: bool, expression_text: str).
    """
    expression = source_bytes[callee_node.start_byte:callee_node.end_byte].decode()

    if callee_node.type in INDIRECT_CALLEE_TYPES:
        return (True, expression)

    if callee_node.type == "identifier":
        if expression in fnptr_names:
            return (True, expression)
        return (False, expression)

    return (False, expression)


def extract_callee_name(callee_node, source_bytes) -> str | None:
    """Extract callee function name from a direct call identifier node."""
    if callee_node.type == "identifier":
        return source_bytes[callee_node.start_byte:callee_node.end_byte].decode()
    return None
