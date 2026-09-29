"""Tests for SWE-28: Rostelecom Gen2 Atomaro vector logo & SVG favicon,
role navigation 152-FZ zero-oracle for administrator, and admin system dashboard.
"""
from pathlib import Path
import re
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]


def test_rostelecom_vector_logo_and_brand_component():
    """Verify RostelecomLogo SVG component and Brand in frontend/src/ui.tsx."""
    ui_path = ROOT / "frontend" / "src" / "ui.tsx"
    assert ui_path.is_file(), "ui.tsx must exist"
    content = ui_path.read_text(encoding="utf-8")

    # 1. RostelecomLogo component exists
    assert "export function RostelecomLogo" in content, "RostelecomLogo component must be exported"

    # 2. ViewBox and default size
    assert 'viewBox="0 0 25 40"' in content, "RostelecomLogo must use viewBox='0 0 25 40'"
    assert "size = 28" in content, "RostelecomLogo must default to size 28"

    # 3. Two-tone ribbon colors
    assert "#7700FF" in content, "Upper ribbon body must use #7700FF"
    assert "#FF4F12" in content, "Lower orange fold must use #FF4F12"

    # 4. Brand component uses RostelecomLogo and Gen2 typography
    assert "<RostelecomLogo" in content, "Brand component must render RostelecomLogo"
    assert "Ростелеком" in content, "Brand title must be 'Ростелеком'"
    assert "ИТ Школа · Партнёры" in content, "Brand subtitle must be 'ИТ Школа · Партнёры'"
    assert "brand-text" in content, "Brand must use .brand-text class"


def test_brand_mark_legacy_styles_removed():
    """Verify legacy .brand-mark styles are removed and Gen2 .brand styles exist."""
    css_path = ROOT / "frontend" / "src" / "styles.css"
    ui_path = ROOT / "frontend" / "src" / "ui.tsx"
    css_content = css_path.read_text(encoding="utf-8")
    ui_content = ui_path.read_text(encoding="utf-8")

    # .brand-mark must be completely absent from both CSS and TSX
    assert ".brand-mark" not in css_content, ".brand-mark must be removed from styles.css"
    assert "brand-mark" not in ui_content, "brand-mark must be removed from ui.tsx"

    # Gen2 .brand and .brand-text must be styled, and logo SVG must prevent flex squashing
    assert ".brand" in css_content, ".brand styling must be present"
    assert ".brand-text" in css_content, ".brand-text styling must be present"
    assert ".brand svg" in css_content and "flex-shrink" in css_content, ".brand svg must specify flex-shrink"


def test_browser_svg_favicon_embedded():
    """Verify SVG favicon with Rostelecom official logo is embedded in index.html."""
    html_path = ROOT / "frontend" / "index.html"
    assert html_path.is_file(), "index.html must exist"
    html_content = html_path.read_text(encoding="utf-8")

    # Link tag for SVG favicon
    assert '<link rel="icon" type="image/svg+xml"' in html_content, "SVG favicon link must be present"
    assert "data:image/svg+xml" in html_content, "Favicon must be embedded via data URI"
    assert "viewBox='0 0 25 40'" in html_content, "Favicon SVG must use viewBox='0 0 25 40'"
    # Url-encoded or direct hex colors for Rostelecom ribbon
    assert "%237700FF" in html_content or "#7700FF" in html_content, "Favicon must have #7700FF"
    assert "%23FF4F12" in html_content or "#FF4F12" in html_content, "Favicon must have #FF4F12"


def test_admin_role_navigation_and_152fz_banner():
    """Verify role navigation excludes interactions for administrator and shows 152-FZ banner."""
    app_path = ROOT / "frontend" / "src" / "App.tsx"
    assert app_path.is_file(), "App.tsx must exist"
    app_content = app_path.read_text(encoding="utf-8")

    # Navigation excludes 'interactions' for admin
    assert "const isAdmin = me.role === 'administrator' || me.role === 'admin'" in app_content
    assert "!isAdmin ? [{ code: 'interactions'" in app_content or "code: 'interactions'" in app_content

    # 152-FZ protection banner for direct URL navigation
    required_banner_phrase = (
        "В соответствии со ст. 7 152-ФЗ прямой доступ к клиентским воронкам закреплён за менеджерами и руководителями. "
        "Для настройки системы используйте разделы «Справочники», «Интеграции» и «Отчёты»."
    )
    assert required_banner_phrase in app_content, "Exact 152-FZ protection banner text must be present"
    assert "Вернуться на дашборд" in app_content, "Return to dashboard button must be present"


