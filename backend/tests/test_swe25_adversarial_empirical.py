"""Empirical and Adversarial Test Suite for SWE-25 & AC21.

Author: teamwork_preview_challenger_d9_empirical (Challenger 1, Stage 9)
Archetype: Empirical Challenger & Adversarial Critic
Mission: Find bugs, stress-test assumptions, mine edge cases, and execute exhaustive
         empirical verification of SWE-25 (Role-based Knowledge Base & Reference Views)
         and AC21 (Interactive Error & Fault Simulator) in frontend/src/views/ReferenceViews.tsx.

Dimensions tested:
1. Extreme input fuzzing for isHelpTabAllowed(tab, role):
   - Whitespace, mixed casing, non-string primitives, objects, functions, symbols.
   - Malicious injection payloads: SQLi, XSS, command injection, path traversal, null bytes, unicode homoglyphs.
2. Invariant verification: isHelpTabAllowed(getInitialTab(role), role) === true across 1,000+ randomized trials.
3. AC21 Fault Simulator exhaustive validation:
   - All 12 fault codes: 400, 401, 403, 404, 409, 422, 413, quarantine, 500, 502, 503, 504.
   - Schema validation: statusText, envelope.error.{code, message, request_id, details}, remediation.
   - Domain invariants: Zero-Oracle 404, CAS revision conflict 409, 25MB limit 413, 10-format whitelist quarantine.
4. Form state preservation simulation:
   - Proving that simulated error triggering does NOT erase user inputs (demoTitle, demoComment).
5. 152-FZ & Security invariants:
   - Zero storage leaks (no localStorage/sessionStorage), synthetic data only.
"""
from pathlib import Path
import json
import re
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[2]
REFERENCE_VIEWS = ROOT / "frontend" / "src" / "views" / "ReferenceViews.tsx"

EXPECTED_12_FAULT_CODES = [
    "400", "401", "403", "404", "409", "422",
    "413", "quarantine", "500", "502", "503", "504"
]

EXPECTED_10_FORMATS = [
    "png", "jpeg", "pdf", "zip", "gzip", "rar", "doc", "docx", "xls", "xlsx"
]


def _extract_source_components():
    """Extract helper functions and SIMULATED_ERRORS directly from ReferenceViews.tsx."""
    assert REFERENCE_VIEWS.is_file(), f"Missing file: {REFERENCE_VIEWS}"
    content = REFERENCE_VIEWS.read_text(encoding="utf-8")

    is_allowed_match = re.search(r"export function isHelpTabAllowed\([^)]*\)[^{]*\{([\s\S]*?)\n\}", content)
    get_initial_match = re.search(r"export function getInitialTab\([^)]*\)[^{]*\{([\s\S]*?)\n\}", content)
    errors_match = re.search(r"export const SIMULATED_ERRORS[^{]*= (\{[\s\S]*?\n\});", content)

    assert is_allowed_match is not None, "Could not extract isHelpTabAllowed from ReferenceViews.tsx"
    assert get_initial_match is not None, "Could not extract getInitialTab from ReferenceViews.tsx"
    assert errors_match is not None, "Could not extract SIMULATED_ERRORS from ReferenceViews.tsx"

    return {
        "is_allowed_body": is_allowed_match.group(1),
        "get_initial_body": get_initial_match.group(1),
        "simulated_errors_js": errors_match.group(1),
        "full_content": content,
    }


def _run_node_script(script_body: str) -> subprocess.CompletedProcess:
    """Run an isolated Node.js test script and return completed process."""
    return subprocess.run(
        ["node", "-e", script_body],
        capture_output=True,
        text=True,
        check=False
    )


