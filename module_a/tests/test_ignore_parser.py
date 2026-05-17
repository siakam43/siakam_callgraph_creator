import os
import sys
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from module_a.ignore_parser import parse_siakamignore, should_exclude


def test_no_ignore_file():
    patterns = parse_siakamignore("/nonexistent/path")
    assert patterns == []


def test_parse_simple_patterns():
    content = "# comment line\nbuild/\n*.o\n"
    tmp_dir = tempfile.mkdtemp()
    try:
        with open(os.path.join(tmp_dir, ".siakamignore"), "w") as f:
            f.write(content)
        patterns = parse_siakamignore(tmp_dir)
        assert "build/" in patterns
        assert "*.o" in patterns
        assert len(patterns) == 2
    finally:
        os.remove(os.path.join(tmp_dir, ".siakamignore"))
        os.rmdir(tmp_dir)


def test_should_exclude_directory():
    patterns = ["build/"]
    assert should_exclude(patterns, "build/output.o") is True
    assert should_exclude(patterns, "build/sub/dir/file.c") is True
    assert should_exclude(patterns, "src/build.c") is False


def test_should_exclude_glob():
    patterns = ["*.o"]
    assert should_exclude(patterns, "file.o") is True
    assert should_exclude(patterns, "file.c") is False


def test_should_exclude_negation():
    patterns = ["*.o", "!important.o"]
    assert should_exclude(patterns, "file.o") is True
    assert should_exclude(patterns, "important.o") is False


def test_empty_and_comment_lines():
    content = "\n  \n# this is a comment\n*.h\n"
    tmp_dir = tempfile.mkdtemp()
    try:
        with open(os.path.join(tmp_dir, ".siakamignore"), "w") as f:
            f.write(content)
        patterns = parse_siakamignore(tmp_dir)
        assert patterns == ["*.h"]
    finally:
        os.remove(os.path.join(tmp_dir, ".siakamignore"))
        os.rmdir(tmp_dir)
