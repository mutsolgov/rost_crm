"""Adversarial Oracle: CSS Cascade Evaluation & Computed Styles Verification.

Empirically simulates the CSS cascade and computed style resolution
according to W3C Cascading and Inheritance Level 4 specification.
Verifies computed property outcomes across viewport widths:
- Mobile (< 768px: 360, 375, 390, 414, 767px)
- Tablet (768px - 1023px)
- Desktop (1024px - 1439px)
- Wide screen (>= 1440px)
"""
import re
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
STYLES_CSS = ROOT / "frontend" / "src" / "styles.css"


class CSSRule:
    def __init__(self, selector: str, properties: dict[str, str], media_query: str | None, source_order: int):
        self.selector = selector.strip()
        self.properties = properties
        self.media_query = media_query
        self.source_order = source_order

    def applies_to_width(self, width: int) -> bool:
        if self.media_query is None:
            return True
        mq = self.media_query
        if "max-width: 767px" in mq:
            return width <= 767
        if "min-width: 768px" in mq and "max-width: 1023px" in mq:
            return 768 <= width <= 1023
        if "min-width: 1440px" in mq:
            return width >= 1440
        return True


def parse_css_rules(css_text: str) -> list[CSSRule]:
    """Parse CSS into structured CSSRule objects respecting media query blocks and source order."""
    # Remove CSS comments
    cleaned = re.sub(r"/\*.*?\*/", "", css_text, flags=re.DOTALL)

    rules: list[CSSRule] = []
    order = 0

    # Tokenize by top-level blocks
    pos = 0
    current_media: str | None = None

    while pos < len(cleaned):
        # Check for @media
        media_match = re.compile(r"\s*@media\s*([^{]+)\{").search(cleaned, pos)
        # Look for normal selector before media or next selector
        rule_match = re.compile(r"([^{}]+)\{([^}]+)\}").search(cleaned, pos)

        if media_match and (not rule_match or media_match.start() <= rule_match.start()):
            media_cond = media_match.group(1).strip()
            # find matching closing brace for this media block
            brace_start = media_match.end() - 1
            depth = 1
            idx = brace_start + 1
            while idx < len(cleaned) and depth > 0:
                if cleaned[idx] == "{":
                    depth += 1
                elif cleaned[idx] == "}":
                    depth -= 1
                idx += 1
            media_content = cleaned[brace_start + 1 : idx - 1]
            # parse rules inside media block
            sub_pos = 0
            while sub_pos < len(media_content):
                sub_match = re.compile(r"([^{}]+)\{([^}]+)\}").search(media_content, sub_pos)
                if not sub_match:
                    break
                sel = sub_match.group(1).strip()
                decls_raw = sub_match.group(2).strip()
                decls: dict[str, str] = {}
                for decl in decls_raw.split(";"):
                    if ":" in decl:
                        prop, val = decl.split(":", 1)
                        decls[prop.strip()] = val.strip()
                order += 1
                rules.append(CSSRule(sel, decls, media_cond, order))
                sub_pos = sub_match.end()

            pos = idx
        elif rule_match:
            sel = rule_match.group(1).strip()
            decls_raw = rule_match.group(2).strip()
            decls = {}
            for decl in decls_raw.split(";"):
                if ":" in decl:
                    prop, val = decl.split(":", 1)
                    decls[prop.strip()] = val.strip()
            order += 1
            rules.append(CSSRule(sel, decls, None, order))
            pos = rule_match.end()
        else:
            break

    return rules


def compute_style(rules: list[CSSRule], target_selector: str, property_name: str, width: int) -> str | None:
    """Compute the effective property value according to CSS cascade rules (matching selector, media query, source order)."""
    winning_value: str | None = None
    winning_order = -1

    for rule in rules:
        # Check if target_selector matches selector list
        selectors = [s.strip() for s in rule.selector.split(",")]
        if target_selector in selectors:
            if rule.applies_to_width(width) and property_name in rule.properties:
                if rule.source_order > winning_order:
                    winning_order = rule.source_order
                    winning_value = rule.properties[property_name]

    return winning_value


@pytest.fixture(scope="module")
def parsed_css():
    assert STYLES_CSS.is_file(), f"styles.css not found at {STYLES_CSS}"
    content = STYLES_CSS.read_text(encoding="utf-8")
    return parse_css_rules(content)


