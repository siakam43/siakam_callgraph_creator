"""Phase 1+2: per-file call analysis using project-wide symbols."""
import logging

from module_a.models import FunctionNode, DirectEdge, IndirectPoint, ProjectSymbols
from module_a.uid_generator import compute_uid
from module_a._ast_helpers import (
    iter_all, has_descendant, find_first_id, get_type_name, find_identifier,
)

logger = logging.getLogger(__name__)

# Merged from indirect_detector.py
_INDIRECT_CALLEE_TYPES = frozenset({
    "field_expression",
    "pointer_expression",
    "subscript_expression",
    "cast_expression",
    "call_expression",
    "parenthesized_expression",
    "conditional_expression",
})


class CallAnalyzer:
    """Per-file call graph analysis using project-wide symbols."""

    def __init__(self, symbols: ProjectSymbols, filepath: str,
                 source_bytes: bytes):
        self._symbols = symbols
        self._filepath = filepath
        self._source = source_bytes
        self.functions: list[FunctionNode] = []
        self.edges: list[DirectEdge] = []
        self.indirect_points: list[IndirectPoint] = []

    def analyze(self, root) -> tuple[list, list, list]:
        """Walk the AST and return (functions, edges, indirect_points)."""
        self._walk(root)
        return self.functions, self.edges, self.indirect_points

    # ---- internal ----

    def _walk(self, node, current_func=None, local_fnptr_names=None):
        if node.type == "function_definition":
            declarator = node.child_by_field_name("declarator")
            func_name = find_identifier(declarator or node, self._source)
            if func_name and node.has_error:
                logger.warning("%s:%d: syntax error in function '%s', skipping",
                               self._filepath, node.start_point[0] + 1, func_name)
                for child in node.children:
                    self._walk(child, current_func, local_fnptr_names)
                return

            if func_name:
                fn = FunctionNode(
                    name=func_name,
                    file=self._filepath,
                    line_start=node.start_point[0] + 1,
                    has_body=node.child_by_field_name("body") is not None,
                    body_file=self._filepath,
                    body_line_start=node.start_point[0] + 1,
                    body_line_end=node.end_point[0] + 1,
                )
                self.functions.append(fn)

                func_local_names = set(self._symbols.global_fnptr_names)

                if declarator:
                    param_names = set()
                    _extract_fnptr_params(declarator, self._source, param_names,
                                          self._symbols.typedef_fnptr_names)
                    func_local_names.update(param_names)

                body = node.child_by_field_name("body")
                if body:
                    self._expand_local_fnptr_names(body, func_local_names)

                for child in node.children:
                    self._walk(child, func_name, func_local_names)
                return

        elif node.type == "call_expression" and current_func:
            callee_node = node.child_by_field_name("function")
            if callee_node:
                line = node.start_point[0] + 1
                self._classify_call(callee_node, current_func, local_fnptr_names, line)

        for child in node.children:
            self._walk(child, current_func, local_fnptr_names)

    def _classify_call(self, callee_node, current_func, local_fnptr_names,
                       line) -> None:
        callee_text = self._source[callee_node.start_byte:callee_node.end_byte].decode()

        # Priority 1: macro expansion
        if callee_node.type == "identifier" and callee_text in self._symbols.macro_call_map:
            self.edges.append(DirectEdge(
                caller=current_func,
                callee=self._symbols.macro_call_map[callee_text],
                file=self._filepath,
                line=line,
            ))
            return

        # Priority 2: indirect call by AST type
        if callee_node.type in _INDIRECT_CALLEE_TYPES:
            self._add_indirect_point(current_func, callee_node, line)
            return

        # Priority 3: indirect call by known fnptr name
        effective_names = (local_fnptr_names if local_fnptr_names is not None
                           else self._symbols.global_fnptr_names)
        if callee_node.type == "identifier" and callee_text in effective_names:
            self._add_indirect_point(current_func, callee_node, line)
            return

        # Priority 4: direct call
        if callee_node.type == "identifier":
            self.edges.append(DirectEdge(
                caller=current_func,
                callee=callee_text,
                file=self._filepath,
                line=line,
            ))

    def _add_indirect_point(self, func, callee_node, line):
        expression = self._source[callee_node.start_byte:callee_node.end_byte].decode()
        uid = compute_uid(self._filepath, func, line, expression)
        self.indirect_points.append(IndirectPoint(
            uid=uid, func=func, file=self._filepath,
            line=line, expression=expression,
        ))

    # ---- local fnptr expansion ----

    def _expand_local_fnptr_names(self, body_node, local_names):
        """Iteratively expand local_names from assignments in function body.

        Stops when the set stabilizes (typically 1-3 iterations).
        """
        changed = True
        while changed:
            changed = False
            new_names = set()
            for node in iter_all(body_node):
                names = _extract_names_from_assignment(
                    node, self._source, local_names,
                    self._symbols.typedef_fnptr_names,
                )
                for name in names:
                    if name not in local_names and name not in new_names:
                        new_names.add(name)
                        changed = True
            local_names.update(new_names)


def _extract_fnptr_params(func_declarator_node, source_bytes, names, typedef_names):
    """Extract fnptr parameter names from a function declarator."""
    for child in iter_all(func_declarator_node):
        if child.type == "parameter_declaration":
            if has_descendant(child, "function_declarator"):
                name = find_first_id(child, source_bytes)
                if name:
                    names.add(name)
            else:
                type_name = get_type_name(child, source_bytes)
                if type_name and type_name in typedef_names:
                    name = find_first_id(child, source_bytes)
                    if name:
                        names.add(name)


def _extract_names_from_assignment(node, source_bytes, local_names, typedef_names):
    """Extract new fnptr names from a declaration or assignment node."""
    found = []

    # Pattern 1: declaration with init_declarator
    if node.type == "declaration":
        type_name = get_type_name(node, source_bytes)
        if type_name and type_name in typedef_names:
            for child in iter_all(node):
                if child.type == "init_declarator":
                    name = find_first_id(child, source_bytes)
                    if name:
                        found.append(name)

        for child in iter_all(node):
            if child.type == "init_declarator":
                if has_descendant(child, "function_declarator"):
                    name = find_first_id(child, source_bytes)
                    if name:
                        found.append(name)

    # Pattern 2: assignment_expression
    elif node.type == "assignment_expression":
        lhs = node.child_by_field_name("left")
        rhs = node.child_by_field_name("right")
        if lhs and rhs:
            rhs_text = source_bytes[rhs.start_byte:rhs.end_byte].decode()
            rhs_involves_fnptr = False

            if rhs.type == "identifier" and rhs_text in local_names:
                rhs_involves_fnptr = True
            elif rhs.type == "field_expression":
                rhs_involves_fnptr = True
            elif rhs.type == "cast_expression":
                for sub in iter_all(rhs):
                    if sub.type == "identifier" and \
                       source_bytes[sub.start_byte:sub.end_byte].decode() in local_names:
                        rhs_involves_fnptr = True
                        break

            if rhs_involves_fnptr:
                lhs_name = find_first_id(lhs, source_bytes)
                if lhs_name:
                    found.append(lhs_name)

    # Pattern 3: expression_statement containing assignment
    elif node.type == "expression_statement":
        for child in node.children:
            found.extend(_extract_names_from_assignment(
                child, source_bytes, local_names, typedef_names))

    return found

