"""Contract and static analysis verification for swe_25 requirements:
R1. Role-based tab filtering (.help-tabs) in HelpPage (ReferenceViews.tsx)
R2. Guard-protection of content rendering and auto-fallback of activeTab
R3. Preservation of AC21 error simulator and state preservation
"""
from pathlib import Path
import json
import re
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[2]
REFERENCE_VIEWS = ROOT / "frontend" / "src" / "views" / "ReferenceViews.tsx"


def _extract_helpers_from_source():
    """Extract the real function bodies directly from ReferenceViews.tsx."""
    content = REFERENCE_VIEWS.read_text(encoding="utf-8")
    is_allowed_match = re.search(r"export function isHelpTabAllowed\([^)]*\)[^{]*\{([\s\S]*?)\n\}", content)
    get_initial_match = re.search(r"export function getInitialTab\([^)]*\)[^{]*\{([\s\S]*?)\n\}", content)
    assert is_allowed_match is not None, "Could not find isHelpTabAllowed in ReferenceViews.tsx"
    assert get_initial_match is not None, "Could not find getInitialTab in ReferenceViews.tsx"

    fn1 = is_allowed_match.group(1)
    fn2 = get_initial_match.group(1)
    return fn1, fn2


def test_swe25_reference_views_file_exists():
    """Verify ReferenceViews.tsx exists and is readable."""
    assert REFERENCE_VIEWS.is_file(), f"Missing {REFERENCE_VIEWS}"


def test_swe25_help_tab_type_and_helpers_exported():
    """Verify HelpTab type, isHelpTabAllowed, and getInitialTab are defined and exported."""
    content = REFERENCE_VIEWS.read_text(encoding="utf-8")

    assert "export type HelpTab" in content, "HelpTab type must be exported"
    assert "export function isHelpTabAllowed" in content, "isHelpTabAllowed predicate must be exported"
    assert "export function getInitialTab" in content, "getInitialTab helper must be exported"


def test_swe25_is_help_tab_allowed_real_source_evaluation():
    """Verify isHelpTabAllowed role-based visibility matrix according to R1 using real extracted source."""
    fn1, fn2 = _extract_helpers_from_source()
    node_code = f"""
    const isHelpTabAllowed = new Function("tab", "role", {json.dumps(fn1)});
    const allTabs = ['manager', 'supervisor', 'admin', 'errors', 'security'];

    // Manager: exactly 3 tabs (manager, errors, security)
    const managerTabs = allTabs.filter(t => isHelpTabAllowed(t, 'manager'));
    if (managerTabs.length !== 3) process.exit(1);
    if (!managerTabs.includes('manager') || !managerTabs.includes('errors') || !managerTabs.includes('security')) process.exit(2);
    if (managerTabs.includes('supervisor') || managerTabs.includes('admin')) process.exit(3);

    // Supervisor: exactly 4 tabs (manager, supervisor, errors, security)
    const supervisorTabs = allTabs.filter(t => isHelpTabAllowed(t, 'supervisor'));
    if (supervisorTabs.length !== 4) process.exit(4);
    if (!supervisorTabs.includes('supervisor') || !supervisorTabs.includes('manager') || !supervisorTabs.includes('errors') || !supervisorTabs.includes('security')) process.exit(5);
    if (supervisorTabs.includes('admin')) process.exit(6);

    // Administrator: all 5 tabs
    const adminTabs = allTabs.filter(t => isHelpTabAllowed(t, 'administrator'));
    if (adminTabs.length !== 5) process.exit(7);

    // Admin alias: all 5 tabs
    const adminAliasTabs = allTabs.filter(t => isHelpTabAllowed(t, 'admin'));
    if (adminAliasTabs.length !== 5) process.exit(8);

    // Role case insensitivity & padding: 'Administrator', 'SUPERVISOR', ' manager '
    if (!isHelpTabAllowed('admin', 'Administrator')) process.exit(9);
    if (!isHelpTabAllowed('supervisor', 'SUPERVISOR')) process.exit(10);
    if (!isHelpTabAllowed('manager', ' manager ')) process.exit(11);

    // Tab argument case insensitivity & padding: 'Admin', 'ERRORS', 'Security', 'Supervisor', ' admin '
    if (!isHelpTabAllowed('Admin', 'admin')) process.exit(12);
    if (!isHelpTabAllowed('ERRORS', 'manager')) process.exit(13);
    if (!isHelpTabAllowed('Security', 'manager')) process.exit(14);
    if (!isHelpTabAllowed('Supervisor', 'supervisor')) process.exit(15);
    if (!isHelpTabAllowed(' admin ', 'admin')) process.exit(16);

    // Tab alias: 'administrator' accepted as tab name
    if (!isHelpTabAllowed('administrator', 'admin')) process.exit(17);
    if (!isHelpTabAllowed('administrator', 'administrator')) process.exit(18);
    if (isHelpTabAllowed('administrator', 'manager')) process.exit(19);

    // Invalid / empty / null / unknown tabs
    if (isHelpTabAllowed(null, 'admin')) process.exit(20);
    if (isHelpTabAllowed(undefined, 'admin')) process.exit(21);
    if (isHelpTabAllowed('', 'admin')) process.exit(22);
    if (isHelpTabAllowed('   ', 'admin')) process.exit(23);
    if (isHelpTabAllowed('unknown_tab', 'admin')) process.exit(24);

    // Non-string arguments must safely return false without throwing TypeError
    if (isHelpTabAllowed(123, 'admin')) process.exit(26);
    if (isHelpTabAllowed({{}}, 'admin')) process.exit(27);
    if (isHelpTabAllowed(true, 'admin')) process.exit(28);
    if (isHelpTabAllowed('admin', 123)) process.exit(29);
    if (isHelpTabAllowed('admin', {{}})) process.exit(30);

    // Unrecognized role: strictly 2 public tabs (errors, security)
    const guestTabs = allTabs.filter(t => isHelpTabAllowed(t, 'guest'));
    if (guestTabs.length !== 2 || !guestTabs.includes('errors') || !guestTabs.includes('security')) process.exit(25);

    console.log("OK");
    """
    res = subprocess.run(["node", "-e", node_code], capture_output=True, text=True)
    assert res.returncode == 0, f"Node verification failed: {res.stderr}"
    assert "OK" in res.stdout


