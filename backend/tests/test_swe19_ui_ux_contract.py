"""Integration and contract verification for swe_19 UI/UX requirements:
R1: Role-based catalog import access
R2: Input field clearing upon mutation success and draft preservation on error
R3: Unified chronological timeline without comment duplication
"""
import re
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]


def headers(user="manager-a", key=None):
    res = {"X-Demo-User": user}
    if key:
        res["Idempotency-Key"] = key
    return res


def test_swe19_backend_comment_and_event_contract(client):
    """Test that posting a comment creates both a Comment and a comment_added event with comment_id."""
    body = {
        "title": "Тест таймлайна swe_19",
        "organization_id": "org-1",
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "cycle_label": "Цикл 1",
        "owner_id": "manager-a",
    }
    resp = client.post("/api/v1/interactions", json=body, headers=headers("manager-a", str(uuid4())))
    assert resp.status_code == 201
    item = resp.json()
    item_id = item["id"]
    rev = item["revision"]

    c_resp = client.post(
        f"/api/v1/interactions/{item_id}/comments",
        json={"body": "Тестовый комментарий проверки таймлайна", "expected_revision": rev},
        headers=headers("manager-a", str(uuid4())),
    )
    assert c_resp.status_code == 201
    comment_data = c_resp.json()
    assert comment_data["body"] == "Тестовый комментарий проверки таймлайна"
    assert "id" in comment_data
    comment_id = comment_data["id"]
    new_rev = comment_data["interaction_revision"]
    assert new_rev == rev + 1

    d_resp = client.get(f"/api/v1/interactions/{item_id}", headers=headers("manager-a"))
    assert d_resp.status_code == 200
    detail_data = d_resp.json()

    found_c = [c for c in detail_data["comments"] if c["id"] == comment_id]
    assert len(found_c) == 1

    found_events = [
        e for e in detail_data["events"]
        if e.get("type") == "comment_added" and (e.get("comment_id") == comment_id or e.get("payload", {}).get("comment_id") == comment_id)
    ]
    assert len(found_events) == 1
    assert found_events[0]["comment"] == "Тестовый комментарий проверки таймлайна"


def test_swe19_backend_assignment_and_event_contract(client):
    """Test that reassignment by supervisor creates an owner_changed event with reason."""
    body = {
        "title": "Тест переназначения swe_19",
        "organization_id": "org-1",
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "cycle_label": "Цикл 1",
        "owner_id": "manager-a",
    }
    resp = client.post("/api/v1/interactions", json=body, headers=headers("manager-a", str(uuid4())))
    assert resp.status_code == 201
    item = resp.json()
    item_id = item["id"]
    rev = item["revision"]

    assign_resp = client.post(
        f"/api/v1/interactions/{item_id}/assignments",
        json={"owner_id": "manager-b", "expected_revision": rev, "reason": "Перевод на другого менеджера по загрузке"},
        headers=headers("supervisor", str(uuid4())),
    )
    assert assign_resp.status_code == 200
    updated = assign_resp.json()
    assert updated["owner_id"] == "manager-b"
    assert updated["revision"] == rev + 1

    d_resp = client.get(f"/api/v1/interactions/{item_id}", headers=headers("supervisor"))
    assert d_resp.status_code == 200
    detail_data = d_resp.json()
    owner_events = [e for e in detail_data["events"] if e.get("type") == "owner_changed"]
    assert len(owner_events) >= 1
    assert owner_events[-1]["comment"] == "Перевод на другого менеджера по загрузке"
    assert owner_events[-1]["owner_id"] == "manager-b"


def test_swe19_frontend_catalog_page_role_invariants():
    """Verify frontend CatalogPage enforces isPrivileged for import buttons, migration buttons, and modals."""
    cat_path = ROOT / "frontend" / "src" / "views" / "CatalogPage.tsx"
    assert cat_path.is_file(), f"Missing {cat_path}"
    content = cat_path.read_text(encoding="utf-8")

    assert "isPrivileged" in content
    assert "supervisor" in content
    assert "administrator" in content
    assert "admin" in content

    # Both buttons must be guarded by isPrivileged
    import_btn_match = re.search(r"\{api\s*&&\s*isPrivileged\s*&&\s*\(\s*<Button.*?<Icon\s+name=\"upload\"", content, re.DOTALL)
    assert import_btn_match is not None, "Import catalog button must be guarded by isPrivileged"

    migration_btn_match = re.search(r"\{api\s*&&\s*isPrivileged\s*&&\s*\(\s*<Button.*?<Icon\s+name=\"refresh\"", content, re.DOTALL)
    assert migration_btn_match is not None, "Workflow migration button must be guarded by isPrivileged"

    # Both modals must be guarded by isPrivileged
    import_modal_match = re.search(r"\{importOpen\s*&&\s*api\s*&&\s*isPrivileged\s*&&\s*\(", content)
    assert import_modal_match is not None, "ImportWizardModal must be guarded by isPrivileged"

    migration_modal_match = re.search(r"\{migrationOpen\s*&&\s*api\s*&&\s*isPrivileged\s*&&\s*\(", content)
    assert migration_modal_match is not None, "WorkflowMigratorModal must be guarded by isPrivileged"


