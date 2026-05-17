import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from module_a._call_analyzer import parse_file


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "macros")


def test_macro_call_expansion():
    fixture_path = os.path.join(FIXTURES_DIR, "simple_macro", "fixture.c")
    edges_path = os.path.join(FIXTURES_DIR, "simple_macro", "ground_truth_edges.json")

    result = parse_file(fixture_path)

    with open(edges_path) as f:
        expected = json.load(f)

    result_edges = {(e["caller"], e["callee"], e["line"]) for e in result.get("edges", [])}
    expected_edges = {(e["caller"], e["callee"], e["line"]) for e in expected["edges"]}
    assert result_edges == expected_edges, \
        f"Extra: {result_edges - expected_edges}\nMissing: {expected_edges - result_edges}"
