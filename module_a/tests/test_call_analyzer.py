"""Tests for _call_analyzer.py — Phase 1+2 per-file call analysis."""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from module_a._call_analyzer import CallAnalyzer, parse_file
from module_a._project_scanner import ProjectSymbols
from module_a._parser import create_parser as _cp, parse_file as _pf
from module_a.models import FunctionNode, DirectEdge, IndirectPoint


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


class TestCallAnalyzerInit:
    def test_initial_state(self):
        sym = ProjectSymbols(set(), set(), {})
        a = CallAnalyzer(sym, "test.c", b"")
        assert a.functions == []
        assert a.edges == []
        assert a.indirect_points == []


class TestMacroExpansion:
    def test_macro_call_expands_to_callee(self):
        """CALL_DEBUG() expands to debug_log."""
        result = parse_file(os.path.join(
            FIXTURES, "macro_expansion", "example_1_simple", "fixture.c"))
        edges = {(e["caller"], e["callee"]) for e in result["edges"]}
        assert ("do_work", "debug_log") in edges
        # The macro name should NOT appear as callee
        assert not any(e["callee"] == "CALL_DEBUG" for e in result["edges"])

    def test_macro_first_call_only(self):
        """Multi-call macro body → first callee extracted."""
        result = parse_file(os.path.join(
            FIXTURES, "macro_expansion", "example_2_multi_call", "fixture.c"))
        edges = {(e["caller"], e["callee"]) for e in result["edges"]}
        assert ("do_work", "log") in edges


class TestIndirectCallDetection:
    def test_indirect_by_ast_type_field_expression(self):
        sym = ProjectSymbols(set(), set(), {})
        src = b'void f(void) { ops->read(); }'
        from tree_sitter import Language, Parser
        import tree_sitter_c as tsc
        parser, src_bytes = Parser(Language(tsc.language())), src
        root = parser.parse(src_bytes).root_node
        a = CallAnalyzer(sym, "test.c", src_bytes)
        funcs, edges, ips = a.analyze(root)
        assert len(ips) == 1
        assert ips[0].expression == "ops->read"

    def test_indirect_by_fnptr_name(self):
        sym = ProjectSymbols(set(), {"handler"}, {})
        src = b'void f(void) { handler(42); }'
        from tree_sitter import Language, Parser
        import tree_sitter_c as tsc
        parser, src_bytes = Parser(Language(tsc.language())), src
        root = parser.parse(src_bytes).root_node
        a = CallAnalyzer(sym, "test.c", src_bytes)
        funcs, edges, ips = a.analyze(root)
        assert len(ips) == 1
        assert ips[0].expression == "handler"


class TestDirectCall:
    def test_plain_function_call(self):
        result = parse_file(os.path.join(
            FIXTURES, "macros", "simple_macro", "fixture.c"))
        edges = {(e["caller"], e["callee"]) for e in result["edges"]}
        # debug_log calls fprintf
        assert ("debug_log", "fprintf") in edges
        # do_work → debug_log (macro expansion)
        assert ("do_work", "debug_log") in edges


class TestParseFile:
    def test_returns_dict_with_expected_keys(self):
        result = parse_file(os.path.join(
            FIXTURES, "macros", "simple_macro", "fixture.c"))
        assert "functions" in result
        assert "edges" in result
        assert "indirect_points" in result
        assert isinstance(result["functions"], list)
        assert isinstance(result["edges"], list)
        assert isinstance(result["indirect_points"], list)

    def test_functions_have_required_fields(self):
        result = parse_file(os.path.join(
            FIXTURES, "macros", "simple_macro", "fixture.c"))
        for fn in result["functions"]:
            assert "name" in fn
            assert "file" in fn
            assert "line_start" in fn
            assert "has_body" in fn


class TestFunctionDetection:
    def test_finds_functions(self):
        result = parse_file(os.path.join(
            FIXTURES, "macros", "simple_macro", "fixture.c"))
        names = {f["name"] for f in result["functions"]}
        assert "debug_log" in names
        assert "do_work" in names

    def test_has_body_true_for_function_with_body(self):
        result = parse_file(os.path.join(
            FIXTURES, "macros", "simple_macro", "fixture.c"))
        for fn in result["functions"]:
            assert fn["has_body"] is True
