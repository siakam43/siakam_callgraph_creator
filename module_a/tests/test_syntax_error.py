import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from module_a.c_parser import parse_file


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "syntax_error")


def test_syntax_error_skips_bad_function():
    fixture_path = os.path.join(FIXTURES_DIR, "bad_function", "fixture.c")
    truth_path = os.path.join(FIXTURES_DIR, "bad_function", "ground_truth_nodes.json")

    result = parse_file(fixture_path)

    with open(truth_path) as f:
        expected = json.load(f)

    result_names = {fn["name"] for fn in result.get("functions", [])}
    expected_names = {fn["name"] for fn in expected["functions"]}
    assert result_names == expected_names, \
        f"Extra: {result_names - expected_names}\nMissing: {expected_names - result_names}"


def test_syntax_error_reports_warning(capsys):
    fixture_path = os.path.join(FIXTURES_DIR, "bad_function", "fixture.c")
    parse_file(fixture_path)
    captured = capsys.readouterr()
    output = (captured.err + captured.out).lower()
    assert "error" in output or "syntax" in output, \
        f"Expected error/syntax warning, got: {captured.err}{captured.out}"
