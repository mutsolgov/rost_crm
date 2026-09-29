"""Automated contract test suite for SWE-29:
Embedded documentation (User Guide & System Administrator Guide)
with real interface screenshots (TOR p. 5, GOST R 59853-2021).
"""
import struct
import subprocess
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import create_app

ROOT = Path(__file__).resolve().parents[2]
DOCS_SCREENSHOTS = ROOT / "docs" / "screenshots"
PUBLIC_SCREENSHOTS = ROOT / "frontend" / "public" / "docs" / "screenshots"
REFERENCE_VIEWS = ROOT / "frontend" / "src" / "views" / "ReferenceViews.tsx"
STYLES_CSS = ROOT / "frontend" / "src" / "styles.css"
USER_GUIDE = ROOT / "docs" / "USER_GUIDE.md"
SYSADMIN_GUIDE = ROOT / "docs" / "SYSADMIN_GUIDE.md"
EXPLANATORY_NOTE = ROOT / "docs" / "Пояснительная_записка_и_сопроводительная_документация_CRM_ИТ_Школа_Ростелеком.md"
NGINX_CONF = ROOT / "deploy" / "nginx.conf"
DOCS_ARCHITECTURE = ROOT / "docs" / "architecture"

EXPECTED_SCREENSHOT_NAMES = [
    "screen-01-login.png",
    "screen-02-manager-overview.png",
    "screen-03-interactions-registry.png",
    "screen-04-interaction-card-graph.png",
    "screen-05-interaction-d02-prevent.png",
    "screen-06-interaction-transition-rework.png",
    "screen-07-attachments-and-audit.png",
    "screen-08-supervisor-overview-reassign.png",
    "screen-09-reports-analytics-export.png",
    "screen-10-admin-overview-telemetry.png",
    "screen-11-catalog-import-wizard.png",
    "screen-12-workflow-migrator.png",
    "screen-13-error-diagnostic-center.png",
]


def test_screenshots_exist_in_public_and_docs_dirs():
    """Checks frontend/public/docs/screenshots/ and docs/screenshots/ exist.
    Checks all 13 PNG screenshots exist in both dirs (26 files total).
    Validates PNG signature b'\\x89PNG\\r\\n\\x1a\\n'.
    Validates dimensions (1440, 900) via struct.unpack('>II', data[16:24]).
    Validates file size > 20,000 bytes.
    """
    assert DOCS_SCREENSHOTS.is_dir(), f"Missing docs screenshots dir: {DOCS_SCREENSHOTS}"
    assert PUBLIC_SCREENSHOTS.is_dir(), f"Missing public screenshots dir: {PUBLIC_SCREENSHOTS}"

    verified_files = 0
    for target_dir in [DOCS_SCREENSHOTS, PUBLIC_SCREENSHOTS]:
        for filename in EXPECTED_SCREENSHOT_NAMES:
            file_path = target_dir / filename
            assert file_path.is_file(), f"Missing screenshot file: {file_path}"

            data = file_path.read_bytes()
            assert data[:8] == b"\x89PNG\r\n\x1a\n", f"Invalid PNG magic bytes in {file_path}"

            width, height = struct.unpack(">II", data[16:24])
            assert (width, height) == (1440, 900), (
                f"Unexpected dimensions ({width}x{height}) in {file_path}, expected (1440, 900)"
            )

            assert len(data) > 20000, (
                f"Screenshot file size too small ({len(data)} bytes) in {file_path}, expected > 20000 bytes"
            )
            verified_files += 1

    assert verified_files == 26, f"Expected exactly 26 screenshot files verified, got {verified_files}"


def test_user_guide_markdown_structure():
    """Checks docs/USER_GUIDE.md exists and > 3000 bytes.
    Checks presence of sections for Login, Manager (15 stages, card, graph, D02, rework comments,
    attachments, audit trail), Supervisor (Reassign, Reports), and Errors.
    Checks markdown references to screen-01..screen-09, screen-13.
    """
    assert USER_GUIDE.is_file(), f"Missing {USER_GUIDE}"
    content = USER_GUIDE.read_text(encoding="utf-8")
    assert len(content) > 3000, f"USER_GUIDE.md too short: {len(content)} characters"

    lower = content.lower()

    # Login / Auth section
    assert "авторизаци" in lower or "ролевая модель" in lower or "логин" in lower

    # Manager section (15 stages, card, graph, D02, rework comments, attachments, audit trail)
    assert "кам-менеджер" in lower or "менеджер" in lower
    assert "15 этап" in lower or "жизненн" in lower or "воронка" in lower
    assert "карточка взаимодействия" in lower or "карточк" in lower
    assert "граф" in lower
    assert "d02" in lower
    assert "доработк" in lower or "комментари" in lower
    assert "вложени" in lower or "файл" in lower or "25 мб" in lower
    assert "audit trail" in lower or "аудит" in lower

    # Supervisor section (Reassign, Reports)
    assert "руководител" in lower or "supervisor" in lower
    assert "reassign" in lower or "переназначени" in lower
    assert "отчёт" in lower or "отчет" in lower or "snapshot" in lower

    # Errors section
    assert "ошибок" in lower or "ac21" in lower or "диагностик" in lower

    # References to screen-01..screen-09, screen-13
    required_screens = [f"screen-{i:02d}" for i in range(1, 10)] + ["screen-13"]
    for screen in required_screens:
        assert screen in content, f"Screenshot {screen} missing from USER_GUIDE.md"


