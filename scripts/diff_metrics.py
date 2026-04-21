"""Diff two build_*_metrics.json files and highlight regressions.

Usage:
    python scripts/diff_metrics.py <before.json> <after.json>

Reports any numeric metric whose value changed, plus newly added or removed
keys. Exit code 0 if the two files agree on all scalar values.
"""

import argparse
import json
import sys
from pathlib import Path


def _flatten(d, prefix=""):
    """Flatten a nested dict of numeric values into {dotted_key: value}."""
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}" if not prefix else f"{prefix}.{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, key))
        elif isinstance(v, (int, float)):
            out[key] = v
    return out


def diff(before_path, after_path):
    before = json.loads(Path(before_path).read_text())
    after = json.loads(Path(after_path).read_text())

    b = _flatten(before)
    a = _flatten(after)

    all_keys = sorted(set(b) | set(a))
    changes = []
    for k in all_keys:
        bv = b.get(k)
        av = a.get(k)
        if bv == av:
            continue
        if bv is None:
            changes.append((k, None, av, "ADDED"))
        elif av is None:
            changes.append((k, bv, None, "REMOVED"))
        else:
            delta = av - bv
            changes.append((k, bv, av, f"Δ={delta:+}"))

    if not changes:
        print("No differences.")
        return 0

    # Sort by absolute magnitude of change for readability
    def _mag(c):
        _, bv, av, _ = c
        if bv is None or av is None:
            return float("inf")
        return abs(av - bv)

    changes.sort(key=_mag, reverse=True)

    print(f"Comparing:\n  before = {before_path}\n  after  = {after_path}\n")
    print(f"{'KEY':<60} {'BEFORE':>10} {'AFTER':>10}  CHANGE")
    print("-" * 95)
    for k, bv, av, desc in changes:
        bvs = f"{bv:,}" if isinstance(bv, (int, float)) else "-"
        avs = f"{av:,}" if isinstance(av, (int, float)) else "-"
        print(f"{k:<60} {bvs:>10} {avs:>10}  {desc}")
    print()
    print(f"{len(changes):,} metric(s) changed.")
    return 1


def main():
    parser = argparse.ArgumentParser(
        description="Diff two build metrics JSON files and highlight changes."
    )
    parser.add_argument("before", help="Path to the earlier metrics JSON")
    parser.add_argument("after", help="Path to the later metrics JSON")
    args = parser.parse_args()
    sys.exit(diff(args.before, args.after))


if __name__ == "__main__":
    main()
