import json
import hashlib
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from module_a.c_parser import parse_file


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def compute_uid(file, func, line, expression):
    raw = f"{file}:{func}:{line}:{expression}"
    return hashlib.sha256(raw.encode()).hexdigest()[:8]


def discover_all_fixtures():
    fixtures = []
    for category in sorted(os.listdir(FIXTURES_DIR)):
        cat_path = os.path.join(FIXTURES_DIR, category)
        if not os.path.isdir(cat_path):
            continue
        for example in sorted(os.listdir(cat_path)):
            example_path = os.path.join(cat_path, example)
            fixture_path = os.path.join(example_path, "fixture.c")
            truth_path = os.path.join(example_path, "ground_truth_indirect.json")
            if os.path.exists(fixture_path) and os.path.exists(truth_path):
                fixtures.append((category, example, fixture_path, truth_path))
    return fixtures


@pytest.mark.parametrize("category,example,fixture_path,truth_path",
                         discover_all_fixtures())
def test_indirect_detection(category, example, fixture_path, truth_path):
    result = parse_file(fixture_path)

    with open(truth_path) as f:
        expected = json.load(f)

    result_points = {(ip["func"], ip["file"], ip["line"], ip["expression"])
                     for ip in result.get("indirect_points", [])}
    expected_points = {(ip["func"], ip["file"], ip["line"], ip["expression"])
                       for ip in expected.get("indirect_points", [])}
    assert result_points == expected_points, \
        f"Mismatch in {category}/{example}:\nExtra: {result_points - expected_points}\nMissing: {expected_points - result_points}"

    for ip in result.get("indirect_points", []):
        expected_uid = compute_uid(ip["file"], ip["func"], ip["line"], ip["expression"])
        assert ip["uid"] == expected_uid, \
            f"{category}/{example}: uid mismatch for {ip['expression']}: {ip['uid']} != {expected_uid}"


def test_uid_deterministic():
    uid1 = compute_uid("file.c", "func", 42, "ops->read")
    uid2 = compute_uid("file.c", "func", 42, "ops->read")
    assert uid1 == uid2
    assert len(uid1) == 8


def test_uid_different_inputs():
    uid1 = compute_uid("file.c", "func", 42, "ops->read")
    uid2 = compute_uid("file.c", "func", 43, "ops->read")
    assert uid1 != uid2
