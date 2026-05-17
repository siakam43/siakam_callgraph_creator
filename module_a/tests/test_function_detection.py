import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from module_a._call_analyzer import parse_file


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def discover_fixtures():
    fixtures = []
    for category in sorted(os.listdir(FIXTURES_DIR)):
        cat_path = os.path.join(FIXTURES_DIR, category)
        if not os.path.isdir(cat_path):
            continue
        for example in sorted(os.listdir(cat_path)):
            example_path = os.path.join(cat_path, example)
            fixture_path = os.path.join(example_path, "fixture.c")
            truth_path = os.path.join(example_path, "ground_truth_nodes.json")
            if os.path.exists(fixture_path) and os.path.exists(truth_path):
                fixtures.append((category, example, fixture_path, truth_path))
    return fixtures


@pytest.mark.parametrize("category,example,fixture_path,truth_path",
                         discover_fixtures())
def test_function_detection(category, example, fixture_path, truth_path):
    result = parse_file(fixture_path)

    with open(truth_path) as f:
        expected = json.load(f)

    result_names = {fn["name"] for fn in result["functions"]}
    expected_names = {fn["name"] for fn in expected["functions"]}
    assert result_names == expected_names, \
        f"Mismatch in {category}/{example}:\nExtra: {result_names - expected_names}\nMissing: {expected_names - result_names}"

    expected_by_key = {(ef["name"], ef["line_start"]): ef for ef in expected["functions"]}

    for fn in result["functions"]:
        key = (fn["name"], fn["line_start"])
        expected_fn = expected_by_key.get(key)
        if expected_fn is None:
            continue
        assert fn["has_body"] == expected_fn["has_body"], \
            f"{category}/{example}: {fn['name']} has_body mismatch"
