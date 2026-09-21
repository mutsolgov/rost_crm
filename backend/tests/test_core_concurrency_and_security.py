"""Core Concurrency, Security Invariants, and Workflow Boundary Test Suite.

R3 QA Automation, Concurrency Stress-testing & Pre-Defense Audit.
Enforces:
1. Parallel CAS race conditions under high concurrency (20 threads with ThreadPoolExecutor).
2. 152-FZ / FSTEK 117 Scope isolation and strict HTTP 404 Not Found (never 403).
3. Idempotency-Key caching, replay consistency, and zero side-effect duplication.
4. Workflow boundary and illegal state transition rejection (HTTP 422 / 409).
5. Formula injection sanitization (=, +, -, @) in spreadsheet exports.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import io
from uuid import uuid4
import zipfile

import pytest


def headers(user="manager-a", key=None):
    res = {"X-Demo-User": user}
    if key:
        res["Idempotency-Key"] = key
    return res


def create_interaction(client, user="manager-a", **overrides):
    org_id = "org-2" if user == "manager-b" else "org-1"
    body = {
        "title": "Тестовое взаимодействие",
        "organization_id": org_id,
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "cycle_label": "2026-Стресс",
        "owner_id": user,
    }
    body.update(overrides)
    res = client.post("/api/v1/interactions", json=body, headers=headers(user, str(uuid4())))
    assert res.status_code == 201, res.text
    return res.json()


def get_detail(client, interaction_id, user="manager-a"):
    res = client.get(f"/api/v1/interactions/{interaction_id}", headers=headers(user))
    return res


# ==============================================================================
# Test 1: Parallel CAS race condition (20 concurrent threads)
# ==============================================================================

def test_cas_concurrency_parallel_race_twenty_threads_patch(client):
    """Simulate 20 concurrent PATCH requests with identical expected_revision.

    Verifies CAS optimistic locking:
    - Exactly 1 request succeeds (HTTP 200).
    - Exactly 19 requests receive HTTP 409 Conflict with REVISION_CONFLICT code.
    - Database state reflects exactly 1 revision increment and 1 event.
    """
    card = create_interaction(client, user="manager-a", title="Initial Card for CAS Race")
    card_id = card["id"]
    initial_revision = card["revision"]

    def worker(thread_idx):
        return client.patch(
            f"/api/v1/interactions/{card_id}",
            json={
                "expected_revision": initial_revision,
                "cycle_label": f"Thread-Worker-{thread_idx}",
            },
            headers=headers("manager-a", str(uuid4())),
        )

    with ThreadPoolExecutor(max_workers=20) as executor:
        responses = list(executor.map(worker, range(20)))

    status_codes = [r.status_code for r in responses]
    success_count = status_codes.count(200)
    conflict_count = status_codes.count(409)

    assert success_count == 1, f"Expected exactly 1 success, got {success_count} ({status_codes})"
    assert conflict_count == 19, f"Expected exactly 19 conflicts, got {conflict_count} ({status_codes})"

    for resp in responses:
        if resp.status_code == 409:
            data = resp.json()
            assert data["error"]["code"] == "REVISION_CONFLICT"
            assert "Карточка изменена" in data["error"]["message"]

    # Verify updated card integrity
    detail_res = get_detail(client, card_id, "manager-a")
    assert detail_res.status_code == 200
    updated_card = detail_res.json()
    assert updated_card["revision"] == initial_revision + 1

    # Exactly 1 attributes_corrected event was logged
    patch_events = [e for e in updated_card["events"] if e["type"] == "attributes_corrected"]
    assert len(patch_events) == 1


def test_cas_concurrency_parallel_race_twenty_threads_transition(client):
    """Simulate 20 concurrent transition requests with identical expected_revision.

    Verifies CAS optimistic locking during state machine execution:
    - Exactly 1 request succeeds (HTTP 200).
    - Exactly 19 requests receive HTTP 409 Conflict with REVISION_CONFLICT code.
    - State transitioned cleanly to needs_clarification.
    """
    card = create_interaction(client, user="manager-a", title="Transition CAS Race Card")
    card_id = card["id"]
    initial_revision = card["revision"]
    assert card["state"] == "contact_search"

    def worker(thread_idx):
        return client.post(
            f"/api/v1/interactions/{card_id}/transitions",
            json={
                "transition_code": "contact_search_to_needs_clarification",
                "expected_revision": initial_revision,
                "comment": f"Параллельный переход поток {thread_idx}",
            },
            headers=headers("manager-a", str(uuid4())),
        )

    with ThreadPoolExecutor(max_workers=20) as executor:
        responses = list(executor.map(worker, range(20)))

    status_codes = [r.status_code for r in responses]
    assert status_codes.count(200) == 1, f"Expected 1 200 OK, got {status_codes.count(200)}"
    assert status_codes.count(409) == 19, f"Expected 19 409 Conflicts, got {status_codes.count(409)}"

    # Check state and events
    detail_res = get_detail(client, card_id, "manager-a").json()
    assert detail_res["state"] == "needs_clarification"
    assert detail_res["revision"] == initial_revision + 1

    state_changed_events = [e for e in detail_res["events"] if e["type"] == "state_changed"]
    assert len(state_changed_events) == 1


# ==============================================================================
# Test 2: Scope isolation and strict HTTP 404 Not Found (never 403)
# ==============================================================================

def test_scope_isolation_manager_cross_access_strict_404(client):
    """152-FZ and FSTEK 117 strict isolation invariant.

    Manager A attempting to access, download from, comment on, patch, or transition
    Manager B's interaction MUST receive strict HTTP 404 Not Found (never 403 Forbidden).
    This hides the existence of unauthorized records.
    """
    # Manager B creates interaction in org-2
    card_b = create_interaction(client, user="manager-b", title="Конфиденциальная карточка Менеджера Б")
    card_b_id = card_b["id"]

    # Manager B uploads an attachment
    fake_pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>%%EOF"
    upload_res = client.post(
        f"/api/v1/interactions/{card_b_id}/attachments",
        files={"file": ("confidential.pdf", fake_pdf, "application/pdf")},
        headers=headers("manager-b"),
    )
    assert upload_res.status_code == 201, upload_res.text
    attachment_id = upload_res.json()["id"]

    # 1. Detail access by Manager A -> Strict 404
    r_detail = client.get(f"/api/v1/interactions/{card_b_id}", headers=headers("manager-a"))
    assert r_detail.status_code == 404
    assert r_detail.json()["error"]["code"] == "NOT_FOUND"

    # 2. Attachment download by Manager A -> Strict 404
    r_download = client.get(
        f"/api/v1/interactions/{card_b_id}/attachments/{attachment_id}/download",
        headers=headers("manager-a"),
    )
    assert r_download.status_code == 404
    assert r_download.json()["error"]["code"] == "NOT_FOUND"

    # 3. Add comment by Manager A -> Strict 404
    r_comment = client.post(
        f"/api/v1/interactions/{card_b_id}/comments",
        json={"expected_revision": 1, "body": "Несанкционированный комментарий"},
        headers=headers("manager-a", str(uuid4())),
    )
    assert r_comment.status_code == 404
    assert r_comment.json()["error"]["code"] == "NOT_FOUND"

    # 4. Patch by Manager A -> Strict 404
    r_patch = client.patch(
        f"/api/v1/interactions/{card_b_id}",
        json={"expected_revision": 1, "title": "Взлом названия"},
        headers=headers("manager-a", str(uuid4())),
    )
    assert r_patch.status_code == 404
    assert r_patch.json()["error"]["code"] == "NOT_FOUND"

    # 5. Transition by Manager A -> Strict 404
    r_trans = client.post(
        f"/api/v1/interactions/{card_b_id}/transitions",
        json={"transition_code": "contact_search_to_needs_clarification", "expected_revision": 1},
        headers=headers("manager-a", str(uuid4())),
    )
    assert r_trans.status_code == 404
    assert r_trans.json()["error"]["code"] == "NOT_FOUND"


def test_scope_isolation_after_reassignment_strict_404(client):
    """When a card is reassigned to another manager, previous owner immediately loses access (404)."""
    # Manager A creates card
    card = create_interaction(client, user="manager-a", title="Карточка для переназначения")
    card_id = card["id"]

    # Confirm Manager A can access it
    assert client.get(f"/api/v1/interactions/{card_id}", headers=headers("manager-a")).status_code == 200

    # Supervisor reassigns card to Manager B
    reassign_res = client.post(
        f"/api/v1/interactions/{card_id}/assignments",
        json={"expected_revision": card["revision"], "owner_id": "manager-b", "reason": "Передача другому менеджеру"},
        headers=headers("supervisor", str(uuid4())),
    )
    assert reassign_res.status_code == 200

    # Manager A now receives strict 404
    r_lost = client.get(f"/api/v1/interactions/{card_id}", headers=headers("manager-a"))
    assert r_lost.status_code == 404
    assert r_lost.json()["error"]["code"] == "NOT_FOUND"


# ==============================================================================
# Test 3: Idempotency-Key caching and side-effect guarantees
# ==============================================================================

def test_idempotency_caching_and_replay_without_side_effects(client):
    """Replaying requests with the same Idempotency-Key returns cached response with 0 side effects."""
    card = create_interaction(client, user="manager-a", title="Idempotency Test Card")
    card_id = card["id"]
    rev = card["revision"]
    idem_key = f"idem-key-{uuid4()}"

    patch_payload = {
        "expected_revision": rev,
        "title": "Обновленный заголовок карточки",
        "cycle_label": "2026-Идемпотентность",
    }

    # First request -> 200 OK
    res1 = client.patch(
        f"/api/v1/interactions/{card_id}",
        json=patch_payload,
        headers=headers("manager-a", idem_key),
    )
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["revision"] == rev + 1
    assert data1["title"] == "Обновленный заголовок карточки"

    # Second request with EXACT same key and payload -> Returns cached response (200 OK)
    res2 = client.patch(
        f"/api/v1/interactions/{card_id}",
        json=patch_payload,
        headers=headers("manager-a", idem_key),
    )
    assert res2.status_code == 200
    assert res2.json() == data1

    # Third request -> Returns cached response (200 OK)
    res3 = client.patch(
        f"/api/v1/interactions/{card_id}",
        json=patch_payload,
        headers=headers("manager-a", idem_key),
    )
    assert res3.status_code == 200
    assert res3.json() == data1

    # Verify no duplicate events or double revision increment
    card_detail = get_detail(client, card_id, "manager-a").json()
    assert card_detail["revision"] == rev + 1
    corrected_events = [e for e in card_detail["events"] if e["type"] == "attributes_corrected"]
    assert len(corrected_events) == 1

    # Submitting a DIFFERENT payload with the SAME key -> 409 IDEMPOTENCY_CONFLICT
    res_conflict = client.patch(
        f"/api/v1/interactions/{card_id}",
        json={"expected_revision": rev + 1, "title": "Совершенно другой заголовок"},
        headers=headers("manager-a", idem_key),
    )
    assert res_conflict.status_code == 409
    assert res_conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    # Missing or empty Idempotency-Key -> 422 VALIDATION_ERROR
    res_missing = client.patch(
        f"/api/v1/interactions/{card_id}",
        json={"expected_revision": rev + 1, "title": "Без ключа"},
        headers=headers("manager-a"),  # no key
    )
    assert res_missing.status_code == 422
    assert res_missing.json()["error"]["code"] == "VALIDATION_ERROR"


# ==============================================================================
# Test 4: Workflow boundary / illegal transitions
# ==============================================================================

def test_workflow_illegal_transition_rejections(client):
    """Verify that workflow boundaries and illegal transitions are rejected with HTTP 422 or 409."""
    # 1. Card created without program and product
    card = create_interaction(client, user="manager-a", program_id=None, product_id=None)
    card_id = card["id"]

    # Transition up to document_signing
    for t_code in [
        "contact_search_to_needs_clarification",
        "needs_clarification_to_meeting",
        "meeting_to_document_exchange",
        "document_exchange_to_document_signing",
    ]:
        res = client.post(
            f"/api/v1/interactions/{card_id}/transitions",
            json={"transition_code": t_code, "expected_revision": card["revision"]},
            headers=headers("manager-a", str(uuid4())),
        )
        assert res.status_code == 200
        card = res.json()

    assert card["state"] == "document_signing"

    # 2. Attempting transition to materials_transfer without program/product -> HTTP 422
    res_blocked = client.post(
        f"/api/v1/interactions/{card_id}/transitions",
        json={"transition_code": "document_signing_to_materials_transfer", "expected_revision": card["revision"]},
        headers=headers("manager-a", str(uuid4())),
    )
    assert res_blocked.status_code == 422
    assert res_blocked.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "Перед этим этапом укажите ИТ-программу и ИТ-продукт" in res_blocked.json()["error"]["message"]

    # 3. Cancellation transition requires non-empty comment -> HTTP 422 if empty or whitespace
    res_cancel_empty = client.post(
        f"/api/v1/interactions/{card_id}/transitions",
        json={"transition_code": "document_signing_to_cancelled", "expected_revision": card["revision"], "comment": "   "},
        headers=headers("manager-a", str(uuid4())),
    )
    assert res_cancel_empty.status_code == 422
    assert res_cancel_empty.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "нужен комментарий" in res_cancel_empty.json()["error"]["message"]

    # Cancel with valid comment -> succeeds
    res_cancel = client.post(
        f"/api/v1/interactions/{card_id}/transitions",
        json={"transition_code": "document_signing_to_cancelled", "expected_revision": card["revision"], "comment": "Отмена по решению вуза"},
        headers=headers("manager-a", str(uuid4())),
    )
    assert res_cancel.status_code == 200
    cancelled_card = res_cancel.json()
    assert cancelled_card["state"] == "cancelled"

    # 4. Attempting any transition from a terminal state (cancelled) -> rejected
    res_terminal_trans = client.post(
        f"/api/v1/interactions/{card_id}/transitions",
        json={"transition_code": "contact_search_to_needs_clarification", "expected_revision": cancelled_card["revision"]},
        headers=headers("manager-a", str(uuid4())),
    )
    assert res_terminal_trans.status_code in (409, 422)

    # 5. Out-of-order transition (skip steps) on fresh card -> HTTP 409 TRANSITION_NOT_ALLOWED
    fresh_card = create_interaction(client, user="manager-a", title="Fresh Card")
    res_skip = client.post(
        f"/api/v1/interactions/{fresh_card['id']}/transitions",
        json={"transition_code": "document_signing_to_materials_transfer", "expected_revision": fresh_card["revision"]},
        headers=headers("manager-a", str(uuid4())),
    )
    assert res_skip.status_code in (409, 422)

    # 6. Malformed payload (missing expected_revision) -> HTTP 422
    res_malformed = client.post(
        f"/api/v1/interactions/{fresh_card['id']}/transitions",
        json={"transition_code": "contact_search_to_needs_clarification"},
        headers=headers("manager-a", str(uuid4())),
    )
    assert res_malformed.status_code == 422
    assert res_malformed.json()["error"]["code"] == "VALIDATION_ERROR"


# ==============================================================================
# Test 5: Formula injection escaping (=, +, -, @)
# ==============================================================================

def test_formula_injection_escaping_in_reports(client):
    """Verify that spreadsheet formula injection characters (=, +, -, @) are safely escaped with ' in XLSX exports."""
    payloads = [
        "=CMD|' /C calc'!A0",
        "+SUM(100, 200)",
        "-123456*99",
        "@AVERAGE(A1:Z100)",
    ]

    for formula_str in payloads:
        create_interaction(
            client,
            user="manager-a",
            title=formula_str,
            cycle_label=f"Cycle {formula_str}",
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    export_req = {"as_of": now_iso, "knowledge_cutoff": now_iso}

    resp = client.post(
        "/api/v1/reports/snapshot/export?format=xlsx",
        json=export_req,
        headers=headers("supervisor"),
    )
    assert resp.status_code == 200
    assert resp.content.startswith(b"PK\x03\x04")

    # Inspect the zipped XML sheet content
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        sheet_xml = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")

        # Crucial security invariants:
        # 1. No executable formula elements (<f> tags)
        assert "<f>" not in sheet_xml
        # 2. All strings stored as inlineStr
        assert 't="inlineStr"' in sheet_xml

        # 3. Every formula character was escaped with single quote '
        for formula_str in payloads:
            escaped_val = f"'{formula_str}"
            assert escaped_val in sheet_xml, f"Failed to find escaped '{formula_str}' in sheet1.xml"


def test_formula_injection_escaping_in_csv_export(client):
    """Verify that spreadsheet formula injection characters (=, +, -, @) are safely escaped with ' in CSV exports."""
    payloads = [
        "=HYPERLINK(\"http://evil.com\",\"Click\")",
        "+cmd|' /C notepad'!A0",
        "-9999*88",
        "@SUM(1,2)",
        "   =TRIM(A1)",
    ]

    for formula_str in payloads:
        create_interaction(
            client,
            user="manager-a",
            title=formula_str,
            cycle_label="CSV-Formula-Test",
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    export_req = {"as_of": now_iso, "knowledge_cutoff": now_iso}

    resp = client.post(
        "/api/v1/reports/snapshot/export?format=csv",
        json=export_req,
        headers=headers("supervisor"),
    )
    assert resp.status_code == 200
    assert resp.headers["X-Report-Format"] == "csv"
    assert "text/csv" in resp.headers["Content-Type"]

    import csv
    csv_content = resp.content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(csv_content))
    csv_rows = list(reader)
    title_idx = csv_rows[0].index("Название")
    titles = [row[title_idx] for row in csv_rows[1:]]

    for formula_str in payloads:
        expected_title = f"'{formula_str.strip()}"
        assert expected_title in titles, f"Expected '{expected_title}' to be in CSV titles: {titles}"


def test_file_security_path_traversal_null_bytes_and_oracle_defense(client):
    """Verify Path Traversal, null-byte rejection, and zero-oracle foreign upload isolation."""
    card_a = create_interaction(client, user="manager-a", title="Card A for File Security")
    card_b = create_interaction(client, user="manager-b", title="Card B for File Security")
    card_a_id = card_a["id"]
    card_b_id = card_b["id"]

    valid_pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>%%EOF"
    bad_exe = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00"

    # 1. Backslash path traversal on own card -> sanitized to basename
    resp_bs = client.post(
        f"/api/v1/interactions/{card_a_id}/attachments",
        files={"file": (r"..\..\..\..\windows\system32\important.pdf", valid_pdf, "application/pdf")},
        headers=headers("manager-a"),
    )
    assert resp_bs.status_code == 201
    assert resp_bs.json()["file_name"] == "important.pdf"

    # 2. Null-byte in filename -> rejected with 422
    resp_null = client.post(
        f"/api/v1/interactions/{card_a_id}/attachments",
        files={"file": ("malware.pdf\x00.exe", valid_pdf, "application/pdf")},
        headers=headers("manager-a"),
    )
    assert resp_null.status_code == 422
    assert resp_null.json()["error"]["code"] == "FILE_TYPE_NOT_ALLOWED"

    # 3. Manager A attempts to upload invalid file (bad_exe) to Manager B's card -> Strict 404 NOT_FOUND!
    # Crucial 152-FZ / FSTEK oracle prevention: do NOT reveal 422 or 413 on foreign card!
    resp_oracle_type = client.post(
        f"/api/v1/interactions/{card_b_id}/attachments",
        files={"file": ("exploit.exe", bad_exe, "application/octet-stream")},
        headers=headers("manager-a"),
    )
    assert resp_oracle_type.status_code == 404
    assert resp_oracle_type.json()["error"]["code"] == "NOT_FOUND"

    # 4. Manager A attempts to upload oversized file (>25MB) to Manager B's card -> Strict 404 NOT_FOUND!
    oversized = valid_pdf + b"0" * (26_214_400 + 10)
    resp_oracle_size = client.post(
        f"/api/v1/interactions/{card_b_id}/attachments",
        files={"file": ("huge.pdf", oversized, "application/pdf")},
        headers=headers("manager-a"),
    )
    assert resp_oracle_size.status_code == 404
    assert resp_oracle_size.json()["error"]["code"] == "NOT_FOUND"

    # 5. Manager A uploads oversized file to OWN card -> 413 FILE_TOO_LARGE
    resp_own_oversized = client.post(
        f"/api/v1/interactions/{card_a_id}/attachments",
        files={"file": ("huge.pdf", oversized, "application/pdf")},
        headers=headers("manager-a"),
    )
    assert resp_own_oversized.status_code == 413
    assert resp_own_oversized.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_frontend_jwt_in_memory_audit():
    """Verify that frontend codebase never persists JWT tokens to localStorage or sessionStorage."""
    from pathlib import Path
    frontend_src = Path(__file__).resolve().parent.parent.parent / "frontend" / "src"
    assert frontend_src.is_dir(), f"Frontend src not found at {frontend_src}"

    # Scan all ts, tsx, js files
    for file_path in frontend_src.rglob("*"):
        if file_path.suffix in (".ts", ".tsx", ".js"):
            content = file_path.read_text(encoding="utf-8")
            # Check that localStorage.setItem or sessionStorage.setItem is never called
            assert "localStorage.setItem" not in content, f"Forbidden localStorage.setItem found in {file_path}"
            assert "sessionStorage.setItem" not in content, f"Forbidden sessionStorage.setItem found in {file_path}"
            assert "localStorage[" not in content, f"Forbidden localStorage access found in {file_path}"
            assert "sessionStorage[" not in content, f"Forbidden sessionStorage access found in {file_path}"


def test_immutable_audit_log_temporal_integrity(client):
    """Verify that every mutating operation records an immutable InteractionEvent with full temporal metadata."""
    # 1. Created event
    card = create_interaction(client, user="manager-a", title="Temporal Audit Test Card")
    card_id = card["id"]
    rev = card["revision"]

    # 2. Attributes corrected event
    patch_res = client.patch(
        f"/api/v1/interactions/{card_id}",
        json={"expected_revision": rev, "cycle_label": "2026-Cycle-Audit"},
        headers=headers("manager-a", str(uuid4())),
    )
    assert patch_res.status_code == 200
    rev = patch_res.json()["revision"]

    # 3. Comment added event
    comment_res = client.post(
        f"/api/v1/interactions/{card_id}/comments",
        json={"expected_revision": rev, "body": "Аудиторский комментарий"},
        headers=headers("manager-a", str(uuid4())),
    )
    assert comment_res.status_code == 201
    rev = comment_res.json()["revision"]

    # 4. Attachment uploaded event
    fake_pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>%%EOF"
    att_res = client.post(
        f"/api/v1/interactions/{card_id}/attachments",
        files={"file": ("audit_doc.pdf", fake_pdf, "application/pdf")},
        headers=headers("manager-a"),
    )
    assert att_res.status_code == 201

    # 5. State changed event
    trans_res = client.post(
        f"/api/v1/interactions/{card_id}/transitions",
        json={"transition_code": "contact_search_to_needs_clarification", "expected_revision": rev},
        headers=headers("manager-a", str(uuid4())),
    )
    assert trans_res.status_code == 200
    rev = trans_res.json()["revision"]

    # 6. Reassignment event
    assign_res = client.post(
        f"/api/v1/interactions/{card_id}/assignments",
        json={"expected_revision": rev, "owner_id": "manager-b", "reason": "Переназначение для проверки аудита"},
        headers=headers("supervisor", str(uuid4())),
    )
    assert assign_res.status_code == 200

    # Fetch full history as supervisor
    detail = client.get(f"/api/v1/interactions/{card_id}", headers=headers("supervisor")).json()
    events = detail["events"]

    expected_types = [
        "created",
        "attributes_corrected",
        "comment_added",
        "attachment_uploaded",
        "state_changed",
        "owner_changed",
    ]
    actual_types = [e["type"] for e in events]
    for exp_type in expected_types:
        assert exp_type in actual_types, f"Missing event type '{exp_type}' in events: {actual_types}"

    # Verify temporal invariants for all events
    for idx, event in enumerate(events, start=1):
        assert event["sequence"] == idx, f"Sequence must be strictly continuous: expected {idx}, got {event['sequence']}"
        assert event["actor_name"], "actor_name must not be empty"
        assert event["effective_at"], "effective_at must not be empty"
        assert event["received_at"], "received_at must not be empty"
        assert "snapshot" in event["payload"], "payload must contain an immutable state snapshot"
        assert isinstance(event["payload"]["snapshot"], dict)