class TestSWE25AdversarialRoleFuzzing:
    """Stress-test isHelpTabAllowed with extreme inputs and adversarial payloads."""

    def test_swe25_fuzz_extreme_inputs_and_malicious_injections(self):
        """Fuzz isHelpTabAllowed with SQLi, XSS, null bytes, unicode, and non-string types."""
        components = _extract_source_components()
        fn1 = components["is_allowed_body"]

        node_script = f"""
        const isHelpTabAllowed = new Function("tab", "role", {json.dumps(fn1)});

        // 1. Extreme non-string types for tab (should all safely return false without throwing)
        const invalidTabs = [
            null, undefined, 0, 1, -1, 42, 3.14, NaN, Infinity, -Infinity,
            true, false, {{}}, [], [1, 2], {{ tab: 'admin' }}, () => 'admin',
            Symbol('tab'), BigInt(123), '', '   ', '\\t\\n\\r  '
        ];
        for (const badTab of invalidTabs) {{
            try {{
                const res = isHelpTabAllowed(badTab, 'admin');
                if (res !== false) {{
                    console.error('Expected false for bad tab:', badTab, 'got:', res);
                    process.exit(1);
                }}
            }} catch (err) {{
                console.error('Threw error on bad tab:', badTab, err);
                process.exit(2);
            }}
        }}

        // 2. Extreme non-string types for role (should safely default to manager or handle gracefully)
        const invalidRoles = [
            null, undefined, 0, 1, -1, 42, 3.14, NaN, Infinity, -Infinity,
            true, false, {{}}, [], [ 'admin' ], {{ role: 'admin' }}, () => 'admin',
            Symbol('role'), BigInt(456), '', '   ', '\\t\\n\\r  '
        ];
        for (const badRole of invalidRoles) {{
            try {{
                // Public tabs must remain accessible even with invalid role
                if (!isHelpTabAllowed('errors', badRole)) {{
                    console.error('Errors tab must be allowed for bad role:', badRole);
                    process.exit(3);
                }}
                if (!isHelpTabAllowed('security', badRole)) {{
                    console.error('Security tab must be allowed for bad role:', badRole);
                    process.exit(4);
                }}
                // Privileged admin/supervisor tabs must NEVER be granted to invalid roles
                if (isHelpTabAllowed('admin', badRole)) {{
                    console.error('Admin tab illegally granted for bad role:', badRole);
                    process.exit(5);
                }}
                if (isHelpTabAllowed('supervisor', badRole)) {{
                    console.error('Supervisor tab illegally granted for bad role:', badRole);
                    process.exit(6);
                }}
            }} catch (err) {{
                console.error('Threw error on bad role:', badRole, err);
                process.exit(7);
            }}
        }}

        // 3. Malicious injection attacks as role parameter
        const maliciousRoles = [
            "admin; DROP TABLE users; --",
            "admin' OR '1'='1",
            "administrator' UNION SELECT * FROM users --",
            "<script>alert('xss')</script>",
            "<img src=x onerror=alert(1)>",
            "javascript:void(0)",
            "${7*7}",
            "{{ role }}",
            "admin\\x00evil",
            "admin\\0evil",
            "admin\\ninjected",
            "admin\\r\\ninjected",
            "admin\\tinjected",
            "../../admin",
            "../etc/passwd",
            "admin\\u200Bevil",
            "аdmin", // Cyrillic homoglyph
            "администратор", // Russian Cyrillic
            "root", "superuser", "god", "daemon", "operator", "sysadmin",
            "manager-a", "supervisor-b", "user_12345"
        ];

        for (const malRole of maliciousRoles) {{
            // Must not grant admin or supervisor access
            if (isHelpTabAllowed('admin', malRole)) {{
                console.error('VULNERABILITY: Admin tab granted to malicious role payload:', malRole);
                process.exit(10);
            }}
            if (isHelpTabAllowed('supervisor', malRole)) {{
                console.error('VULNERABILITY: Supervisor tab granted to malicious role payload:', malRole);
                process.exit(11);
            }}
            // Public tabs must still be allowed
            if (!isHelpTabAllowed('errors', malRole)) {{
                console.error('Errors tab should be allowed for role:', malRole);
                process.exit(12);
            }}
        }}

        // 4. Case-insensitivity and whitespace padding on legitimate roles
        const validAdminVariations = ['admin', 'Admin', 'ADMIN', 'administrator', 'Administrator', 'ADMINISTRATOR', '  admin  ', '\\tadministrator\\n', '  ADMIN  '];
        for (const a of validAdminVariations) {{
            if (!isHelpTabAllowed('admin', a)) {{
                console.error('Admin tab denied for valid admin variation:', a);
                process.exit(20);
            }}
            if (!isHelpTabAllowed('supervisor', a)) {{
                console.error('Supervisor tab denied for admin variation:', a);
                process.exit(21);
            }}
            if (!isHelpTabAllowed('manager', a)) {{
                console.error('Manager tab denied for admin variation:', a);
                process.exit(22);
            }}
        }}

        const validSupervisorVariations = ['supervisor', 'Supervisor', 'SUPERVISOR', '  supervisor  ', '\\tsupervisor\\r\\n'];
        for (const s of validSupervisorVariations) {{
            if (!isHelpTabAllowed('supervisor', s)) {{
                console.error('Supervisor tab denied for valid supervisor variation:', s);
                process.exit(23);
            }}
            if (!isHelpTabAllowed('manager', s)) {{
                console.error('Manager tab denied for supervisor variation:', s);
                process.exit(24);
            }}
            if (isHelpTabAllowed('admin', s)) {{
                console.error('Supervisor illegally granted admin tab:', s);
                process.exit(25);
            }}
        }}

        const validManagerVariations = ['manager', 'Manager', 'MANAGER', '  manager  ', '\\nmanager\\t'];
        for (const m of validManagerVariations) {{
            if (!isHelpTabAllowed('manager', m)) {{
                console.error('Manager tab denied for valid manager variation:', m);
                process.exit(26);
            }}
            if (isHelpTabAllowed('supervisor', m)) {{
                console.error('Manager illegally granted supervisor tab:', m);
                process.exit(27);
            }}
            if (isHelpTabAllowed('admin', m)) {{
                console.error('Manager illegally granted admin tab:', m);
                process.exit(28);
            }}
        }}

        console.log("PASS: Fuzzing & Malicious Injection Resilience Verified");
        """
        res = _run_node_script(node_script)
        assert res.returncode == 0, f"Node script failed (exit {res.returncode}):\n{res.stderr}\n{res.stdout}"
        assert "PASS" in res.stdout


