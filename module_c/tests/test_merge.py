import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from module_c.merge import merge_callgraph, generate_dot


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
EXPECTED_DIR = os.path.join(os.path.dirname(__file__), "expected")


def test_merge_direct_edges():
    cg = merge_callgraph(
        os.path.join(FIXTURES_DIR, "nodes.json"),
        os.path.join(FIXTURES_DIR, "edges.json"),
        os.path.join(FIXTURES_DIR, "indirect_points.json"),
        os.path.join(FIXTURES_DIR, "indirect"),
    )
    direct = [e for e in cg["edges"] if e["type"] == "direct"]
    assert len(direct) == 6


def test_merge_indirect_edges():
    cg = merge_callgraph(
        os.path.join(FIXTURES_DIR, "nodes.json"),
        os.path.join(FIXTURES_DIR, "edges.json"),
        os.path.join(FIXTURES_DIR, "indirect_points.json"),
        os.path.join(FIXTURES_DIR, "indirect"),
    )
    indirect = [e for e in cg["edges"] if e["type"] == "indirect"]
    assert len(indirect) == 2


def test_merge_failed_indirect_ignored():
    cg = merge_callgraph(
        os.path.join(FIXTURES_DIR, "nodes.json"),
        os.path.join(FIXTURES_DIR, "edges.json"),
        os.path.join(FIXTURES_DIR, "indirect_points.json"),
        os.path.join(FIXTURES_DIR, "indirect"),
    )
    uids = {e.get("uid") for e in cg["edges"] if e["type"] == "indirect"}
    assert "cccccccc" not in uids


def test_merge_empty_targets_no_edges():
    cg = merge_callgraph(
        os.path.join(FIXTURES_DIR, "nodes.json"),
        os.path.join(FIXTURES_DIR, "edges.json"),
        os.path.join(FIXTURES_DIR, "indirect_points.json"),
        os.path.join(FIXTURES_DIR, "indirect"),
    )
    uids = {e.get("uid") for e in cg["edges"] if e["type"] == "indirect"}
    assert "bbbbbbbb" not in uids


def test_full_callgraph_matches_expected():
    cg = merge_callgraph(
        os.path.join(FIXTURES_DIR, "nodes.json"),
        os.path.join(FIXTURES_DIR, "edges.json"),
        os.path.join(FIXTURES_DIR, "indirect_points.json"),
        os.path.join(FIXTURES_DIR, "indirect"),
    )
    with open(os.path.join(EXPECTED_DIR, "callgraph_expected.json")) as f:
        expected = json.load(f)
    assert len(cg["nodes"]) == len(expected["nodes"])
    result_edges = {(e["caller"], e["callee"], e["type"], e.get("uid", ""))
                    for e in cg["edges"]}
    expected_edges = {(e["caller"], e["callee"], e["type"], e.get("uid", ""))
                      for e in expected["edges"]}
    assert result_edges == expected_edges


def test_generate_dot_format():
    cg = merge_callgraph(
        os.path.join(FIXTURES_DIR, "nodes.json"),
        os.path.join(FIXTURES_DIR, "edges.json"),
        os.path.join(FIXTURES_DIR, "indirect_points.json"),
        os.path.join(FIXTURES_DIR, "indirect"),
    )
    dot = generate_dot(cg)
    assert dot.startswith("digraph callgraph {")
    assert dot.endswith("}\n")
    assert '"init" -> "do_work"' in dot
    assert "indirect" in dot