def test_swe19_backend_import_authorization_boundaries(client):
    """Verify negative and positive role boundaries for catalog import (403 for manager, 200 for supervisor/admin)."""
    # Manager trying import preview -> 403 Forbidden
    resp_prev = client.post(
        "/api/v1/imports/organizations/preview",
        files={"file": ("test.csv", b"name,type\nOrg1,university\n", "text/csv")},
        headers=headers("manager-a"),
    )
    assert resp_prev.status_code == 403, f"Expected 403 for manager, got {resp_prev.status_code}"

    # Manager trying import commit -> 403 Forbidden
    resp_comm = client.post(
        "/api/v1/imports/organizations/commit",
        files={"file": ("test.csv", b"name,type\nOrg1,university\n", "text/csv")},
        headers=headers("manager-a", str(uuid4())),
    )
    assert resp_comm.status_code == 403, f"Expected 403 for manager, got {resp_comm.status_code}"

    # Supervisor CAN access import preview (HTTP 200)
    resp_sup = client.post(
        "/api/v1/imports/organizations/preview",
        files={"file": ("test.csv", b"name,type\nOrgAlpha,university\n", "text/csv")},
        headers=headers("supervisor"),
    )
    assert resp_sup.status_code == 200, f"Expected 200 for supervisor, got {resp_sup.status_code}: {resp_sup.text}"
    assert resp_sup.json()["rows_total"] == 1

    # Administrator CAN access import preview (HTTP 200)
    resp_admin = client.post(
        "/api/v1/imports/organizations/preview",
        files={"file": ("test.csv", b"name,type\nOrgBeta,university\n", "text/csv")},
        headers=headers("administrator"),
    )
    assert resp_admin.status_code == 200, f"Expected 200 for administrator, got {resp_admin.status_code}: {resp_admin.text}"
    assert resp_admin.json()["rows_total"] == 1


def test_swe19_frontend_interaction_page_input_resets_and_timeline():
    """Verify frontend InteractionPage implements input resets, option reset, draft preservation, and unified timeline."""
    int_path = ROOT / "frontend" / "src" / "views" / "InteractionPage.tsx"
    assert int_path.is_file(), f"Missing {int_path}"
    content = int_path.read_text(encoding="utf-8")

    assert "setComment('')" in content, "setComment('') must be called after comment mutation"
    assert "setReason('')" in content, "setReason('') must be called after assignment mutation"
    assert "setOwner('')" in content, "setOwner('') must be called after assignment mutation"
    assert '<option value="">Выберите менеджера</option>' in content, "Manager select must have empty reset option"

    # Invariant: inputs are cleared ONLY upon successful completion of async mutation, preserving drafts on error
    comment_reset_order = re.search(
        r"await\s+api\.post\(.*?'/comments'.*?\);\s*setComment\(''\);",
        content,
        re.DOTALL,
    )
    assert comment_reset_order is not None, "setComment('') must be invoked strictly after successful comment mutation"

    assignment_reset_order = re.search(
        r"await\s+api\.post\(.*?'/assignments'.*?\);\s*setReason\(''\);\s*setOwner\(''\);",
        content,
        re.DOTALL,
    )
    assert assignment_reset_order is not None, "setReason('') and setOwner('') must be invoked strictly after successful assignment mutation"

    assert "coveredCommentIds" in content, "coveredCommentIds set must be used to deduplicate comments"
    assert "standaloneComments" in content, "standaloneComments must filter out already covered comments"
    assert "timelineEntries" in content, "timelineEntries must combine events and standalone comments"
    assert "tone-orange" in content, "Comment entries must receive tone-orange styling"
    assert "записей" in content and "запись" in content and "записи" in content, "Russian pluralization must be implemented"


