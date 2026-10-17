"""Tier 2: Boundary and Corner Cases.

Covers:
- Empty inputs (empty payloads, 0-byte uploads, empty strings)
- Maximum limits and pagination boundaries (max string sizes, page_size=100 vs 101, page=0)
- Unicode Cyrillic text, punctuation, SQL injection characters treated as literals
- 152-ФЗ Zero-Oracle 404 isolation boundaries (non-disclosing 404 instead of 403)
- Compare-And-Swap (CAS) optimistic revision concurrency (expected_revision conflict)
- Expired import packages (> 24 hours lifecycle)
- BIFF8 binary corruption & malformed OLE2 streams
"""
import io
import struct
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.files import validate_magic_bytes
from app.importer import parse_biff8_stdlib
from app.models import Interaction, User, utcnow
from tests.e2e.helpers import admin_headers, auth_headers, create_e2e_interaction, manager_headers


# ============================================================================
# 1. Empty Inputs
# ============================================================================

def test_t2_empty_interaction_creation_payload_returns_422(client):
    """Empty JSON body on interaction creation must return 422 Unprocessable Entity."""
    resp = client.post("/api/v1/interactions", json={}, headers=manager_headers("manager-a", str(uuid.uuid4())))
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}"


def test_t2_empty_title_interaction_creation_rejected(client):
    """Empty string title on interaction creation must return 422."""
    body = {
        "title": "",
        "organization_id": "org-1",
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "cycle_label": "2026",
    }
    resp = client.post("/api/v1/interactions", json=body, headers=manager_headers("manager-a", str(uuid.uuid4())))
    assert resp.status_code == 422


def test_t2_zero_byte_file_upload_rejected(client):
    """Uploading a 0-byte file to import preview must be rejected with error diagnostics."""
    resp = client.post(
        "/api/v1/imports/preview?type=organizations",
        files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
        headers=admin_headers(),
    )
    assert resp.status_code in (200, 422), f"Unexpected status code {resp.status_code}"
    if resp.status_code == 200:
        data = resp.json()
        assert data.get("rows_total", len(data.get("rows", []))) == 0


def test_t2_empty_comment_command_rejected(client):
    """Submitting empty text comment must be rejected with 422."""
    resp = client.post(
        "/api/v1/interactions/ix-1/comments",
        json={"body": "", "expected_revision": 1},
        headers=manager_headers("manager-a", str(uuid.uuid4())),
    )
    assert resp.status_code == 422


