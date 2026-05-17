"""Tests for analyzer.py — project-level two-phase pipeline."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from module_a.analyzer import run_analysis


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "cross_file")


class TestCrossFileExample3:
    """example_3_both: typedef in types.h + macro in api.h, both used in main.c"""

    def test_finds_functions_from_main_c(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_analysis(
                os.path.join(FIXTURES, "example_3_both"), tmpdir)
            names = {f["name"] for f in result["functions"]}
            assert "send_notification" in names
            assert "run" in names

    def test_macro_expansion_from_api_header(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_analysis(
                os.path.join(FIXTURES, "example_3_both"), tmpdir)
            edges = {(e["caller"], e["callee"]) for e in result["edges"]}
            # DISPATCH() in main.c expands to send_notification via api.h macro
            assert ("run", "send_notification") in edges

    def test_cross_file_typedef_detects_fnptr(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_analysis(
                os.path.join(FIXTURES, "example_3_both"), tmpdir)
            ips = {(ip["func"], ip["expression"]) for ip in result["indirect_points"]}
            # handler is declared as notify_t (cross-file typedef from types.h)
            assert ("run", "handler") in ips

    def test_writes_output_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_analysis(os.path.join(FIXTURES, "example_3_both"), tmpdir)
            for fname in ["nodes.json", "edges.json", "indirect_points.json"]:
                assert os.path.isfile(os.path.join(tmpdir, fname))


class TestCrossFileExample1:
    """example_1_typedef: typedef in types.h → fnptr detection in main.c"""

    def test_cross_file_fnptr_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_analysis(
                os.path.join(FIXTURES, "example_1_typedef"), tmpdir)
            ips = {(ip["func"], ip["file"], ip["expression"])
                   for ip in result["indirect_points"]}
            assert ("init", "main.c", "handler") in ips


class TestCrossFileExample2:
    """example_2_macro: macro in api.h → expansion in main.c"""

    def test_cross_file_macro_expansion(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_analysis(
                os.path.join(FIXTURES, "example_2_macro"), tmpdir)
            edges = {(e["caller"], e["callee"]) for e in result["edges"]}
            # CALL_API("run") in main.c → do_api_call via api.h macro
            assert ("run", "do_api_call") in edges

    def test_output_matches_ground_truth(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_analysis(
                os.path.join(FIXTURES, "example_2_macro"), tmpdir)
            truth_path = os.path.join(FIXTURES, "example_2_macro",
                                       "ground_truth_edges.json")
            with open(truth_path) as f:
                expected = json.load(f)
            result_edges = {(e["caller"], e["callee"], e["line"])
                            for e in result["edges"]}
            expected_edges = {(e["caller"], e["callee"], e["line"])
                              for e in expected["edges"]}
            assert result_edges == expected_edges