def test_admin_overview_dashboard_structure():
    """Verify admin overview contains system telemetry and removes empty funnel table."""
    ws_path = ROOT / "frontend" / "src" / "views" / "WorkspaceViews.tsx"
    assert ws_path.is_file(), "WorkspaceViews.tsx must exist"
    ws_content = ws_path.read_text(encoding="utf-8")

    # Empty funnel table stub and commercial funnels must be removed from admin Overview
    assert "Коммерческие воронки изолированы" not in ws_content, (
        "Stub 'Коммерческие воронки изолированы' must be removed from admin Overview"
    )
    assert "ДОСТУПНАЯ ВОРОНКА" not in ws_content, (
        "Commercial funnel 'ДОСТУПНАЯ ВОРОНКА' must be completely removed from admin Overview"
    )
    assert "Этапы сотрудничества (по назначенным организациям)" not in ws_content, (
        "Commercial funnel stages must be completely removed from admin Overview"
    )

    # Required sections in admin dashboard
    assert "Статус системных контуров и каталогов" in ws_content, (
        "Card 'Статус системных контуров и каталогов' must be present"
    )
    assert "Системный журнал действий и импорта" in ws_content, (
        "Block 'Системный журнал действий и импорта' must be present"
    )

    # Verification of LMS, Website, Catalogs (вузы, программы, продукты, договоры), and integration buffer
    assert "Контур LMS Zion" in ws_content
    assert "Контур Сайта ИТ Школы" in ws_content
    assert "Вузы и партнёры" in ws_content
    assert "ИТ-программы" in ws_content
    assert "ИТ-продукты" in ws_content
    assert "Договоры" in ws_content
    assert "Буфер интеграций" in ws_content


