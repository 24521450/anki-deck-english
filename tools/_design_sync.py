"""Shared parser for design-sync check.

Extracts CSS rules from:
  - `design/index.html` vùng 2 (card-CSS section after the boundary comment)
  - `design/EAVM/styling.txt`

Returns (rules, preview_selectors) where:
  - rules: dict of {selector: {property: value}}
  - preview_selectors: set of selector names marked /* @preview-only */ in index.html

Rules in index.html preceded by `/* @preview-only */` are skipped
(rule-level marker — entire rule is preview-only, not synced to .apkg).

Property-pair level: compares set of (selector, property, value) tuples
ignoring order of selectors, properties, and formatting whitespace.
"""

import re
from pathlib import Path

# Boundary marker comments in index.html.
# Card CSS is the section between PREVIEW_BOUNDARY_START and PREVIEW_BOUNDARY_END.
PREVIEW_BOUNDARY_START = "ANKI CARD STYLES — must match EAVM/styling.txt exactly"
PREVIEW_BOUNDARY_END = "END ANKI CARD STYLES"

# Marker for preview-only rules (rule-level). The marker must be on its own
# line, immediately before the rule it should skip.
PREVIEW_ONLY_MARKER = "@preview-only"

# Sentinel used internally during parsing to mark preview-only rules.
_PREVIEW_SENTINEL = "__PREVIEW_ONLY_SENTINEL__"

# Standard CSS comment regex (handles multi-line, nested-ish via alternation)
_CSS_COMMENT_RE = re.compile(
    r"/\*[^*]*\*+(?:[^/*][^*]*\*+)*/",
    re.DOTALL,
)

