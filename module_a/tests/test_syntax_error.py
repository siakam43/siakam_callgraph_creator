import json
import logging
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from module_a._call_analyzer import parse_file


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


def test_syntax_error_reports_warning(caplog):
    fixture_path = os.path.join(FIXTURES_DIR, "bad_function", "fixture.c")
    with caplog.at_level(logging.WARNING):
        parse_file(fixture_path)
    # The bad_function fixture has a syntax error → logging.warning called
    # caplog.text contains the formatted log output
    assert len(caplog.records) > 0, "Expected at least one warning log record"
    assert any("syntax error" in r.message.lower() for r in caplog.records), \
        f"Expected 'syntax error' in log messages, got: {[r.message for r in caplog.records]}"
