import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from module_a.analyzer import analyze_single_file


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def discover_fixtures_with_direct_calls():
    fixtures = []
    for category in sorted(os.listdir(FIXTURES_DIR)):
        cat_path = os.path.join(FIXTURES_DIR, category)
        if not os.path.isdir(cat_path):
            continue
        for example in sorted(os.listdir(cat_path)):
            example_path = os.path.join(cat_path, example)
            fixture_path = os.path.join(example_path, "fixture.c")
            edges_path = os.path.join(example_path, "ground_truth_edges.json")
            if os.path.exists(fixture_path) and os.path.exists(edges_path):
                with open(edges_path) as f:
                    expected = json.load(f)
                if expected.get("edges"):
                    fixtures.append((category, example, fixture_path, edges_path))
    return fixtures


@pytest.mark.parametrize("category,example,fixture_path,edges_path",
                         discover_fixtures_with_direct_calls())
def test_direct_edges(category, example, fixture_path, edges_path):
    result = analyze_single_file(fixture_path)

    with open(edges_path) as f:
        expected = json.load(f)

    result_edges = {(e["caller"], e["callee"], e["line"]) for e in result.get("edges", [])}
    expected_edges = {(e["caller"], e["callee"], e["line"]) for e in expected["edges"]}
    assert result_edges == expected_edges, \
        f"Mismatch in {category}/{example}:\nExtra: {result_edges - expected_edges}\nMissing: {expected_edges - result_edges}"
