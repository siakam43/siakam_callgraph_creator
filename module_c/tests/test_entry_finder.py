import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from module_c.entry_finder import find_entry_functions, _is_basic_params
from module_c.merge import merge_callgraph


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_callgraph():
    return merge_callgraph(
        os.path.join(FIXTURES_DIR, "nodes.json"),
        os.path.join(FIXTURES_DIR, "edges.json"),
        os.path.join(FIXTURES_DIR, "indirect_points.json"),
        os.path.join(FIXTURES_DIR, "indirect"),
    )


class TestIsBasicParams:
    def test_empty_params(self):
        assert _is_basic_params([]) is True

    def test_void_param(self):
        assert _is_basic_params(["void"]) is True

    def test_int_param(self):
        assert _is_basic_params(["int x"]) is True

    def test_int_pointer_param(self):
        assert _is_basic_params(["int *x"]) is False

    def test_struct_param(self):
        assert _is_basic_params(["struct foo *p"]) is False

    def test_union_param(self):
        assert _is_basic_params(["union bar u"]) is False

    def test_array_param(self):
        assert _is_basic_params(["char buf[256]"]) is False

    def test_uint32_t_param(self):
        assert _is_basic_params(["uint32_t count"]) is True

    def test_size_t_and_int_params(self):
        assert _is_basic_params(["size_t len", "int flags"]) is True

    def test_mixed_basic_and_nonbasic(self):
        assert _is_basic_params(["uint32_t x", "device_t *d"]) is False

    def test_unsigned_long(self):
        assert _is_basic_params(["unsigned long n"]) is True

    def test_typedef_struct_value(self):
        assert _is_basic_params(["device_t dev"]) is False

    def test_const_char_pointer(self):
        assert _is_basic_params(["const char *name"]) is False

    def test_function_pointer_param(self):
        assert _is_basic_params(["void (*callback)(int)"]) is False


class TestFindEntryFunctions:
    def test_excludes_header_only(self):
        entries = find_entry_functions({
            "nodes": [
                {"name": "f1", "has_body": True, "body_file": "a.c",
                 "file": "a.c", "line_start": 1,
                 "body_line_start": 1, "body_line_end": 5,
                 "params": ["int *p"]},
                {"name": "f2", "has_body": False, "body_file": None,
                 "file": "b.h", "line_start": -1,
                 "body_line_start": None, "body_line_end": None,
                 "params": []},
            ],
            "edges": [],
        })
        names = {e["name"] for e in entries}
        assert "f1" in names
        assert "f2" not in names

    def test_excludes_header_body(self):
        entries = find_entry_functions({
            "nodes": [
                {"name": "inl", "has_body": True, "body_file": "util.h",
                 "file": "util.h", "line_start": 1,
                 "body_line_start": 1, "body_line_end": 5,
                 "params": ["int *p"]},
            ],
            "edges": [],
        })
        assert len(entries) == 0

    def test_no_callers_is_entry(self):
        entries = find_entry_functions({
            "nodes": [
                {"name": "main", "has_body": True, "body_file": "a.c",
                 "file": "a.c", "line_start": 1,
                 "body_line_start": 1, "body_line_end": 5,
                 "params": ["int argc", "char **argv"]},
                {"name": "helper", "has_body": True, "body_file": "a.c",
                 "file": "a.c", "line_start": 6,
                 "body_line_start": 6, "body_line_end": 10,
                 "params": ["int x"]},
            ],
            "edges": [
                {"caller": "main", "callee": "helper", "type": "direct"},
            ],
        })
        names = {e["name"] for e in entries}
        assert "main" in names
        assert "helper" not in names

    def test_excludes_basic_params_only(self):
        entries = find_entry_functions({
            "nodes": [
                {"name": "noop", "has_body": True, "body_file": "a.c",
                 "file": "a.c", "line_start": 1,
                 "body_line_start": 1, "body_line_end": 5,
                 "params": ["int x"]},
            ],
            "edges": [],
        })
        assert len(entries) == 0

    def test_excludes_no_params(self):
        entries = find_entry_functions({
            "nodes": [
                {"name": "noop", "has_body": True, "body_file": "a.c",
                 "file": "a.c", "line_start": 1,
                 "body_line_start": 1, "body_line_end": 5,
                 "params": []},
            ],
            "edges": [],
        })
        assert len(entries) == 0

    def test_excludes_void_param(self):
        entries = find_entry_functions({
            "nodes": [
                {"name": "noop", "has_body": True, "body_file": "a.c",
                 "file": "a.c", "line_start": 1,
                 "body_line_start": 1, "body_line_end": 5,
                 "params": ["void"]},
            ],
            "edges": [],
        })
        assert len(entries) == 0

    def test_cycle_no_entry(self):
        entries = find_entry_functions({
            "nodes": [
                {"name": "a", "has_body": True, "body_file": "x.c",
                 "file": "x.c", "line_start": 1,
                 "body_line_start": 1, "body_line_end": 5,
                 "params": ["int *p"]},
                {"name": "b", "has_body": True, "body_file": "x.c",
                 "file": "x.c", "line_start": 6,
                 "body_line_start": 6, "body_line_end": 10,
                 "params": ["int *p"]},
            ],
            "edges": [
                {"caller": "a", "callee": "b", "type": "direct"},
                {"caller": "b", "callee": "a", "type": "direct"},
            ],
        })
        assert len(entries) == 0

    def test_empty_graph(self):
        entries = find_entry_functions({"nodes": [], "edges": []})
        assert entries == []