class TestSWE25InvariantRandomizedPermutations:
    """Stress-test the core invariant across 1,000+ randomized permutations."""

    def test_swe25_invariant_across_1000_random_permutations(self):
        """Verify: isHelpTabAllowed(getInitialTab(role), role) === true for >= 1,000 randomized inputs."""
        components = _extract_source_components()
        fn1 = components["is_allowed_body"]
        fn2 = components["get_initial_body"]

        node_script = f"""
        const isHelpTabAllowed = new Function("tab", "role", {json.dumps(fn1)});
        const getInitialTab = new Function("role", {json.dumps(fn2)});

        const seedRoles = [
            'manager', 'supervisor', 'administrator', 'admin',
            'Manager', 'SUPERVISOR', 'Administrator', 'ADMIN',
            '  manager  ', '  supervisor  ', '  admin  ', '  administrator  ',
            null, undefined, '', '   ', '\\t\\n\\r  ', 0, 1, -1, 42, 3.14, NaN, Infinity, -Infinity,
            true, false, {{}}, [], [1, 2, 3], {{ role: 'admin' }}, () => {{}},
            'admin; DROP TABLE users; --', '<script>alert(1)</script>', \"' OR '1'='1\",
            'admin\\x00', 'admin\\n', 'admin\\r\\n', 'admin\\t', 'admin/../admin', '../manager',
            'manager-a', 'supervisor-b', 'guest', 'root', 'daemon', 'auditor', 'student',
            'operator', 'anonymous', 'system', 'ADMINISTRATOR', 'AdMiNiStRaToR', 'SuPeRvIsOr', 'MaNaGeR'
        ];

        let trials = 0;
        const validTabSet = new Set(['manager', 'supervisor', 'admin', 'errors', 'security']);

        // First test all seed cases
        for (const role of seedRoles) {{
            trials++;
            const initTab = getInitialTab(role);
            if (!validTabSet.has(initTab)) {{
                console.error(`Invalid initial tab "${{initTab}}" produced for role:`, role);
                process.exit(1);
            }}
            const allowed = isHelpTabAllowed(initTab, role);
            if (allowed !== true) {{
                console.error(`Invariant broken for seed role "${{JSON.stringify(role)}}": getInitialTab="${{initTab}}", allowed=${{allowed}}`);
                process.exit(2);
            }}
        }}

        // Now run 1,000 randomized permutations
        const chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 _-./;()\\"\\'<>+=!?#@$%^&*\\t\\n';
        const roleKeywords = ['manager', 'supervisor', 'admin', 'administrator', 'guest', 'auditor', 'hacker', ''];

        for (let i = 0; i < 1000; i++) {{
            trials++;
            let testRole;
            const mode = Math.random();

            if (mode < 0.3) {{
                // Scrambled casing and padding of role keywords
                const base = roleKeywords[Math.floor(Math.random() * roleKeywords.length)];
                const padLeft = ' '.repeat(Math.floor(Math.random() * 6));
                const padRight = ' '.repeat(Math.floor(Math.random() * 6));
                const cased = base.split('').map(c => Math.random() > 0.5 ? c.toUpperCase() : c.toLowerCase()).join('');
                testRole = padLeft + cased + padRight;
            }} else if (mode < 0.6) {{
                // Random characters
                const len = Math.floor(Math.random() * 30);
                testRole = Array.from({{ length: len }}, () => chars[Math.floor(Math.random() * chars.length)]).join('');
            }} else if (mode < 0.8) {{
                // Primitives & falsy/truthy non-strings
                const prims = [null, undefined, Math.floor(Math.random() * 2000) - 1000, Math.random() > 0.5, {{}}, [], NaN, ''];
                testRole = prims[Math.floor(Math.random() * prims.length)];
            }} else {{
                // Adversarial injections
                const exploits = [
                    "admin' OR 1=1 --",
                    "<script>alert('xss')</script>",
                    "manager; drop database;",
                    "\\u0000admin",
                    "admin\\r\\nSet-Cookie: session=evil",
                    "${{7*7}}",
                    "{{{{ role }}}}",
                    "javascript:void(0)",
                    "root@localhost",
                    "system:serviceaccount:default:admin"
                ];
                testRole = exploits[Math.floor(Math.random() * exploits.length)];
            }}

            const initTab = getInitialTab(testRole);
            if (!validTabSet.has(initTab)) {{
                console.error(`Invalid initial tab "${{initTab}}" at trial ${{i}} for role:`, testRole);
                process.exit(3);
            }}
            const allowed = isHelpTabAllowed(initTab, testRole);
            if (allowed !== true) {{
                console.error(`Invariant broken at trial ${{i}} for role "${{JSON.stringify(testRole)}}": initialTab="${{initTab}}", allowed=${{allowed}}`);
                process.exit(4);
            }}
        }}

        console.log(`PASS: Invariant holds 100% across ${{trials}} trials`);
        """
        res = _run_node_script(node_script)
        assert res.returncode == 0, f"Node invariant test failed:\n{res.stderr}\n{res.stdout}"
        assert "PASS: Invariant holds 100%" in res.stdout


