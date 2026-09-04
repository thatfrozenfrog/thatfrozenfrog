#!/usr/bin/env python3
"""Update 4chan post datetimes in README.md to current runtime.

Usage:
  python3 scripts/update_datetime.py [--readme PATH]
"""
import argparse
import os
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
if DIR not in sys.path:
    sys.path.insert(0, DIR)

from generate_stats import update_readme_datetimes


def main():
    default_readme = os.path.join(os.path.dirname(DIR), "README.md")
    parser = argparse.ArgumentParser(description="Update post datetimes in README.md.")
    parser.add_argument("--readme", default=default_readme, help="Path to README.md")
    args = parser.parse_args()

    if not os.path.exists(args.readme):
        print(f"Error: {args.readme} not found", file=sys.stderr)
        sys.exit(1)

    updated = update_readme_datetimes(args.readme)
    if updated:
        print(f"Successfully updated timestamps in {args.readme} to current runtime.")
    else:
        print(f"Timestamps in {args.readme} are already up to date.")


if __name__ == "__main__":
    main()