# @preview-only comment regex — matches /* @preview-only ... */
_PREVIEW_ONLY_RE = re.compile(
    r"/\*\s*" + re.escape(PREVIEW_ONLY_MARKER) + r"[^*]*\*+(?:[^/*][^*]*\*+)*/",
    re.DOTALL,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = REPO_ROOT / "design" / "index.html"
STYLING_TXT = REPO_ROOT / "design" / "EAVM" / "styling.txt"


def extract_vung2_css(html_text: str) -> str:
    """Pull out the card-CSS section from index.html (between START and END markers)."""
    start_idx = html_text.find(PREVIEW_BOUNDARY_START)
    if start_idx == -1:
        raise ValueError(
            f"Could not find START boundary marker in index.html. "
            f"Expected comment containing: {PREVIEW_BOUNDARY_START!r}"
        )
    start_comment_end = html_text.find("*/", start_idx)
    if start_comment_end == -1:
        raise ValueError("START boundary comment in index.html is not closed with */")
    css_start = start_comment_end + 2

    end_idx = html_text.find(PREVIEW_BOUNDARY_END, css_start)
    if end_idx == -1:
        raise ValueError(
            f"Could not find END boundary marker in index.html. "
            f"Expected comment containing: {PREVIEW_BOUNDARY_END!r}"
        )
    # Back up to the start of the /* comment containing the END marker
    end_comment_start = html_text.rfind("/*", css_start, end_idx)
    if end_comment_start == -1:
        # END marker is in a non-/* context — just slice to end_idx
        return html_text[css_start:end_idx]
    return html_text[css_start:end_comment_start]


def _parse_declarations(body: str) -> dict[str, str]:
    """Parse CSS declaration block into {property: value}.

    Whitespace inside values is collapsed. Property names are lowercased.
    """
    props: dict[str, str] = {}
    for decl in body.split(";"):
        decl = decl.strip()
        if not decl or ":" not in decl:
            continue
        prop, _, value = decl.partition(":")
        prop = prop.strip().lower()
        value = re.sub(r"\s+", " ", value.strip())
        if prop:
            props[prop] = value
    return props


def _find_matching_brace(text: str, open_pos: int) -> int:
    """Find position of `}` matching the `{` at open_pos. Counts nested braces.

    Returns -1 if no matching `}` is found.
    """
    depth = 1
    i = open_pos + 1
    n = len(text)
    while i < n:
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def parse_css(
    css_text: str,
    skip_preview_only: bool = True,
) -> tuple[dict[str, dict[str, str]], set[str]]:
    """Parse CSS into ({selector: {property: value}}, preview_selectors).

    Skips @-rules (@import, @keyframes, @media, etc.) entirely.
    Skips /* @preview-only */-marked rules when skip_preview_only is True
    (rule-level marker — entire rule omitted; selector still recorded in
    preview_selectors for downstream filtering).
    """
    # Replace @preview-only comments with a sentinel attached to the next selector.
    marked = _PREVIEW_ONLY_RE.sub(_PREVIEW_SENTINEL + " ", css_text)
    # Strip remaining CSS comments.
    cleaned = _CSS_COMMENT_RE.sub("", marked)

    rules: dict[str, dict[str, str]] = {}
    preview_selectors: set[str] = set()

    i = 0
    n = len(cleaned)
    while i < n:
        # Find next `{` — selector is everything between current i and that brace.
        brace = cleaned.find("{", i)
        if brace == -1:
            break
        # Find matching `}` by counting nested braces (handles @keyframes, @media).
        close = _find_matching_brace(cleaned, brace)
        if close == -1:
            break

        raw_selector = cleaned[i:brace]
        # Strip statement-style @-rules (@import, @charset) that have no braces
        # and would otherwise pollute the selector. The @-rule body may contain
        # quoted strings (e.g. url('...;...;...');), so we honour quotes.
        raw_selector = re.sub(
            r'@(?:[^;{"\']*|"[^"]*"|\'[^\']*\')*;',
            "",
            raw_selector,
        ).strip()
        body = cleaned[brace + 1 : close].strip()
        i = close + 1

        # Skip @-rules (@import, @keyframes, @media, @charset, etc.)
        if raw_selector.startswith("@"):
            continue

        # Detect @preview-only marker.
        is_preview = raw_selector.startswith(_PREVIEW_SENTINEL)
        if is_preview:
            raw_selector = raw_selector[len(_PREVIEW_SENTINEL) :].strip()

        if skip_preview_only and is_preview:
            # Record selector as preview-only for downstream filtering, but don't add to rules.
            for sel in [s.strip() for s in raw_selector.split(",") if s.strip()]:
                preview_selectors.add(sel)
            continue

        if not raw_selector or not body:
            continue

        props = _parse_declarations(body)
        if not props:
            continue

        for sel in [s.strip() for s in raw_selector.split(",") if s.strip()]:
            existing = rules.get(sel, {})
            existing.update(props)
            rules[sel] = existing

    return rules, preview_selectors


def _expand_pairs(rules: dict[str, dict[str, str]]) -> set[tuple[str, str, str]]:
    """Flatten rules into set of (selector, property, value) tuples."""
    pairs: set[tuple[str, str, str]] = set()
    for selector, props in rules.items():
        for prop, value in props.items():
            pairs.add((selector.strip(), prop, value))
    return pairs


def diff_rules(
    design_rules: dict[str, dict[str, str]],
    styling_rules: dict[str, dict[str, str]],
    preview_selectors: set[str] | None = None,
) -> tuple[set[tuple[str, str, str]], set[tuple[str, str, str]]]:
    """Compare two parsed rule dicts. Return (only_in_design, only_in_styling).

    Selectors in preview_selectors are excluded from BOTH sides — they're
    intentionally preview-only and shouldn't be enforced as drift.
    """
    if preview_selectors is None:
        preview_selectors = set()

    filtered_design = {s: p for s, p in design_rules.items() if s not in preview_selectors}
    filtered_styling = {s: p for s, p in styling_rules.items() if s not in preview_selectors}

    design_pairs = _expand_pairs(filtered_design)
    styling_pairs = _expand_pairs(filtered_styling)
    return design_pairs - styling_pairs, styling_pairs - design_pairs


def load_design_and_styling() -> tuple[
    dict[str, dict[str, str]],
    dict[str, dict[str, str]],
    set[str],
]:
    """Load and parse both files. Returns (design_rules, styling_rules, preview_selectors)."""
    html_text = INDEX_HTML.read_text(encoding="utf-8")
    styling_text = STYLING_TXT.read_text(encoding="utf-8")
    css = extract_vung2_css(html_text)
    design, preview = parse_css(css, skip_preview_only=True)
    styling, _ = parse_css(styling_text, skip_preview_only=False)
    return design, styling, preview