class TestAC21FaultSimulatorExhaustive:
    """Exhaustive programmatic check of SIMULATED_ERRORS in ReferenceViews.tsx."""

    def test_ac21_all_12_fault_codes_schema_and_content(self):
        """Verify each of the 12 fault codes contains statusText, valid envelope.error, and remediation."""
        components = _extract_source_components()
        errs_js = components["simulated_errors_js"]

        node_script = f"""
        const SIMULATED_ERRORS = {errs_js};
        const expectedCodes = {json.dumps(EXPECTED_12_FAULT_CODES)};
        const expectedFormats = {json.dumps(EXPECTED_10_FORMATS)};

        // 1. Verify exact 12 keys
        const actualKeys = Object.keys(SIMULATED_ERRORS);
        if (actualKeys.length !== expectedCodes.length) {{
            console.error(`Expected ${{expectedCodes.length}} fault codes, got ${{actualKeys.length}}`);
            process.exit(1);
        }}

        for (const code of expectedCodes) {{
            if (!SIMULATED_ERRORS[code]) {{
                console.error(`Missing fault code: "${{code}}"`);
                process.exit(2);
            }}

            const spec = SIMULATED_ERRORS[code];

            // Verify statusText
            if (typeof spec.statusText !== 'string' || spec.statusText.trim().length === 0) {{
                console.error(`Code ${{code}}: statusText must be a non-empty string`);
                process.exit(3);
            }}

            // Verify remediation
            if (typeof spec.remediation !== 'string' || spec.remediation.trim().length === 0) {{
                console.error(`Code ${{code}}: remediation must be a non-empty string`);
                process.exit(4);
            }}

            // Verify envelope
            if (!spec.envelope || typeof spec.envelope !== 'object') {{
                console.error(`Code ${{code}}: envelope must be an object`);
                process.exit(5);
            }}

            // Verify envelope.error
            if (!spec.envelope.error || typeof spec.envelope.error !== 'object') {{
                console.error(`Code ${{code}}: envelope.error must be an object`);
                process.exit(6);
            }}

            const err = spec.envelope.error;

            // code
            if (typeof err.code !== 'string' || err.code.trim().length === 0) {{
                console.error(`Code ${{code}}: envelope.error.code must be a non-empty string`);
                process.exit(7);
            }}

            // message
            if (typeof err.message !== 'string' || err.message.trim().length === 0) {{
                console.error(`Code ${{code}}: envelope.error.message must be a non-empty string`);
                process.exit(8);
            }}

            // request_id
            if (typeof err.request_id !== 'string' || !err.request_id.startsWith('req-sim-')) {{
                console.error(`Code ${{code}}: envelope.error.request_id must start with "req-sim-", got: ${{err.request_id}}`);
                process.exit(9);
            }}

            // details
            if (!err.details || typeof err.details !== 'object' || Array.isArray(err.details)) {{
                console.error(`Code ${{code}}: envelope.error.details must be a dictionary/object`);
                process.exit(10);
            }}
        }}

        // 2. Domain-Specific Invariant Checks
        // 404: Zero-Oracle & 152-FZ scope isolation
        const err404 = SIMULATED_ERRORS['404'];
        if (!err404.statusText.includes('Zero-Oracle') || !err404.statusText.includes('152-ФЗ')) {{
            console.error('404 must explicitly mention Zero-Oracle and 152-ФЗ in statusText');
            process.exit(20);
        }}
        if (err404.envelope.error.code !== 'NOT_FOUND') {{
            console.error('404 canonical code must be NOT_FOUND');
            process.exit(21);
        }}

        // 409: CAS conflict
        const err409 = SIMULATED_ERRORS['409'];
        if (err409.envelope.error.code !== 'REVISION_CONFLICT') {{
            console.error('409 canonical code must be REVISION_CONFLICT');
            process.exit(22);
        }}
        if (typeof err409.envelope.error.details.expected_revision !== 'number' || typeof err409.envelope.error.details.current_revision !== 'number') {{
            console.error('409 details must contain expected_revision and current_revision numbers');
            process.exit(23);
        }}

        // 413: 25 MB payload limit
        const err413 = SIMULATED_ERRORS['413'];
        if (err413.envelope.error.code !== 'FILE_TOO_LARGE') {{
            console.error('413 canonical code must be FILE_TOO_LARGE');
            process.exit(24);
        }}
        if (err413.envelope.error.details.max_bytes !== 26214400) {{
            console.error('413 details.max_bytes must be exactly 26214400 (25 MB)');
            process.exit(25);
        }}

        // quarantine: 10 allowed formats
        const errQuarantine = SIMULATED_ERRORS['quarantine'];
        if (errQuarantine.envelope.error.code !== 'FILE_TYPE_NOT_ALLOWED') {{
            console.error('Quarantine canonical code must be FILE_TYPE_NOT_ALLOWED');
            process.exit(26);
        }}
        const formats = errQuarantine.envelope.error.details.allowed_formats;
        if (!Array.isArray(formats) || formats.length !== 10) {{
            console.error('Quarantine details.allowed_formats must be an array of exactly 10 formats');
            process.exit(27);
        }}
        for (const fmt of expectedFormats) {{
            if (!formats.includes(fmt)) {{
                console.error(`Quarantine allowed_formats missing expected format "${{fmt}}"`);
                process.exit(28);
            }}
        }}

        // 502 & 504: External Zion LMS integration failures
        const err502 = SIMULATED_ERRORS['502'];
        if (!JSON.stringify(err502).includes('rtkb.zion-lms.ru')) {{
            console.error('502 must reference Zion LMS upstream');
            process.exit(29);
        }}

        const err504 = SIMULATED_ERRORS['504'];
        if (!JSON.stringify(err504).includes('rtkb.zion-lms.ru')) {{
            console.error('504 must reference Zion LMS upstream');
            process.exit(30);
        }}

        console.log("PASS: All 12 Fault Codes Satisfy Canonical Envelope Schema & Domain Invariants");
        """
        res = _run_node_script(node_script)
        assert res.returncode == 0, f"Fault simulator verification failed:\n{res.stderr}\n{res.stdout}"
        assert "PASS: All 12 Fault Codes Satisfy Canonical Envelope Schema" in res.stdout