def test_backend_api_admin_telemetry_and_zero_oracle(client: TestClient):
    """Verify backend /api/v1/dashboard telemetry for admin and 152-FZ zero oracle isolation."""
    # 1. Administrator receives extended system_stats telemetry
    resp = client.get("/api/v1/dashboard", headers={"X-Demo-User": "administrator"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "system_stats" in data, "Admin must receive system_stats in dashboard"
    stats = data["system_stats"]

    assert stats["total_users"] > 0
    assert stats["total_organizations_catalog"] > 0
    assert stats["total_programs_catalog"] > 0
    assert stats["total_products_catalog"] > 0
    assert "total_contracts_catalog" in stats
    assert "total_inbox_pending" in stats
    assert stats["lms_health_status"] in ("healthy", "ok", "error")
    assert stats["website_health_status"] in ("healthy", "ok", "error")

    # 2. Manager receives NO system_stats
    resp_m = client.get("/api/v1/dashboard", headers={"X-Demo-User": "manager-a"})
    assert resp_m.status_code == 200
    assert "system_stats" not in resp_m.json(), "Manager must not receive admin system_stats"

    # 3. 152-FZ Zero Oracle: Administrator query to /interactions returns 0 commercial cards
    resp_admin_interactions = client.get("/api/v1/interactions", headers={"X-Demo-User": "administrator"})
    assert resp_admin_interactions.status_code == 200
    interactions_data = resp_admin_interactions.json()
    assert interactions_data["total"] == 0, "Admin must see 0 commercial interactions without direct mandate"
    assert len(interactions_data["items"]) == 0


def test_backend_api_integration_health_error_resilience(client: TestClient):
    """Verify backend reports error status when integration adapters raise exceptions."""
    from unittest.mock import patch
    with patch("app.integrations.factory.get_adapter") as mock_get:
        def failing_adapter(source, settings):
            raise ConnectionError(f"Simulated connection failure to {source}")
        mock_get.side_effect = failing_adapter

        resp = client.get("/api/v1/dashboard", headers={"X-Demo-User": "administrator"})
        assert resp.status_code == 200, resp.text
        stats = resp.json()["system_stats"]
        assert stats["lms_health_status"] == "error", "LMS exception must produce error status"
        assert stats["website_health_status"] == "error", "Website exception must produce error status"


def test_admin_dashboard_responsive_classes_and_tone_badges():
    """Verify platform contours and catalog counters use responsive CSS classes and dynamic tone badges."""
    ws_path = ROOT / "frontend" / "src" / "views" / "WorkspaceViews.tsx"
    css_path = ROOT / "frontend" / "src" / "styles.css"
    ws_content = ws_path.read_text(encoding="utf-8")
    css_content = css_path.read_text(encoding="utf-8")

    # WorkspaceViews must use responsive classes
    assert "platform-contours-grid" in ws_content, "Must use platform-contours-grid class"
    assert "platform-catalogs-grid" in ws_content, "Must use platform-catalogs-grid class"

    # Badges must not hardcode tone-green when status is attention/error
    assert "className={'stage-badge ' +" in ws_content, (
        "Status badges must dynamically assign tone classes"
    )

    # Stylesheet must define classes and mobile responsive adaptations
    assert ".platform-contours-grid" in css_content
    assert ".platform-catalogs-grid" in css_content


def test_admin_direct_interaction_url_zero_oracle_protection():
    """Verify App.tsx guards direct URL routing to #/interactions or #/interactions/:id."""
    app_path = ROOT / "frontend" / "src" / "App.tsx"
    assert app_path.is_file(), "App.tsx must exist"
    app_content = app_path.read_text(encoding="utf-8")

    # Ensure isAdmin evaluation strictly gates the interaction block before rendering InteractionPage
    match = re.search(r"activeNav === 'interactions'\s*&&\s*\(\s*isAdmin\s*\?", app_content)
    assert match is not None, "activeNav === 'interactions' must prioritize isAdmin check before interactionId"

    # Ensure return to dashboard button navigates to overview
    assert "navigate('overview')" in app_content


def test_admin_overview_data_loading_guard_covers_lower_panel():
    """Verify admin overview-lower is enclosed inside the {!data ? ... : <> ... </>} guard."""
    ws_path = ROOT / "frontend" / "src" / "views" / "WorkspaceViews.tsx"
    assert ws_path.is_file(), "WorkspaceViews.tsx must exist"
    ws_content = ws_path.read_text(encoding="utf-8")

    # Locate if (isAdmin) branch up to the manager/supervisor return block
    admin_block_match = re.search(
        r"if\s*\(\s*isAdmin\s*\)\s*\{(.*?)\n\s*return\s*<>\s*<PageHeader\s*eyebrow=\{'РАБОЧИЙ ОБЗОР",
        ws_content,
        re.DOTALL,
    )
    assert admin_block_match is not None, "Admin block must exist in Overview"
    admin_body = admin_block_match.group(1)

    # In the admin block, the overview-lower div must appear before the closing </Fragment>} </>;
    lower_idx = admin_body.find('className="overview-lower"')
    guard_close_idx = admin_body.find('</>}')
    assert lower_idx != -1, "overview-lower must be in admin overview"
    assert guard_close_idx != -1, "guard closing '</>}' must be present in admin overview"
    assert lower_idx < guard_close_idx, (
        "overview-lower must appear BEFORE '</>}' to prevent rendering uninitialized stats during loading"
    )


def test_admin_dashboard_tablet_responsive_adaptations():
    """Verify tablet breakpoint includes platform monitor grids for 768px-1023px viewport fidelity."""
    css_path = ROOT / "frontend" / "src" / "styles.css"
    css_content = css_path.read_text(encoding="utf-8")

    tablet_match = re.search(
        r"@media\s*\(\s*min-width:\s*768px\s*\)\s*and\s*\(\s*max-width:\s*1023px\s*\)\s*\{(.*?)\}\s*\n\s*/\*\s*Mobile",
        css_content,
        re.DOTALL,
    )
    assert tablet_match is not None, "Tablet media query must exist in styles.css"
    tablet_rules = tablet_match.group(1)

    assert ".platform-contours-grid" in tablet_rules, "Tablet rules must adapt .platform-contours-grid"
    assert ".platform-catalogs-grid" in tablet_rules, "Tablet rules must adapt .platform-catalogs-grid"


def test_all_roles_navigation_matrix():
    """Verify role navigation invariants across manager, supervisor, and administrator."""
    app_path = ROOT / "frontend" / "src" / "App.tsx"
    app_content = app_path.read_text(encoding="utf-8")

    # Invariants in App.tsx navigation declaration:
    # 1. Overview is available to all
    # 2. Interactions is available only when !isAdmin
    # 3. Integrations is available when isPrivileged (supervisor or admin)
    # 4. Reports, Catalogs, Help available to all
    assert "code: 'overview'" in app_content
    assert "!isAdmin ? [{ code: 'interactions'" in app_content
    assert "isPrivileged ? [{ code: 'integrations'" in app_content
    assert "code: 'reports'" in app_content
    assert "code: 'catalogs'" in app_content
    assert "code: 'help'" in app_content



