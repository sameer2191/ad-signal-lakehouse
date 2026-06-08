"""Command line interface for the local lakehouse simulator."""

from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from .lakehouse import run_demo


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ad_signal_lakehouse",
        description="Local marketing analytics lakehouse simulator.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("demo", help="Generate events and build bronze/silver/gold artifacts.")
    demo.add_argument("--output", default="runs/demo", help="Output directory for generated artifacts.")
    demo.add_argument("--events", type=int, default=5000, help="Number of synthetic ad events to generate.")
    demo.add_argument("--seed", type=int, default=42, help="Deterministic generator seed.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "demo":
        if args.events < 1:
            parser.error("--events must be greater than zero")
        result = run_demo(Path(args.output), events=args.events, seed=args.seed)
        print("Ad Signal Lakehouse demo complete")
        print(f"  status: {result.status}")
        print(f"  output: {result.output_dir}")
        print(f"  bronze: {result.bronze_file}")
        print(f"  sqlite: {result.database_path}")
        print(f"  health: {result.health_report_path}")
        print(f"  dashboard: {result.dashboard_path}")
        print(
            "  counts: "
            f"bronze={result.counts['bronze_events']}, "
            f"silver={result.counts['silver_events']}, "
            f"rejected={result.counts['rejected_events']}, "
            f"duplicates={result.counts['duplicate_events']}, "
            f"late={result.counts['late_events']}"
        )
        return 0 if result.status == "pass" else 2

    parser.error(f"unknown command: {args.command}")
    return 2