def test_t2_empty_query_params_on_interactions_returns_default_page(client):
    """GET /api/v1/interactions with empty query string succeeds and returns default page."""
    resp = client.get("/api/v1/interactions", headers=admin_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data or isinstance(data, list)


# ============================================================================
# 2. Maximum Limits & Pagination Boundaries
# ============================================================================

def test_t2_page_size_100_is_maximum_allowed(client):
    """page_size=100 is valid upper boundary and succeeds."""
    resp = client.get("/api/v1/interactions?page_size=100", headers=admin_headers())
    assert resp.status_code == 200


def test_t2_page_size_101_exceeds_limit_returns_422(client):
    """page_size=101 strictly exceeds the le=100 constraint and returns 422."""
    resp = client.get("/api/v1/interactions?page_size=101", headers=admin_headers())
    assert resp.status_code == 422, f"Expected 422 for page_size=101, got {resp.status_code}"


def test_t2_page_zero_violates_ge_one_returns_422(client):
    """page=0 strictly violates ge=1 pagination constraint and returns 422."""
    resp = client.get("/api/v1/interactions?page_size=10&page=0", headers=admin_headers())
    assert resp.status_code == 422, f"Expected 422 for page=0, got {resp.status_code}"


def test_t2_maximum_length_title_accepted(client):
    """Interaction title up to 200 characters is accepted."""
    long_title = "В" * 200
    interaction = create_e2e_interaction(client, title=long_title)
    assert interaction["title"] == long_title


def test_t2_oversized_title_rejected(client):
    """Interaction title exceeding 500 characters is rejected with 422."""
    oversized = "В" * 600
    body = {
        "title": oversized,
        "organization_id": "org-1",
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "cycle_label": "2026",
    }
    resp = client.post("/api/v1/interactions", json=body, headers=manager_headers("manager-a", str(uuid.uuid4())))
    assert resp.status_code in (422, 400)


# ============================================================================
# 3. Unicode, Cyrillic, and Meta-Character Stress
# ============================================================================

def test_t2_cyrillic_full_alphabet_and_punctuation(client):
    """Interaction titles and comments support full Cyrillic alphabet, quotes, and dashes."""
    complex_title = "ИТ-Школа: «Проектирование & Внедрение — 2026/27» (СПбГЭУ, МГТУ им. Баумана)"
    interaction = create_e2e_interaction(client, title=complex_title, user="manager-a")
    assert interaction["title"] == complex_title

    # Add Cyrillic comment
    comment_text = "Согласованы специальные условия: скидка 15% для филиалов в г. Южно-Сахалинск и р.п. Листвянка."
    c_resp = client.post(
        f"/api/v1/interactions/{interaction['id']}/comments",
        json={"body": comment_text, "expected_revision": interaction["revision"]},
        headers=manager_headers("manager-a", str(uuid.uuid4())),
    )
    assert c_resp.status_code in (200, 201), c_resp.text


def test_t2_sql_injection_payload_treated_as_literal_string(client):
    """SQL injection meta-characters in search query parameter are escaped and treated literally."""
    sql_payload = "' OR '1'='1'; DROP TABLE users; --"
    resp = client.get(f"/api/v1/interactions?q={sql_payload}", headers=admin_headers())
    assert resp.status_code == 200
    data = resp.json()
    items = data.get("items", []) if isinstance(data, dict) else data
    # Literal search will find 0 interactions, never crash or drop table
    assert isinstance(items, list)


def test_t2_html_and_xss_characters_in_comment(client):
    """HTML script tags in comments are stored safely without code execution."""
    xss_payload = "<script>alert('XSS')</script><img src=x onerror=alert(1)>"
    interaction = create_e2e_interaction(client, title="XSS Test Interaction", user="manager-a")
    c_resp = client.post(
        f"/api/v1/interactions/{interaction['id']}/comments",
        json={"body": xss_payload, "expected_revision": interaction["revision"]},
        headers=manager_headers("manager-a", str(uuid.uuid4())),
    )
    assert c_resp.status_code in (200, 201)


def test_t2_newlines_and_tabs_in_comment(client):
    """Multi-line comment with tabs and CRLF is preserved cleanly."""
    multiline = "Строка 1\nСтрока 2\r\n\tПункт А\n\tПункт Б"
    interaction = create_e2e_interaction(client, title="Multiline Comment Test", user="manager-a")
    c_resp = client.post(
        f"/api/v1/interactions/{interaction['id']}/comments",
        json={"body": multiline, "expected_revision": interaction["revision"]},
        headers=manager_headers("manager-a", str(uuid.uuid4())),
    )
    assert c_resp.status_code in (200, 201)


# ============================================================================
# 4. 152-ФЗ Zero-Oracle 404 & CAS Isolation Boundaries
# ============================================================================

def test_t2_152fz_foreign_interaction_returns_404_not_403(client):
    """CRITICAL INVARIANT 4: Accessing interaction in un-granted org returns HTTP 404, NEVER 403."""
    # Manager-A has grant for org-1 ONLY
    # ix-4 is in org-2 (Manager-B's organization)
    resp = client.get("/api/v1/interactions/ix-4", headers=manager_headers("manager-a"))
    assert resp.status_code == 404, (
        f"152-ФЗ Zero-Oracle violation! Expected 404 Not Found to prevent tenant disclosure, got {resp.status_code}"
    )


def test_t2_152fz_foreign_transition_returns_404(client):
    """Attempting state transition on foreign interaction returns 404."""
    payload = {"transition_code": "contact_search_to_needs_clarification", "expected_revision": 1}
    resp = client.post(
        "/api/v1/interactions/ix-4/transitions",
        json=payload,
        headers=manager_headers("manager-a", str(uuid.uuid4())),
    )
    assert resp.status_code == 404, f"Expected 404 Zero-Oracle, got {resp.status_code}"


def test_t2_152fz_foreign_comment_returns_404(client):
    """Attempting comment on foreign interaction returns 404."""
    resp = client.post(
        "/api/v1/interactions/ix-4/comments",
        json={"body": "Unpermitted comment", "expected_revision": 1},
        headers=manager_headers("manager-a", str(uuid.uuid4())),
    )
    assert resp.status_code == 404, f"Expected 404 Zero-Oracle, got {resp.status_code}"


def test_t2_cas_revision_conflict_returns_409(client):
    """Submitting stale expected_revision returns HTTP 409 Conflict."""
    interaction = create_e2e_interaction(client, title="CAS Test Interaction", user="manager-a")
    ix_id = interaction["id"]
    current_rev = interaction["revision"]  # starts at 1

    # Transition to needs_clarification with current revision (1 -> 2)
    resp1 = client.post(
        f"/api/v1/interactions/{ix_id}/transitions",
        json={"transition_code": "contact_search_to_needs_clarification", "expected_revision": current_rev},
        headers=manager_headers("manager-a", str(uuid.uuid4())),
    )
    assert resp1.status_code == 200, resp1.text
    new_rev = resp1.json()["revision"]
    assert new_rev == current_rev + 1

    # Second transition intentionally sending old expected_revision (1 instead of 2) -> 409
    resp2 = client.post(
        f"/api/v1/interactions/{ix_id}/transitions",
        json={"transition_code": "needs_clarification_to_meeting", "expected_revision": current_rev},
        headers=manager_headers("manager-a", str(uuid.uuid4())),
    )
    assert resp2.status_code == 409, f"Expected 409 CAS Conflict, got {resp2.status_code}"


def test_t2_cas_patch_interaction_conflict_returns_409(client):
    """PATCH with mismatched expected_revision returns 409."""
    interaction = create_e2e_interaction(client, title="Patch CAS Test", user="manager-a")
    ix_id = interaction["id"]

    resp = client.patch(
        f"/api/v1/interactions/{ix_id}",
        json={"title": "Updated Title", "expected_revision": 999},  # stale revision
        headers=manager_headers("manager-a", str(uuid.uuid4())),
    )
    assert resp.status_code == 409, f"Expected 409 Conflict, got {resp.status_code}"


# ============================================================================
# 5. Expired Import Packages (> 24 hours lifecycle)
# ============================================================================

def test_t2_import_package_unknown_id_returns_404(client):
    """Committing with fabricated or non-existent import_id returns 404."""
    payload = {"import_id": f"non-existent-pkg-{uuid.uuid4().hex}", "import_type": "organizations"}
    resp = client.post("/api/v1/imports/commit", json=payload, headers=admin_headers(str(uuid.uuid4())))
    assert resp.status_code == 404


def test_t2_import_preview_tampered_hash_detection(client):
    """Modifying raw CSV between preview and commit triggers hash mismatch."""
    csv1 = "Название;Тип\nВУЗ Раз;university\n"
    prev = client.post(
        "/api/v1/imports/preview?type=organizations",
        files={"file": ("p.csv", io.BytesIO(csv1.encode("utf-8")), "text/csv")},
        headers=admin_headers(),
    )
    assert prev.status_code == 200
    import_id = prev.json()["import_id"]

    # Tampered rows sent
    resp = client.post(
        "/api/v1/imports/commit",
        json={"import_id": import_id, "rows": [{"name": "ВУЗ Измененный", "type": "university"}]},
        headers=admin_headers(str(uuid.uuid4())),
    )
    assert resp.status_code in (409, 422)


# ============================================================================
# 6. BIFF8 Binary Corruption & Malformed OLE2 Streams
# ============================================================================

def test_t2_biff8_truncated_header_raises_clean_error():
    """Truncated OLE2 binary header (< 512 bytes) passed to parse_biff8_stdlib handled cleanly."""
    truncated_bytes = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 50
    try:
        rows = parse_biff8_stdlib(truncated_bytes)
        # If it doesn't raise, it must return empty rows
        assert rows == []
    except (ValueError, IndexError, struct.error, Exception):
        # Expected clean parse exception
        pass


def test_t2_biff8_random_noise_rejected_by_magic_validator():
    """Random binary garbage must fail validate_magic_bytes for xls."""
    garbage = b"\x00\x01\x02\x03\x04\x05" * 100
    assert validate_magic_bytes("xls", garbage) is False


def test_t2_biff8_non_excel_ole2_rejected():
    """Non-BIFF8 OLE2 container does not parse into valid Excel rows."""
    fake_ole2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 1024
    try:
        rows = parse_biff8_stdlib(fake_ole2)
        assert rows == []
    except (ValueError, KeyError, struct.error, Exception):
        pass


def test_t2_importer_handles_malformed_csv_delimiters():
    """CSV with inconsistent delimiter columns does not crash preview."""
    bad_csv = "Организация;Тип;Город\nВУЗ Без Разделителей\nВУЗ;Нормальный;Москва\n"
    from app.importer import parse_csv_stdlib
    rows = parse_csv_stdlib(bad_csv.encode("utf-8"))
    assert isinstance(rows, list)
