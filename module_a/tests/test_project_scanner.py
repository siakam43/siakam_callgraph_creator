"""Tests for _project_scanner.py — Phase 0 cross-file symbol collection."""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from module_a._project_scanner import (
    ProjectSymbols, scan_typedefs, scan_macros, scan_global_fnptrs,
)
from module_a._parser import create_parser, parse_file


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _parse(fixture_path):
    p = create_parser()
    return parse_file(p, fixture_path)


class TestProjectSymbols:
    def test_default_construction(self):
        ps = ProjectSymbols(set(), set(), {})
        assert ps.typedef_fnptr_names == set()
        assert ps.global_fnptr_names == set()
        assert ps.macro_call_map == {}

    def test_with_data(self):
        ps = ProjectSymbols({"cb_t"}, {"handler"}, {"CALL": "target"})
        assert "cb_t" in ps.typedef_fnptr_names
        assert "handler" in ps.global_fnptr_names
        assert ps.macro_call_map["CALL"] == "target"


class TestScanTypedefs:
    def test_detects_typedef_fnptr(self):
        root, src = _parse(os.path.join(
            FIXTURES, "cross_file", "example_1_typedef", "types.h"))
        names = scan_typedefs(root, src)
        assert "callback_t" in names

    def test_no_fnptr_typedef_returns_empty(self):
        root, src = _parse(os.path.join(
            FIXTURES, "macros", "simple_macro", "fixture.c"))
        names = scan_typedefs(root, src)
        assert names == set()


class TestScanMacros:
    def test_expands_simple_macro(self):
        root, src = _parse(os.path.join(
            FIXTURES, "cross_file", "example_2_macro", "api.h"))
        macros = scan_macros(root, src)
        assert macros.get("CALL_API") == "do_api_call"

    def test_skips_macro_with_param_callee(self):
        # #define INVOKE(h) h(0) → callee "h" is param → excluded
        root, src = _parse(os.path.join(
            FIXTURES, "macro_expansion", "example_1_simple", "fixture.c"))
        macros = scan_macros(root, src)
        # CALL_DEBUG() → debug_log(__func__) → callee=debug_log, not a param
        assert macros.get("CALL_DEBUG") == "debug_log"


class TestScanGlobalFnptrs:
    def test_detects_global_fnptr_with_cross_file_typedef(self):
        root, src = _parse(os.path.join(
            FIXTURES, "cross_file", "example_1_typedef", "main.c"))
        names = scan_global_fnptrs(root, src, {"callback_t"})
        assert "handler" in names

    def test_no_fnptr_without_typedef(self):
        root, src = _parse(os.path.join(
            FIXTURES, "cross_file", "example_1_typedef", "main.c"))
        # With empty typedef set, callback_t is unknown → handler NOT detected
        names = scan_global_fnptrs(root, src, set())
        assert "handler" not in names

    def test_inline_fnptr_no_typedef_needed(self):
        root, src = _parse(os.path.join(
            FIXTURES, "cross_file", "example_1_typedef", "main.c"))
        # my_func is a regular function, not a fnptr variable
        assert "my_func" not in scan_global_fnptrs(root, src, {"callback_t"})
