import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from module_c.entry_finder import find_entry_functions
from module_c.merge import merge_callgraph


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_callgraph():
    return merge_callgraph(
        os.path.join(FIXTURES_DIR, "nodes.json"),
        os.path.join(FIXTURES_DIR, "edges.json"),
        os.path.join(FIXTURES_DIR, "indirect_points.json"),
        os.path.join(FIXTURES_DIR, "indirect"),
    )


def test_entry_functions_are_has_body():
    entries = find_entry_functions({
        "nodes": [
            {"name": "f1", "has_body": True, "body_file": "a.c", "file": "a.c", "line_start": 1, "body_line_start": 1, "body_line_end": 5},
            {"name": "f2", "has_body": False, "body_file": None, "file": "b.h", "line_start": -1, "body_line_start": None, "body_line_end": None},
        ],
        "edges": [],
    })
    names = {e["name"] for e in entries}
    assert "f1" in names
    assert "f2" not in names


def test_no_callers_is_entry():
    entries = find_entry_functions({
        "nodes": [
            {"name": "main", "has_body": True, "body_file": "a.c", "file": "a.c", "line_start": 1, "body_line_start": 1, "body_line_end": 5},
            {"name": "helper", "has_body": True, "body_file": "a.c", "file": "a.c", "line_start": 6, "body_line_start": 6, "body_line_end": 10},
        ],
        "edges": [
            {"caller": "main", "callee": "helper", "type": "direct"},
        ],
    })
    names = {e["name"] for e in entries}
    assert "main" in names
    assert "helper" not in names


def test_cycle_no_entry():
    entries = find_entry_functions({
        "nodes": [
            {"name": "a", "has_body": True, "body_file": "x.c", "file": "x.c", "line_start": 1, "body_line_start": 1, "body_line_end": 5},
            {"name": "b", "has_body": True, "body_file": "x.c", "file": "x.c", "line_start": 6, "body_line_start": 6, "body_line_end": 10},
        ],
        "edges": [
            {"caller": "a", "callee": "b", "type": "direct"},
            {"caller": "b", "callee": "a", "type": "direct"},
        ],
    })
    assert len(entries) == 0


def test_entry_from_fixture():
    cg = _load_callgraph()
    entries = find_entry_functions(cg)
    names = {e["name"] for e in entries}
    assert names == {"init", "orphan"}


def test_empty_graph():
    entries = find_entry_functions({"nodes": [], "edges": []})
    assert entries == []
