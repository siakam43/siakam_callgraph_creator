#!/usr/bin/env python3
"""Entry script for siakam_callgraph_creator — C-language call graph analysis toolkit."""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="start.py",
        description="siakam_callgraph_creator — C-language call graph analysis toolkit",
    )
    sub = parser.add_subparsers(dest="command", metavar="command")

    # analyze (Module A)
    p_analyze = sub.add_parser("analyze", help="Run Module A: static analysis (nodes, edges, indirect points)")
    p_analyze.add_argument("project_dir", help="Path to the C project directory")
    p_analyze.add_argument("output_dir", nargs="?", default=None,
                           help="Output directory (default: <project_dir>/.siakam_out)")

    # merge (Module C)
    p_merge = sub.add_parser("merge", help="Run Module C: merge call graph, find entries, generate DOT & JSON")
    p_merge.add_argument("project_dir", help="Path to the C project directory")
    p_merge.add_argument("output_dir", nargs="?", default=None,
                         help="Output directory (default: <project_dir>/.siakam_out)")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "analyze":
        from module_a.analyzer import run_analysis
        output_dir = args.output_dir or f"{args.project_dir}/.siakam_out"
        result = run_analysis(args.project_dir, output_dir)
        print(f"Module A complete: {len(result.get('functions', []))} functions, "
              f"{len(result.get('edges', []))} direct edges, "
              f"{len(result.get('indirect_points', []))} indirect points")

    elif args.command == "merge":
        from module_c.entry_finder import run_module_c
        output_dir = args.output_dir or f"{args.project_dir}/.siakam_out"
        result = run_module_c(args.project_dir, output_dir)
        if result.get("callgraph"):
            nodes = len(result["callgraph"].get("nodes", []))
            edges = len(result["callgraph"].get("edges", []))
            entries = len(result.get("entries", []))
            print(f"Module C complete: {nodes} nodes, {edges} edges, {entries} entry functions")
        else:
            print("Module C complete")


if __name__ == "__main__":
    main()