def test_sysadmin_guide_markdown_structure():
    """Checks docs/SYSADMIN_GUIDE.md exists and > 3000 bytes.
    Checks presence of sections for C4 architecture, Docker Compose, Admin Telemetry,
    Import Wizard, Migrator, Webhooks, 152-FZ / FSTEK 117.
    Checks markdown references to screen-10..screen-12, screen-13.
    """
    assert SYSADMIN_GUIDE.is_file(), f"Missing {SYSADMIN_GUIDE}"
    content = SYSADMIN_GUIDE.read_text(encoding="utf-8")
    assert len(content) > 3000, f"SYSADMIN_GUIDE.md too short: {len(content)} characters"

    lower = content.lower()

    # C4 architecture
    assert "c4" in lower

    # Docker Compose
    assert "docker compose" in lower or "compose.yaml" in lower

    # Admin Telemetry
    assert "телеметри" in lower or "дашборд" in lower or "консоль администратора" in lower

    # Import Wizard
    assert "импорт" in lower and ("dry-run" in lower or "сухой прогон" in lower or "preview" in lower)

    # Migrator
    assert "мигратор" in lower or "миграци" in lower

    # Webhooks
    assert "webhook" in lower or "вебхук" in lower or "веб-хук" in lower or "lms_webhook_secret" in lower

    # 152-FZ / FSTEK 117
    assert "152-фз" in lower
    assert "117" in lower

    # References to screen-10..screen-12, screen-13
    required_screens = [f"screen-{i:02d}" for i in range(10, 14)]
    for screen in required_screens:
        assert screen in content, f"Screenshot {screen} missing from SYSADMIN_GUIDE.md"


def test_explanatory_note_updated():
    """Checks links to USER_GUIDE.md and SYSADMIN_GUIDE.md in docs/Пояснительная_записка_...md.
    Checks screenshot references.
    """
    assert EXPLANATORY_NOTE.is_file(), f"Missing explanatory note: {EXPLANATORY_NOTE}"
    content = EXPLANATORY_NOTE.read_text(encoding="utf-8")

    assert "USER_GUIDE.md" in content, "Explanatory note must link to USER_GUIDE.md"
    assert "SYSADMIN_GUIDE.md" in content, "Explanatory note must link to SYSADMIN_GUIDE.md"
    assert "screenshots/screen-" in content, "Explanatory note must contain screenshot image references"

    # Verify at least 10 screenshots are illustrated in the master explanatory note
    referenced_screens = [f"screen-{i:02d}" for i in range(1, 14) if f"screen-{i:02d}" in content]
    assert len(referenced_screens) >= 10, f"Too few screenshots referenced in note: {referenced_screens}"


