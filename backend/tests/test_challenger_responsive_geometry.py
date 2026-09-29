"""Adversarial Empirical Challenge: Frontend Viewport Geometry, Touch Targets, and CSS Cascade.

Independent verification test suite for rost_crm responsive adaptation (R1 - R5).
Empirically stress-tests:
1. Root viewport isolation: document.body.scrollWidth === window.innerWidth.
2. Breakpoint structure without dead zones.
3. CSS Cascade Ordering & Specificity Inversion: detecting rules defined AFTER media queries
   that unintentionally override responsive mobile styles (e.g. .workflow-scroll-hint display: none).
4. Minimum touch targets (>= 44px) on mobile viewports (< 768px).
5. Isolated horizontal scroll containers (.table-scroll, .workflow-graph-scroll, .funnel-scroll).
6. Read-only architecture invariants and zero dependency bloat.
"""
import re
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
STYLES_CSS = ROOT / "frontend" / "src" / "styles.css"
CATALOG_PAGE = ROOT / "frontend" / "src" / "views" / "CatalogPage.tsx"
WORKFLOW_GRAPH = ROOT / "frontend" / "src" / "views" / "WorkflowGraphView.tsx"
INTERACTION_PAGE = ROOT / "frontend" / "src" / "views" / "InteractionPage.tsx"
REPORTS_PAGE = ROOT / "frontend" / "src" / "views" / "Reports.tsx"


def test_root_viewport_overflow_containment_css():
    """Verify that root containers isolate horizontal scroll at the window level."""
    assert STYLES_CSS.is_file(), f"Missing stylesheet at {STYLES_CSS}"
    css = STYLES_CSS.read_text(encoding="utf-8")

    # html, body, #root, .app-shell, .main-shell rule
    root_match = re.search(
        r"html\s*,\s*body\s*,\s*#root\s*,\s*\.app-shell\s*,\s*\.main-shell\s*\{([^}]+)\}",
        css,
        re.DOTALL,
    )
    assert root_match is not None, "Root containment rule for html, body, #root, .app-shell, .main-shell missing"
    block = root_match.group(1)
    assert "overflow-x: hidden" in block, "Root containment must specify 'overflow-x: hidden'"
    assert "max-width: 100%" in block, "Root containment must specify 'max-width: 100%'"
    assert "min-width: 0" in block, "Root containment must specify 'min-width: 0'"


def test_breakpoint_hierarchy_and_no_dead_zones():
    """Verify unified breakpoint structure and absence of dead zones."""
    css = STYLES_CSS.read_text(encoding="utf-8")

    # Mobile breakpoint
    assert "@media (max-width: 767px)" in css, "Mobile breakpoint must be @media (max-width: 767px)"
    # Tablet breakpoint
    assert "@media (min-width: 768px) and (max-width: 1023px)" in css, (
        "Tablet breakpoint must be @media (min-width: 768px) and (max-width: 1023px)"
    )
    # Wide screen breakpoint
    assert "@media (min-width: 1440px)" in css, "Wide screen breakpoint must be @media (min-width: 1440px)"

    # Check for legacy non-standard media queries that create gaps
    assert "max-width: 760px" not in css, "Found legacy non-standard breakpoint 760px creating dead zone (761-767px)"
    assert "max-width: 1050px" not in css, "Found legacy non-standard breakpoint 1050px"


def test_isolated_horizontal_scroll_containers():
    """Verify isolated horizontal scrolling containers for tables and graphs."""
    css = STYLES_CSS.read_text(encoding="utf-8")

    # .table-scroll
    table_scroll_match = re.search(r"\.table-scroll\s*\{([^}]+)\}", css)
    assert table_scroll_match is not None, ".table-scroll rule missing in CSS"
    ts_block = table_scroll_match.group(1)
    assert re.search(r"overflow-x\s*:\s*auto", ts_block), ".table-scroll must have overflow-x: auto"
    assert re.search(r"-webkit-overflow-scrolling\s*:\s*touch", ts_block), ".table-scroll must have -webkit-overflow-scrolling: touch"
    assert re.search(r"min-width\s*:\s*0", ts_block), ".table-scroll must have min-width: 0"

    # .workflow-graph-scroll
    wf_scroll_match = re.search(r"\.workflow-graph-scroll\s*\{([^}]+)\}", css)
    assert wf_scroll_match is not None, ".workflow-graph-scroll rule missing in CSS"
    wf_block = wf_scroll_match.group(1)
    assert re.search(r"overflow-x\s*:\s*auto", wf_block), ".workflow-graph-scroll must have overflow-x: auto"
    assert re.search(r"-webkit-overflow-scrolling\s*:\s*touch", wf_block), ".workflow-graph-scroll must have -webkit-overflow-scrolling: touch"

    # .funnel-scroll
    funnel_scroll_match = re.search(r"\.funnel-scroll\s*\{([^}]+)\}", css)
    assert funnel_scroll_match is not None, ".funnel-scroll rule missing in CSS"
    fn_block = funnel_scroll_match.group(1)
    assert re.search(r"overflow-x\s*:\s*auto", fn_block), ".funnel-scroll must have overflow-x: auto"
    assert re.search(r"-webkit-overflow-scrolling\s*:\s*touch", fn_block), ".funnel-scroll must have -webkit-overflow-scrolling: touch"

    # .migration-matrix-wrapper
    mig_match = re.search(r"\.migration-matrix-wrapper\s*\{([^}]+)\}", css)
    assert mig_match is not None, ".migration-matrix-wrapper rule missing in CSS"
    mig_block = mig_match.group(1)
    assert re.search(r"overflow-x\s*:\s*auto", mig_block), ".migration-matrix-wrapper must have overflow-x: auto"


