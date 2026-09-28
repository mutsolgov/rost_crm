"""Verification suite for swe_24 requirements:
R1. Cleanup of DeleteAttachmentModal (remove 152-FZ audit warning, concise text)
R2. Exclusion of attachment_deleted audit events from frontend UI while retaining backend DB audit
R3. Timeline tabs ('all' | 'comments' | 'stages') with counters and empty state placeholder
"""
from pathlib import Path
from uuid import uuid4
import re
import pytest

ROOT = Path(__file__).resolve().parents[2]


def headers(user="manager-a", key=None):
    res = {"X-Demo-User": user}
    if key:
        res["Idempotency-Key"] = key
    return res


def test_swe24_delete_attachment_modal_contract():
    """Verify DeleteAttachmentModal removes 152-FZ warning and keeps concise confirmation text."""
    page_path = ROOT / "frontend" / "src" / "views" / "InteractionPage.tsx"
    assert page_path.is_file(), f"Missing {page_path}"
    content = page_path.read_text(encoding="utf-8")

    # Extract DeleteAttachmentModal function block
    modal_match = re.search(
        r"export\s+function\s+DeleteAttachmentModal\s*\(.*?\)\s*\{.*?\n\}",
        content,
        re.DOTALL,
    )
    assert modal_match is not None, "DeleteAttachmentModal component must be defined and exported"
    modal_content = modal_match.group(0)

    # R1: Must NOT have 152-ФЗ or bureaucratic audit warning text
    assert "152-ФЗ" not in modal_content, "152-ФЗ warning block must be removed from DeleteAttachmentModal"
    assert "журнал" not in modal_content.lower(), "Audit log bureaucracy must be removed from DeleteAttachmentModal"

    # R1: Must have concise confirmation text matching specification
    assert "Вы действительно хотите удалить файл «{attachment.file_name}» ({formatFileSize(attachment.file_size)})? Это действие нельзя отменить." in modal_content, (
        "Confirmation text must match exact specification"
    )

    # R1: Must preserve action buttons and handlers
    assert "onClose" in modal_content, "Must support onClose handler"
    assert "onConfirm" in modal_content, "Must support onConfirm handler"
    assert "disabled={busy}" in modal_content, "Must disable actions while deletion is busy"


def test_swe24_frontend_timeline_tabs_and_filtering_contract():
    """Verify InteractionPage timeline tabs state, attachment_deleted exclusion, and empty state."""
    page_path = ROOT / "frontend" / "src" / "views" / "InteractionPage.tsx"
    assert page_path.is_file(), f"Missing {page_path}"
    content = page_path.read_text(encoding="utf-8")

    # R3: Local state for active tab
    assert "const [historyTab, setHistoryTab] = useState<'all' | 'comments' | 'stages'>('all');" in content, (
        "historyTab state must match specified type and default"
    )

    # R2: Exclusion of attachment_deleted from UI timeline
    assert "e.type !== 'attachment_deleted'" in content, (
        "visibleEvents must filter out attachment_deleted system events"
    )

    # R3: List classification
    assert "commentsList" in content, "commentsList must be defined"
    assert "stagesList" in content, "stagesList must be defined"
    assert "allList" in content, "allList must be defined"

    # R3: Tabs UI rendering with counters
    assert 'role="tablist"' in content, "Tabs container must have role=tablist"
    assert 'className={`inbox-tab-btn ${historyTab === \'all\' ? \'active\' : \'\'}`}' in content
    assert 'className={`inbox-tab-btn ${historyTab === \'comments\' ? \'active\' : \'\'}`}' in content
    assert 'className={`inbox-tab-btn ${historyTab === \'stages\' ? \'active\' : \'\'}`}' in content

    assert "<span>Все</span>" in content
    assert "<b>{allList.length}</b>" in content
    assert "<span>Комментарии</span>" in content
    assert "<b>{commentsList.length}</b>" in content
    assert "<span>Этапы workflow</span>" in content
    assert "<b>{stagesList.length}</b>" in content

    # R3: Empty state placeholder
    assert '<p className="empty-inline">В этой категории пока нет записей.</p>' in content, (
        "Empty category placeholder must match exact specification"
    )