def test_frontend_help_page_components():
    """Checks frontend/src/views/ReferenceViews.tsx for dual guide mode (USER_GUIDE and SYSADMIN_GUIDE).
    Checks DocScreenshotCard figure with window controls and callouts.
    Checks DocScreenshotLightbox with ESC listener and backdrop dismiss.
    Checks print/export buttons (window.print()).
    Checks 100% preservation of AC21 error simulator.
    """
    assert REFERENCE_VIEWS.is_file(), f"Missing {REFERENCE_VIEWS}"
    content = REFERENCE_VIEWS.read_text(encoding="utf-8")

    # Dual guide mode: USER_GUIDE and SYSADMIN_GUIDE
    assert "USER_GUIDE" in content, "ReferenceViews.tsx must support USER_GUIDE mode"
    assert "SYSADMIN_GUIDE" in content, "ReferenceViews.tsx must support SYSADMIN_GUIDE mode"
    assert "guideSection" in content or "GuideSection" in content, "ReferenceViews.tsx must manage guide mode state"

    # DocScreenshotCard figure with window controls and callouts
    assert "DocScreenshotCard" in content, "ReferenceViews.tsx must define DocScreenshotCard"
    assert "figure" in content, "DocScreenshotCard must render a figure element"
    assert "doc-screenshot-card" in content, "DocScreenshotCard must use .doc-screenshot-card class"
    assert "callout" in content.lower(), "DocScreenshotCard must support callouts"

    # DocScreenshotLightbox with ESC listener and backdrop dismiss
    assert "DocScreenshotLightbox" in content, "ReferenceViews.tsx must define DocScreenshotLightbox"
    assert "Escape" in content or "keyCode === 27" in content, "Lightbox must listen for Escape key"
    assert "backdrop" in content.lower() or "onClose" in content, "Lightbox must support backdrop dismissal"

    # Print / export buttons
    assert "window.print()" in content, "ReferenceViews.tsx must provide native window.print() button"

    # 100% preservation of AC21 error simulator and role tabs
    assert "SIMULATED_ERRORS" in content, "ReferenceViews.tsx must preserve SIMULATED_ERRORS catalog"
    assert "isHelpTabAllowed" in content, "ReferenceViews.tsx must preserve isHelpTabAllowed"
    assert "getInitialTab" in content, "ReferenceViews.tsx must preserve getInitialTab"
    assert "REVISION_CONFLICT" in content, "ReferenceViews.tsx must include REVISION_CONFLICT simulation"


def test_frontend_css_documentation():
    """Checks frontend/src/styles.css for .doc-screenshot-card, .doc-lightbox,
    .callout-badge, .guide-mode-selector, @media print.
    """
    assert STYLES_CSS.is_file(), f"Missing {STYLES_CSS}"
    content = STYLES_CSS.read_text(encoding="utf-8")

    assert ".doc-screenshot-card" in content, "styles.css must contain .doc-screenshot-card rule"
    assert ".doc-lightbox" in content, "styles.css must contain .doc-lightbox rules"
    assert ".callout-badge" in content, "styles.css must contain .callout-badge rule"
    assert ".guide-mode-selector" in content, "styles.css must contain .guide-mode-selector rule"
    assert "@media print" in content, "styles.css must contain @media print rules"


def test_docs_architecture_strictly_readonly():
    """Checks git diff docs/architecture/ produces 0 modified files."""
    diff_res = subprocess.run(
        ["git", "diff", "--name-only", "docs/architecture/"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert diff_res.stdout.strip() == "", f"docs/architecture/ has modified files: {diff_res.stdout}"

    status_res = subprocess.run(
        ["git", "status", "--porcelain", "docs/architecture/"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert status_res.stdout.strip() == "", f"docs/architecture/ is not clean: {status_res.stdout}"


def test_system_oracles_pass():
    """Runs verify_workflow.py, verify_reports.py, verify_plan.py and asserts exit code 0."""
    checks = [
        ROOT / "docs" / "checks" / "verify_workflow.py",
        ROOT / "docs" / "checks" / "verify_reports.py",
        ROOT / "docs" / "checks" / "verify_plan.py",
    ]

    for script in checks:
        assert script.is_file(), f"Missing oracle script: {script}"
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, (
            f"Oracle {script.name} failed with exit code {proc.returncode}:\n"
            f"STDOUT:\n{proc.stdout}\n"
            f"STDERR:\n{proc.stderr}"
        )


def test_fastapi_screenshot_static_mount():
    """Verify FastAPI application serves screenshots via /docs/screenshots mount."""
    app = create_app()
    client = TestClient(app)

    response_01 = client.get("/docs/screenshots/screen-01-login.png")
    assert response_01.status_code == 200, f"Failed to get screen-01: {response_01.status_code}"
    assert response_01.headers["content-type"] == "image/png"
    assert len(response_01.content) > 20000

    response_13 = client.get("/docs/screenshots/screen-13-error-diagnostic-center.png")
    assert response_13.status_code == 200, f"Failed to get screen-13: {response_13.status_code}"
    assert response_13.headers["content-type"] == "image/png"
    assert len(response_13.content) > 20000


def test_nginx_config_static_prefix_priority():
    """Verify deploy/nginx.conf contains high-priority location ^~ /docs/screenshots/."""
    assert NGINX_CONF.is_file(), f"Missing {NGINX_CONF}"
    content = NGINX_CONF.read_text(encoding="utf-8")

    assert "location ^~ /docs/screenshots/" in content, (
        "deploy/nginx.conf must contain location ^~ /docs/screenshots/ to prevent proxying to API"
    )