def test_swe25_get_initial_tab_real_source_evaluation():
    """Verify getInitialTab returns default tab corresponding to user role using real extracted source."""
    fn1, fn2 = _extract_helpers_from_source()
    node_code = f"""
    const getInitialTab = new Function("role", {json.dumps(fn2)});

    if (getInitialTab('manager') !== 'manager') process.exit(1);
    if (getInitialTab('supervisor') !== 'supervisor') process.exit(2);
    if (getInitialTab('administrator') !== 'admin') process.exit(3);
    if (getInitialTab('admin') !== 'admin') process.exit(4);
    if (getInitialTab(undefined) !== 'manager') process.exit(5);
    if (getInitialTab(null) !== 'manager') process.exit(6);
    if (getInitialTab('') !== 'manager') process.exit(7);
    if (getInitialTab('   ') !== 'manager') process.exit(8);

    // Case insensitivity
    if (getInitialTab('Supervisor') !== 'supervisor') process.exit(9);
    if (getInitialTab('Administrator') !== 'admin') process.exit(10);
    if (getInitialTab('ADMIN') !== 'admin') process.exit(11);

    // Unknown role safely falls back to errors tab
    if (getInitialTab('guest') !== 'errors') process.exit(12);
    if (getInitialTab('auditor') !== 'errors') process.exit(13);

    // Whitespace padding
    if (getInitialTab(' supervisor ') !== 'supervisor') process.exit(14);
    if (getInitialTab(' administrator ') !== 'admin') process.exit(15);
    if (getInitialTab(' admin ') !== 'admin') process.exit(16);
    if (getInitialTab(' manager ') !== 'manager') process.exit(17);

    // Non-string / unexpected role
    if (getInitialTab(123) !== 'manager') process.exit(18);
    if (getInitialTab({{}}) !== 'manager') process.exit(19);

    console.log("OK");
    """
    res = subprocess.run(["node", "-e", node_code], capture_output=True, text=True)
    assert res.returncode == 0, f"Node verification failed: {res.stderr}"
    assert "OK" in res.stdout


def test_swe25_invariant_initial_tab_always_allowed():
    """Verify core invariant: getInitialTab(role) is GUARANTEED to be allowed for role across all inputs."""
    fn1, fn2 = _extract_helpers_from_source()
    node_code = f"""
    const isHelpTabAllowed = new Function("tab", "role", {json.dumps(fn1)});
    const getInitialTab = new Function("role", {json.dumps(fn2)});

    const testRoles = [
      'manager', 'supervisor', 'administrator', 'admin',
      'Manager', 'SUPERVISOR', 'Administrator', 'ADMIN',
      '  manager  ', '  supervisor  ', '  admin  ', '  administrator  ',
      null, undefined, '', '   ', 123, true, {{}},
      'guest', 'auditor', 'unknown_role', 'student'
    ];

    for (const r of testRoles) {{
      const init = getInitialTab(r);
      if (!isHelpTabAllowed(init, r)) {{
        console.error(`Invariant broken for role ${{JSON.stringify(r)}}: initial=${{init}}`);
        process.exit(1);
      }}
    }}

    console.log("OK");
    """
    res = subprocess.run(["node", "-e", node_code], capture_output=True, text=True)
    assert res.returncode == 0, f"Node invariant verification failed: {res.stderr}"
    assert "OK" in res.stdout