@pytest.mark.parametrize("width", [360, 375, 390, 414, 767])
def test_mobile_workflow_scroll_hint_computed_style(parsed_css, width):
    """Under mobile viewport (< 768px), .workflow-scroll-hint MUST compute to display: flex."""
    computed_display = compute_style(parsed_css, ".workflow-scroll-hint", "display", width)
    assert computed_display == "flex", (
        f"At width {width}px, .workflow-scroll-hint computed display='{computed_display}', expected 'flex'!"
    )


@pytest.mark.parametrize("width", [768, 1024, 1440, 1920])
def test_desktop_workflow_scroll_hint_computed_style(parsed_css, width):
    """Under tablet and desktop viewports (>= 768px), .workflow-scroll-hint MUST compute to display: none."""
    computed_display = compute_style(parsed_css, ".workflow-scroll-hint", "display", width)
    assert computed_display == "none", (
        f"At width {width}px, .workflow-scroll-hint computed display='{computed_display}', expected 'none'!"
    )


@pytest.mark.parametrize("width", [360, 375, 390, 414, 767])
def test_mobile_column_selector_list_computed_style(parsed_css, width):
    """Under mobile viewport (< 768px), .column-selector-list MUST compute to grid with 1fr."""
    computed_display = compute_style(parsed_css, ".column-selector-list", "display", width)
    computed_cols = compute_style(parsed_css, ".column-selector-list", "grid-template-columns", width)

    assert computed_display == "grid", (
        f"At width {width}px, .column-selector-list computed display='{computed_display}', expected 'grid'!"
    )
    assert computed_cols == "1fr", (
        f"At width {width}px, .column-selector-list computed grid-template-columns='{computed_cols}', expected '1fr'!"
    )


@pytest.mark.parametrize("width", [768, 1024, 1440])
def test_desktop_column_selector_list_computed_style(parsed_css, width):
    """Under desktop viewport (>= 768px), .column-selector-list MUST compute to flex."""
    computed_display = compute_style(parsed_css, ".column-selector-list", "display", width)
    computed_wrap = compute_style(parsed_css, ".column-selector-list", "flex-wrap", width)

    assert computed_display == "flex", (
        f"At width {width}px, .column-selector-list computed display='{computed_display}', expected 'flex'!"
    )
    assert computed_wrap == "wrap", (
        f"At width {width}px, .column-selector-list computed flex-wrap='{computed_wrap}', expected 'wrap'!"
    )


@pytest.mark.parametrize("width", [360, 375, 390, 414, 767])
def test_mobile_touch_targets_computed_heights(parsed_css, width):
    """All mobile interactive targets must have min-height >= 44px computed."""
    button_min_h = compute_style(parsed_css, ".button", "min-height", width)
    assert button_min_h == "44px", f"At width {width}px, .button min-height='{button_min_h}', expected '44px'"

    icon_btn_min_h = compute_style(parsed_css, ".icon-button", "min-height", width)
    icon_btn_min_w = compute_style(parsed_css, ".icon-button", "min-width", width)
    assert icon_btn_min_h == "44px", f"At width {width}px, .icon-button min-height='{icon_btn_min_h}', expected '44px'"
    assert icon_btn_min_w == "44px", f"At width {width}px, .icon-button min-width='{icon_btn_min_w}', expected '44px'"

    checkbox_min_h = compute_style(parsed_css, ".column-checkbox-item", "min-height", width)
    assert checkbox_min_h == "44px", (
        f"At width {width}px, .column-checkbox-item min-height='{checkbox_min_h}', expected '44px'"
    )


def test_no_base_rules_after_media_queries(parsed_css):
    """Structural invariant: No unconditional (non-media-query) rule can appear after media queries."""
    first_media_order = None
    for rule in parsed_css:
        if rule.media_query is not None and first_media_order is None:
            first_media_order = rule.source_order

    assert first_media_order is not None, "No media queries found in stylesheet"

    violating_rules = [
        rule for rule in parsed_css
        if rule.media_query is None and rule.source_order > first_media_order
    ]

    assert len(violating_rules) == 0, (
        f"Found {len(violating_rules)} base component rules declared AFTER media queries: "
        f"{[r.selector for r in violating_rules[:5]]}. This causes cascade inversions!"
    )