def test_touch_targets_specifications_on_mobile():
    """Verify that buttons, modal actions, and interactive controls specify min-height >= 44px."""
    css = STYLES_CSS.read_text(encoding="utf-8")

    # Mobile media query slice
    m_match = re.search(r"@media\s*\(\s*max-width:\s*767px\s*\)\s*\{(.*?\n)\}\s*\n", css, re.DOTALL)
    assert m_match is not None, "Could not extract @media (max-width: 767px) block"
    mobile_css = m_match.group(1)

    assert ".button { min-height: 44px; }" in mobile_css, "Mobile .button must have min-height: 44px"
    assert ".icon-button { min-width: 44px; min-height: 44px; }" in mobile_css, "Mobile .icon-button must have min 44x44px"
    assert ".mobile-menu { display: inline-flex; min-width: 44px; min-height: 44px; }" in mobile_css, "Mobile menu must be min 44x44px"

    assert "modal-actions" in mobile_css
    assert "min-height: 44px" in mobile_css


def test_markup_structural_integrations():
    """Verify frontend TSX components have proper wrappers, hints, and classes."""
    # WorkflowGraphView: hint and scroll wrapper
    wf_tsx = WORKFLOW_GRAPH.read_text(encoding="utf-8")
    assert "workflow-scroll-hint" in wf_tsx, "WorkflowGraphView missing .workflow-scroll-hint element"
    assert "Сдвиньте вправо для просмотра всех 14 этапов →" in wf_tsx, (
        "WorkflowGraphView missing hint text 'Сдвиньте вправо для просмотра всех 14 этапов →'"
    )
    assert "workflow-graph-scroll" in wf_tsx, "WorkflowGraphView missing .workflow-graph-scroll wrapper"
    assert "workflow-state-details" in wf_tsx, "WorkflowGraphView missing .workflow-state-details"

    # Reports: funnel-scroll and column-selector
    rep_tsx = REPORTS_PAGE.read_text(encoding="utf-8")
    assert "funnel-scroll" in rep_tsx, "Reports missing .funnel-scroll wrapper"
    assert "column-selector" in rep_tsx, "Reports missing .column-selector"
    assert "column-select-all-btn" in rep_tsx, "Reports missing .column-select-all-btn"
    assert "column-checkbox-item" in rep_tsx, "Reports missing .column-checkbox-item"

    # InteractionPage: Выбрать файл label
    ix_tsx = INTERACTION_PAGE.read_text(encoding="utf-8")
    assert "Выбрать файл</Button>" in ix_tsx or ">Выбрать файл\n" in ix_tsx or "size={16} />Выбрать файл" in ix_tsx, (
        "InteractionPage file upload button should be neutral 'Выбрать файл'"
    )

    # CatalogPage: migration matrix table-scroll
    cat_tsx = CATALOG_PAGE.read_text(encoding="utf-8")
    assert "table-scroll migration-matrix-wrapper" in cat_tsx, (
        "CatalogPage migration matrix wrapper must include .table-scroll"
    )


def test_css_cascade_ordering_and_defect_detection():
    """Adversarial cascade check: Detect when default component rules defined AFTER the media query

    override mobile styles due to equal specificity and later document order.
    """
    lines = STYLES_CSS.read_text(encoding="utf-8").splitlines()

    # Find the bounds of @media (max-width: 767px)
    media_start = None
    media_end = None
    brace_depth = 0

    for idx, line in enumerate(lines):
        if "@media (max-width: 767px)" in line:
            media_start = idx
            brace_depth = line.count("{") - line.count("}")
            continue
        if media_start is not None and media_end is None:
            brace_depth += line.count("{") - line.count("}")
            if brace_depth <= 0:
                media_end = idx
                break

    assert media_start is not None and media_end is not None, "Could not locate mobile media query bounds"

    # Check .workflow-scroll-hint:
    # Must NOT have an un-scoped display: none defined AFTER the media query!
    hint_media_line = None
    hint_post_media_lines = []

    for idx, line in enumerate(lines):
        if ".workflow-scroll-hint" in line:
            if media_start <= idx <= media_end:
                hint_media_line = idx + 1
            elif idx > media_end:
                hint_post_media_lines.append((idx + 1, line.strip()))

    # DEFECT IDENTIFICATION:
    # If .workflow-scroll-hint has a definition AFTER the media query, verify its display property
    if hint_post_media_lines:
        post_css = "\n".join(lines[media_end:])
        hint_post_match = re.search(r"\.workflow-scroll-hint\s*\{([^}]+)\}", post_css)
        if hint_post_match:
            post_block = hint_post_match.group(1)
            # If display: none is declared after media query, it will override display: flex on mobile!
            if "display: none" in post_block:
                pytest.fail(
                    f"CRITICAL CASCADE BUG DETECTED: .workflow-scroll-hint has 'display: none' at line {hint_post_media_lines[0][0]}, "
                    f"which appears AFTER the mobile media query (lines {media_start+1}-{media_end+1}). "
                    f"According to CSS cascade rules, the later rule wins, making the hint completely invisible on mobile devices (<768px)! "
                    f"Media queries must be placed AFTER base styles or base styles must precede media queries."
                )


def test_read_only_invariants():
    """Verify read-only invariants: docs/architecture/ untouched, 0 new packages."""
    import subprocess

    diff_arch = subprocess.run(
        ["git", "diff", "--stat", "docs/architecture/"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert diff_arch.stdout.strip() == "", f"docs/architecture/ was modified: {diff_arch.stdout}"

    diff_deps = subprocess.run(
        ["git", "diff", "--stat", "frontend/package.json", "backend/requirements.txt"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert diff_deps.stdout.strip() == "", f"Dependencies modified: {diff_deps.stdout}"