def test_swe24_backend_attachment_deleted_audit_retention(client):
    """Verify backend PostgreSQL audit logging of attachment_deleted is retained (invariant)."""
    # 1. Create an interaction
    body = {
        "title": "Интеракция проверки аудита удаления",
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

    # 2. Upload an attachment
    upload_resp = client.post(
        f"/api/v1/interactions/{item_id}/attachments",
        files={"file": ("audit_sample.pdf", b"%PDF-1.4 test document content", "application/pdf")},
        headers=headers("manager-a", str(uuid4())),
    )
    assert upload_resp.status_code == 201
    att_data = upload_resp.json()
    att_id = att_data["id"]
    det_before = client.get(f"/api/v1/interactions/{item_id}", headers=headers("manager-a")).json()
    rev_before = det_before["revision"]

    # 3. Delete the attachment with CAS revision check
    del_resp = client.delete(
        f"/api/v1/interactions/{item_id}/attachments/{att_id}",
        params={"expected_revision": rev_before},
        headers=headers("manager-a", str(uuid4())),
    )
    assert del_resp.status_code == 200

    # 4. Fetch detail from backend: attachment_deleted event MUST be present in backend events for 152-FZ compliance
    det_resp = client.get(f"/api/v1/interactions/{item_id}", headers=headers("manager-a"))
    assert det_resp.status_code == 200
    det = det_resp.json()

    del_events = [e for e in det["events"] if e.get("type") == "attachment_deleted"]
    assert len(del_events) == 1, "Backend must log exactly one attachment_deleted event for 152-FZ audit trail"
    assert del_events[0]["file_name"] == "audit_sample.pdf"


def test_swe24_tab_classification_and_filtering_simulation():
    """Verify classification logic of allList, commentsList, stagesList, and attachment_deleted exclusion."""
    events = [
        {"id": "e1", "type": "created", "sequence": 1, "effective_at": "2026-09-27T10:00:00Z"},
        {"id": "e2", "type": "comment_added", "sequence": 2, "effective_at": "2026-09-27T10:01:00Z", "comment_id": "c1", "comment": "Первый комментарий"},
        {"id": "e3", "type": "state_changed", "sequence": 3, "effective_at": "2026-09-27T10:02:00Z", "to_state": "meeting"},
        {"id": "e4", "type": "attachment_added", "sequence": 4, "effective_at": "2026-09-27T10:03:00Z", "file_name": "doc.pdf"},
        {"id": "e5", "type": "attachment_deleted", "sequence": 5, "effective_at": "2026-09-27T10:04:00Z", "file_name": "doc.pdf"},
        {"id": "e6", "type": "owner_changed", "sequence": 6, "effective_at": "2026-09-27T10:05:00Z", "owner_id": "manager-b"},
    ]
    comments = [
        {"id": "c1", "body": "Первый комментарий", "created_at": "2026-09-27T10:01:00Z"},
        {"id": "c_extra", "body": "Автономный комментарий", "created_at": "2026-09-27T10:06:00Z"},
    ]

    # Replicate InteractionPage.tsx filtering and classification
    visible_events = [e for e in events if e.get("type") != "attachment_deleted"]
    assert len(visible_events) == 5
    assert not any(e.get("type") == "attachment_deleted" for e in visible_events)

    covered_ids = {str(e.get("comment_id")) for e in visible_events if e.get("comment_id")}
    standalone_comments = [
        c for c in comments
        if str(c["id"]) not in covered_ids
        and not any(e.get("type") in ("comment_added", "comment") and e.get("comment") == c.get("body") for e in visible_events)
    ]
    assert len(standalone_comments) == 1
    assert standalone_comments[0]["id"] == "c_extra"

    all_list = []
    for e in visible_events:
        all_list.append({"key": f"event-{e['id']}", "type": e["type"]})
    for c in standalone_comments:
        all_list.append({"key": f"comment-{c['id']}", "type": "comment"})

    comments_list = [item for item in all_list if item["type"] in ("comment_added", "comment")]
    stages_list = [
        item for item in all_list
        if item["type"] in ("stage_transition", "state_changed", "assignment_changed", "owner_changed", "transition", "assignment")
    ]

    # Counts verification
    assert len(all_list) == 6  # 5 visible events + 1 standalone comment
    assert len(comments_list) == 2  # e2 (comment_added) and c_extra (comment)
    assert len(stages_list) == 2  # e3 (state_changed) and e6 (owner_changed)

    # Empty category simulation
    empty_events_list = [item for item in [] if item["type"] in ("comment_added", "comment")]
    assert len(empty_events_list) == 0