def test_swe25_help_tabs_conditional_rendering():
    """Verify .help-tabs buttons are conditionally rendered using isHelpTabAllowed."""
    content = REFERENCE_VIEWS.read_text(encoding="utf-8")

    # Extract .help-tabs block
    tabs_container = re.search(
        r'<div\s+className="help-tabs"[^>]*>(.*?)</div>\s*\{/\*\s*Tab 1',
        content,
        re.DOTALL,
    )
    assert tabs_container is not None, "Could not find .help-tabs container"
    tabs_html = tabs_container.group(1)

    # Check that role-based tab buttons are conditionally rendered with isHelpTabAllowed
    assert "isHelpTabAllowed('manager', role)" in tabs_html, "Manager tab button must be guarded by isHelpTabAllowed"
    assert "isHelpTabAllowed('supervisor', role)" in tabs_html, "Supervisor tab button must be guarded by isHelpTabAllowed"
    assert "isHelpTabAllowed('admin', role)" in tabs_html, "Admin tab button must be guarded by isHelpTabAllowed"
    assert "isHelpTabAllowed('errors', role)" in tabs_html, "Errors tab button must be guarded by isHelpTabAllowed"
    assert "isHelpTabAllowed('security', role)" in tabs_html, "Security tab button must be guarded by isHelpTabAllowed"


def test_swe25_tab_content_guards():
    """Verify privileged content tabs (supervisor, admin) have guard checks in conditional rendering."""
    content = REFERENCE_VIEWS.read_text(encoding="utf-8")

    # Manager content guard
    assert re.search(
        r"activeTab === 'manager'\s*&&\s*isHelpTabAllowed\('manager',\s*role\)",
        content,
    ) is not None, "Manager content rendering must have isHelpTabAllowed guard"

    # Supervisor content guard (R2)
    assert re.search(
        r"activeTab === 'supervisor'\s*&&\s*isHelpTabAllowed\('supervisor',\s*role\)",
        content,
    ) is not None, "Supervisor content rendering must have isHelpTabAllowed guard"

    # Admin content guard (R2)
    assert re.search(
        r"activeTab === 'admin'\s*&&\s*isHelpTabAllowed\('admin',\s*role\)",
        content,
    ) is not None, "Admin content rendering must have isHelpTabAllowed guard"


def test_swe25_active_tab_validation_and_fallback():
    """Verify useEffect validates activeTab accessibility and falls back to getInitialTab."""
    content = REFERENCE_VIEWS.read_text(encoding="utf-8")

    # Verify useEffect presence with isHelpTabAllowed check and getInitialTab fallback
    effect_match = re.search(
        r"useEffect\(\(\)\s*=>\s*\{\s*if\s*\(!isHelpTabAllowed\(activeTab,\s*role\)\)\s*\{\s*setActiveTab\(getInitialTab\(role\)\);\s*\}\s*\},",
        content,
    )
    assert effect_match is not None, (
        "HelpPage must include useEffect that resets activeTab to getInitialTab(role) if isHelpTabAllowed returns false"
    )


def test_swe25_ac21_error_simulator_preservation():
    """Verify AC21 interactive error simulator remains functional and intact (R3)."""
    content = REFERENCE_VIEWS.read_text(encoding="utf-8")

    # AC21 state hooks
    assert "demoTitle" in content, "demoTitle state must be preserved"
    assert "demoComment" in content, "demoComment state must be preserved"
    assert "demoErrorType" in content, "demoErrorType state must be preserved"
    assert "demoSimulatedError" in content, "demoSimulatedError state must be preserved"
    assert "demoPreserveSuccess" in content, "demoPreserveSuccess state must be preserved"
    assert "handleTriggerDemoError" in content, "handleTriggerDemoError handler must be preserved"

    # Error codes covered
    assert "HTTP 409 Conflict" in content, "409 simulation text must be preserved"
    assert "HTTP 422 Unprocessable Entity" in content, "422 simulation text must be preserved"
    assert "HTTP 413 Payload Too Large" in content, "413 simulation text must be preserved"
    assert "HTTP 422 File Quarantine" in content, "Quarantine simulation text must be preserved"