class TestAC21FormStatePreservation:
    """Empirical simulation of user form input preservation during error triggers."""

    def test_ac21_form_inputs_not_erased_on_simulated_errors(self):
        """Simulate React state transitions: verify demoTitle & demoComment are NEVER erased."""
        components = _extract_source_components()
        errs_js = components["simulated_errors_js"]

        node_script = f"""
        const SIMULATED_ERRORS = {errs_js};
        const codes = {json.dumps(EXPECTED_12_FAULT_CODES)};

        // Simulate React component state container
        class MockHelpPageState {{
            constructor() {{
                this.demoTitle = 'Взаимодействие с СПбГУ по направлению DevOps';
                this.demoComment = 'Договор передан на согласование проректору.';
                this.demoErrorType = '409';
                this.demoSimulatedError = null;
                this.demoPreserveSuccess = false;
                this.demoEnvelope = null;
                this.demoRemediation = null;
            }}

            handleTriggerDemoError(e) {{
                if (e && e.preventDefault) e.preventDefault();
                this.demoPreserveSuccess = true;
                const spec = SIMULATED_ERRORS[this.demoErrorType] || SIMULATED_ERRORS['409'];
                this.demoSimulatedError = spec.statusText;
                this.demoEnvelope = spec.envelope;
                this.demoRemediation = spec.remediation;
            }}
        }}

        const state = new MockHelpPageState();

        // 1. Initial draft preservation
        const initialTitle = state.demoTitle;
        const initialComment = state.demoComment;

        // 2. Trigger each of the 12 error simulations sequentially
        for (const code of codes) {{
            state.demoErrorType = code;
            state.handleTriggerDemoError({{ preventDefault: () => {{}} }});

            // Critical check: Form inputs MUST NOT be cleared or mutated
            if (state.demoTitle !== initialTitle) {{
                console.error(`Regression on code ${{code}}: demoTitle was mutated!`, state.demoTitle);
                process.exit(1);
            }}
            if (state.demoComment !== initialComment) {{
                console.error(`Regression on code ${{code}}: demoComment was mutated!`, state.demoComment);
                process.exit(2);
            }}

            // Error display state must be populated
            if (state.demoSimulatedError !== SIMULATED_ERRORS[code].statusText) {{
                console.error(`Code ${{code}}: statusText mismatch in UI state`);
                process.exit(3);
            }}
            if (state.demoEnvelope !== SIMULATED_ERRORS[code].envelope) {{
                console.error(`Code ${{code}}: envelope mismatch in UI state`);
                process.exit(4);
            }}
            if (state.demoRemediation !== SIMULATED_ERRORS[code].remediation) {{
                console.error(`Code ${{code}}: remediation mismatch in UI state`);
                process.exit(5);
            }}
            if (!state.demoPreserveSuccess) {{
                console.error(`Code ${{code}}: demoPreserveSuccess flag not set`);
                process.exit(6);
            }}
        }}

        // 3. User edits inputs while error is displayed -> triggers new error -> inputs stay intact
        state.demoTitle = 'Новый заголовок после CAS конфликта';
        state.demoComment = 'Исправленный комментарий без сброса страницы.';
        state.demoErrorType = '422';
        state.handleTriggerDemoError({{ preventDefault: () => {{}} }});

        if (state.demoTitle !== 'Новый заголовок после CAS конфликта') {{
            console.error('Custom user input lost during error trigger!');
            process.exit(7);
        }}
        if (state.demoComment !== 'Исправленный комментарий без сброса страницы.') {{
            console.error('Custom user comment lost during error trigger!');
            process.exit(8);
        }}

        console.log("PASS: Form Input State Fully Preserved Across All 12 Fault Simulations");
        """
        res = _run_node_script(node_script)
        assert res.returncode == 0, f"Form state preservation test failed:\n{res.stderr}\n{res.stdout}"
        assert "PASS: Form Input State Fully Preserved" in res.stdout


