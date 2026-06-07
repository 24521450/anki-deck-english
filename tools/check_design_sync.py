"""CLI: check that design/index.html vùng 2 card CSS is in sync with
design/EAVM/styling.txt (which is baked into the .apkg).

Exits 0 if synced, 1 if drift detected.

Usage:
  python -m tools.check_design_sync
"""

from __future__ import annotations

import sys

from tools._design_sync import diff_rules, load_design_and_styling


def main() -> int:
    try:
        design_rules, styling_rules, preview_selectors = load_design_and_styling()
    except (FileNotFoundError, ValueError) as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        return 2

    only_in_design, only_in_styling = diff_rules(design_rules, styling_rules, preview_selectors)

    n_design = sum(len(p) for p in design_rules.values())
    n_styling = sum(len(p) for p in styling_rules.values())
    n_preview = len(preview_selectors)

    if not only_in_design and not only_in_styling:
        print(
            f"[OK] design/index.html vùng 2 ↔ EAVM/styling.txt in sync "
            f"({n_design} properties, {len(design_rules)} selectors; "
            f"{n_preview} preview-only skipped)"
        )
        return 0

    print(
        f"[DRIFT] {n_design} properties in design, {n_styling} in styling. "
        f"Only-in-design: {len(only_in_design)}, only-in-styling: {len(only_in_styling)} "
        f"({n_preview} preview-only selectors skipped)"
    )

    if preview_selectors:
        print(f"\nSkipped preview-only selectors: {sorted(preview_selectors)}")

    if only_in_design:
        print("\n--- Only in design/index.html (need to be added to EAVM/styling.txt) ---")
        for sel, prop, val in sorted(only_in_design):
            print(f"  {sel}  {{  {prop}: {val};  }}")

    if only_in_styling:
        print("\n--- Only in EAVM/styling.txt (drift — not in design) ---")
        for sel, prop, val in sorted(only_in_styling):
            print(f"  {sel}  {{  {prop}: {val};  }}")

    return 1


if __name__ == "__main__":
    sys.exit(main())
