"""Command line interface for closed local migration artifacts."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .core import InputError, audit, read_text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit a redirect CSV against old and live path catalogs."
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("plan", help="CSV with source,target,status header")
    parser.add_argument("--old", required=True, help="old path inventory")
    parser.add_argument("--live", required=True, help="new live path inventory")
    parser.add_argument("--max-hops", type=int, default=1)
    parser.add_argument("--sample-limit", type=int, default=100)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = audit(
            read_text(args.plan),
            read_text(args.old),
            read_text(args.live),
            max_hops=args.max_hops,
            sample_limit=args.sample_limit,
        )
    except (InputError, OSError, UnicodeError) as exc:
        error = str(exc) if isinstance(exc, InputError) else "cannot read input file"
        print(json.dumps({"error": error}, ensure_ascii=True), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True))
    else:
        print("PASS" if report["passed"] else "FAIL")
        print(json.dumps(report["summary"], sort_keys=True, ensure_ascii=True))
        for finding in report["findings"]:
            print(json.dumps(finding, sort_keys=True, ensure_ascii=True))
        if report["truncated"]:
            print("Finding samples truncated; summary counts include every checked path.")
    return 0 if report["passed"] else 1
