"""Command line entry point.

    p6check data/*.xer                 # check files, print a summary
    p6check data/*.xer --out reports   # also write HTML, PNG and JSON per file
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .checks import run_checks, DEFAULT_HIGH_FLOAT_DAYS
from .chart import float_histogram
from .parser import read_xer, XerFormatError
from .report import terminal_summary, write_html, write_json


def positive_float(text: str) -> float:
    value = float(text)
    if not (value > 0 and value != float("inf")):
        raise argparse.ArgumentTypeError(f"must be a positive number, got {text!r}")
    return value


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="p6check", description="Check Primavera P6 .xer schedule files.")
    ap.add_argument("files", nargs="+", type=Path, help=".xer files to check")
    ap.add_argument("--out", type=Path, default=None, help="directory for HTML/PNG/JSON reports (created if missing)")
    ap.add_argument(
        "--high-float-days",
        type=positive_float,
        default=DEFAULT_HIGH_FLOAT_DAYS,
        help=f"flag activities whose total float exceeds this many working days (default {DEFAULT_HIGH_FLOAT_DAYS:g})",
    )
    args = ap.parse_args(argv)

    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)

    failures = 0
    for path in args.files:
        try:
            xer = read_xer(path)
        except (XerFormatError, OSError) as exc:
            print(f"{path.name}: cannot read file: {exc}", file=sys.stderr)
            failures += 1
            continue
        result = run_checks(xer, high_float_days=args.high_float_days)
        print(terminal_summary(xer, result))
        if args.out:
            stem = path.stem
            png = float_histogram(result)
            (args.out / f"{stem}.png").write_bytes(png)
            write_html(xer, result, args.out / f"{stem}.html", png=png)
            write_json(xer, result, args.out / f"{stem}.json")
            print(f"  reports: {args.out / stem}.html  .png  .json")
        print()
    return 1 if failures else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
