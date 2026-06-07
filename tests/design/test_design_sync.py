"""Pytest: design sync check (vùng 2 of index.html ↔ EAVM/styling.txt).

Mirrors the CLI in tools/check_design_sync.py. Both share the parser in
tools/_design_sync.py.

Run via:
  pytest tests/design/test_design_sync.py
  pytest tests/  (whole suite)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the project root importable so `tools._design_sync` resolves
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tools._design_sync import (  # noqa: E402
    diff_rules,
    extract_vung2_css,
    load_design_and_styling,
    parse_css,
)


def test_boundary_extraction_finds_card_css():
    """extract_vung2_css must return text between START and END markers,
    not page chrome or page footer."""
    from tools._design_sync import INDEX_HTML

    html = INDEX_HTML.read_text(encoding="utf-8")
    css = extract_vung2_css(html)
    # Card class is present
    assert ".anki-card-container" in css
    # Page chrome classes are excluded
    assert ".wrap" not in css
    assert ".page-header" not in css
    # Page footer (in <style>) is excluded by END marker
    assert "footer a" not in css or "color: #a78bfa" not in css.split("END ANKI CARD STYLES")[0]


def test_preview_only_marker_is_honoured():
    """Rules marked /* @preview-only */ in index.html must NOT be in
    the parsed design rules."""
    from tools._design_sync import INDEX_HTML

    html = INDEX_HTML.read_text(encoding="utf-8")
    css = extract_vung2_css(html)
    design, preview = parse_css(css, skip_preview_only=True)

    # Both known @preview-only selectors must be skipped from rules
    assert ".anki-card-container" not in design
    assert ".card-content-front" not in design
    # But they must be recorded in preview_selectors
    assert ".anki-card-container" in preview
    assert ".card-content-front" in preview


def test_design_and_styling_are_in_sync():
    """Main assertion: vùng 2 of index.html and EAVM/styling.txt
    must agree on every (selector, property, value) tuple outside
    preview-only selectors."""
    design_rules, styling_rules, preview_selectors = load_design_and_styling()
    only_in_design, only_in_styling = diff_rules(
        design_rules, styling_rules, preview_selectors
    )

    # Compose a readable error message for failures
    msgs = []
    if only_in_design:
        msgs.append(
            f"\n{len(only_in_design)} (selector, property, value) only in design/index.html "
            f"(should be added to EAVM/styling.txt):\n"
            + "\n".join(
                f"  {sel}  {{  {prop}: {val};  }}"
                for sel, prop, val in sorted(only_in_design)
            )
        )
    if only_in_styling:
        msgs.append(
            f"\n{len(only_in_styling)} (selector, property, value) only in EAVM/styling.txt "
            f"(drift — not in design):\n"
            + "\n".join(
                f"  {sel}  {{  {prop}: {val};  }}"
                for sel, prop, val in sorted(only_in_styling)
            )
        )
    if msgs:
        if preview_selectors:
            msgs.append(
                f"\nPreview-only selectors skipped (rule-level): {sorted(preview_selectors)}"
            )
        pytest.fail("\n".join(msgs))
