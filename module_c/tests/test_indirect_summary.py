import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from module_c.entry_finder import build_indirect_summary


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def test_summary_counts():
    summary = build_indirect_summary(
        os.path.join(FIXTURES_DIR, "indirect_points.json"),
        os.path.join(FIXTURES_DIR, "indirect"),
    )
    assert summary["total"] == 3
    assert summary["completed"] == 2
    assert summary["failed"] == 1


def test_completed_with_targets():
    summary = build_indirect_summary(
        os.path.join(FIXTURES_DIR, "indirect_points.json"),
        os.path.join(FIXTURES_DIR, "indirect"),
    )
    call = next(c for c in summary["calls"] if c["uid"] == "aaaaaaaa")
    assert len(call["targets"]) == 2
    assert call["targets"][0]["callee"] == "helper_a"
    assert call["targets"][0]["confidence"] == "high"


def test_completed_empty_targets():
    summary = build_indirect_summary(
        os.path.join(FIXTURES_DIR, "indirect_points.json"),
        os.path.join(FIXTURES_DIR, "indirect"),
    )
    call = next(c for c in summary["calls"] if c["uid"] == "bbbbbbbb")
    assert call["targets"] == []
    assert "error" not in call


def test_failed_call_has_error():
    summary = build_indirect_summary(
        os.path.join(FIXTURES_DIR, "indirect_points.json"),
        os.path.join(FIXTURES_DIR, "indirect"),
    )
    call = next(c for c in summary["calls"] if c["uid"] == "cccccccc")
    assert call["targets"] == []
    assert "error" in call
    assert "Could not trace" in call["error"]


def test_missing_indirect_file():
    summary = build_indirect_summary(
        os.path.join(FIXTURES_DIR, "indirect_points.json"),
        "/nonexistent/indirect/dir",
    )
    assert summary["failed"] == 3
    assert summary["completed"] == 0
    for call in summary["calls"]:
        assert "error" in call