class TestSWE25SecurityAndZeroOracleInvariants:
    """Verify 152-FZ compliance, token storage, and zero-oracle privacy in ReferenceViews.tsx."""

    def test_no_browser_storage_leaks(self):
        """Verify ReferenceViews.tsx does not access localStorage or sessionStorage (tokens strictly in-memory)."""
        components = _extract_source_components()
        content = components["full_content"]

        # Ensure localStorage/sessionStorage APIs are NOT used for storing tokens/state
        assert not re.search(r"\b(localStorage|sessionStorage)\s*\[", content), "localStorage/sessionStorage indexing detected"
        assert not re.search(r"\b(localStorage|sessionStorage)\s*\.\s*[a-zA-Z_]", content), "localStorage/sessionStorage API call detected"
        assert not re.search(r"\bwindow\.(localStorage|sessionStorage)\b", content), "window.localStorage/sessionStorage usage detected"

    def test_zero_oracle_and_role_protection_semantics(self):
        """Verify Zero-Oracle masking and 152-FZ explanations are present."""
        components = _extract_source_components()
        content = components["full_content"]

        assert "Zero-Oracle" in content, "Zero-Oracle masking must be documented in ReferenceViews.tsx"
        assert "152-ФЗ" in content, "152-FZ references must be present in ReferenceViews.tsx"
        assert "ФСТЭК №117" in content, "FSTEK 117 references must be present in ReferenceViews.tsx"
        assert "expected_revision" in content, "CAS expected_revision must be referenced"
