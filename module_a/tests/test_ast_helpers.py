"""Tests for _ast_helpers.py — extracted AST utility functions."""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from tree_sitter import Language, Parser
import tree_sitter_c as tsc

from module_a._ast_helpers import (
    iter_all, has_descendant, is_inside_param_list,
    find_first_id, get_type_name, find_identifier,
)

LANG = Language(tsc.language())


def parse_source(source: str):
    parser = Parser(LANG)
    source_bytes = source.encode()
    tree = parser.parse(source_bytes)
    return tree.root_node, source_bytes


def test_iter_all_yields_node_and_descendants():
    root, src = parse_source("int x; int y;")
    types = [n.type for n in iter_all(root)]
    assert "translation_unit" in types
    assert "declaration" in types
    assert len(types) > 3  # root + declarations + identifiers + primitives


def test_has_descendant_finds_nested_type():
    root, src = parse_source("int x;")
    assert has_descendant(root, "identifier")
    assert not has_descendant(root, "function_definition")


def test_is_inside_param_list_detects_ancestor():
    root, src = parse_source("void foo(int x) {}")
    # Find the 'x' identifier inside the parameter list
    found_x = None
    for node in iter_all(root):
        if node.type == "identifier" and src[node.start_byte:node.end_byte].decode() == "x":
            found_x = node
            break
    assert found_x is not None
    assert is_inside_param_list(found_x)

    # Find the function name 'foo' — not inside param list
    found_foo = None
    for node in iter_all(root):
        if node.type == "identifier" and src[node.start_byte:node.end_byte].decode() == "foo":
            found_foo = node
            break
    assert found_foo is not None
    assert not is_inside_param_list(found_foo)


def test_find_first_id_extracts_first_identifier():
    root, src = parse_source("int my_var;")
    found = find_first_id(root, src)
    assert found == "my_var"


def test_get_type_name_extracts_type_identifier():
    root, src = parse_source("my_type var;")
    # Find the declaration node
    decl = None
    for node in iter_all(root):
        if node.type == "declaration":
            decl = node
            break
    assert decl is not None
    name = get_type_name(decl, src)
    assert name == "my_type"


def test_find_identifier_from_function_declarator():
    root, src = parse_source("void my_func(int x) {}")
    # Find the function_definition node
    func_def = None
    for node in iter_all(root):
        if node.type == "function_definition":
            func_def = node
            break
    assert func_def is not None
    declarator = func_def.child_by_field_name("declarator")
    name = find_identifier(declarator, src)
    assert name == "my_func"
