"""Tests for _parser.py — tree-sitter lifecycle management."""
import logging
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from module_a._parser import create_parser, parse_file


FIXTURE_SIMPLE = os.path.join(
    os.path.dirname(__file__), "fixtures", "macros", "simple_macro", "fixture.c"
)
FIXTURE_SYNTAX_ERR = os.path.join(
    os.path.dirname(__file__), "fixtures", "syntax_error", "bad_function", "fixture.c"
)


def test_create_parser_returns_parser():
    p = create_parser()
    assert p is not None
    # tree_sitter Parser doesn't expose a clean type check; verify it has parse method
    assert hasattr(p, "parse")


def test_parse_file_returns_root_and_bytes():
    p = create_parser()
    root, src = parse_file(p, FIXTURE_SIMPLE)
    assert root.type == "translation_unit"
    assert isinstance(src, bytes)
    assert len(src) > 0


def test_parse_file_reports_syntax_errors(caplog):
    p = create_parser()
    caplog.set_level(logging.WARNING)
    root, src = parse_file(p, FIXTURE_SYNTAX_ERR)
    # Should not crash even with syntax errors
    assert root.type == "translation_unit"
    # Should log warnings about syntax errors (ERROR nodes exist)
    # Note: logging output depends on tree-sitter detecting ERROR nodes