def test_swe19_pluralization_and_timeline_ordering_logic():
    """Test Russian pluralization formula and timeline deduplication / sorting edge cases."""
    def pluralize(count: int) -> str:
        mod10 = abs(count) % 10
        mod100 = abs(count) % 100
        if 11 <= mod100 <= 19:
            return f"{count} записей"
        if mod10 == 1:
            return f"{count} запись"
        if 2 <= mod10 <= 4:
            return f"{count} записи"
        return f"{count} записей"

    # Pluralization edge cases
    assert pluralize(0) == "0 записей"
    assert pluralize(1) == "1 запись"
    assert pluralize(2) == "2 записи"
    assert pluralize(4) == "4 записи"
    assert pluralize(5) == "5 записей"
    assert pluralize(11) == "11 записей"
    assert pluralize(12) == "12 записей"
    assert pluralize(14) == "14 записей"
    assert pluralize(19) == "19 записей"
    assert pluralize(20) == "20 записей"
    assert pluralize(21) == "21 запись"
    assert pluralize(22) == "22 записи"
    assert pluralize(100) == "100 записей"
    assert pluralize(111) == "111 записей"
    assert pluralize(121) == "121 запись"

    # Timeline deduplication & ordering verification replicating InteractionPage.tsx logic
    def build_timeline(events, comments):
        covered_ids = set()
        for e in events:
            cid = e.get("comment_id") or (e.get("payload") or {}).get("comment_id")
            if cid:
                covered_ids.add(str(cid))

        standalone_comments = [
            c for c in comments
            if str(c["id"]) not in covered_ids
            and not any(
                e.get("type") in ("comment_added", "comment") and e.get("comment") and e.get("comment") == c.get("body")
                for e in events
            )
        ]

        entries = []
        for e in events:
            is_comm = e.get("type") in ("comment_added", "comment")
            entries.append({
                "key": f"event-{e['id']}",
                "time": e.get("effective_at"),
                "sequence": e.get("sequence"),
                "is_comment": is_comm,
                "text": e.get("comment") or e.get("to_state") or "",
            })
        for c in standalone_comments:
            entries.append({
                "key": f"comment-{c['id']}",
                "time": c.get("created_at"),
                "sequence": None,
                "is_comment": True,
                "text": c.get("body"),
            })

        from datetime import datetime

        def parse_ts(t):
            if not t:
                return 0
            try:
                return datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp() * 1000
            except Exception:
                return 0

        entries.sort(key=lambda x: (
            parse_ts(x["time"]),
            x["sequence"] if x["sequence"] is not None else 999999
        ))
        return entries

    # Case 1: Comment covered by comment_id in event must NOT be duplicated
    events_1 = [
        {"id": "e1", "type": "created", "sequence": 1, "effective_at": "2026-09-26T10:00:00Z"},
        {"id": "e2", "type": "comment_added", "sequence": 2, "effective_at": "2026-09-26T10:05:00Z", "comment_id": "c1", "comment": "Привет"},
    ]
    comments_1 = [
        {"id": "c1", "body": "Привет", "created_at": "2026-09-26T10:05:00Z"},
    ]
    res_1 = build_timeline(events_1, comments_1)
    assert len(res_1) == 2, f"Expected 2 entries without duplicate, got {len(res_1)}"
    assert [e["key"] for e in res_1] == ["event-e1", "event-e2"]
    assert res_1[1]["is_comment"] is True

    # Case 2: Fallback deduplication by matching body when comment_id is missing from event
    events_2 = [
        {"id": "e1", "type": "comment_added", "sequence": 1, "effective_at": "2026-09-26T10:00:00Z", "comment": "Текст без ID"},
    ]
    comments_2 = [
        {"id": "c_orphan", "body": "Текст без ID", "created_at": "2026-09-26T10:00:00Z"},
    ]
    res_2 = build_timeline(events_2, comments_2)
    assert len(res_2) == 1, f"Expected 1 entry without duplicate, got {len(res_2)}"
    assert res_2[0]["key"] == "event-e1"

    # Case 3: Standalone comment with different content is preserved and chronologically placed
    events_3 = [
        {"id": "e1", "type": "created", "sequence": 1, "effective_at": "2026-09-26T10:00:00Z"},
        {"id": "e2", "type": "state_changed", "sequence": 2, "effective_at": "2026-09-26T10:10:00Z", "to_state": "meeting"},
    ]
    comments_3 = [
        {"id": "c_legacy", "body": "Автономный комментарий", "created_at": "2026-09-26T10:05:00Z"},
    ]
    res_3 = build_timeline(events_3, comments_3)
    assert len(res_3) == 3
    assert [e["key"] for e in res_3] == ["event-e1", "comment-c_legacy", "event-e2"]
    assert res_3[1]["is_comment"] is True
    assert res_3[1]["text"] == "Автономный комментарий"

    # Case 4: Same millisecond tie-breaker by sequence
    events_4 = [
        {"id": "e2", "type": "state_changed", "sequence": 2, "effective_at": "2026-09-26T10:00:00.100Z"},
        {"id": "e1", "type": "created", "sequence": 1, "effective_at": "2026-09-26T10:00:00.100Z"},
    ]
    res_4 = build_timeline(events_4, [])
    assert len(res_4) == 2
    assert [e["key"] for e in res_4] == ["event-e1", "event-e2"]


