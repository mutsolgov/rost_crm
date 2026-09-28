import hashlib
import io
import zipfile
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.files import MAX_FILE_SIZE


def headers(user="manager-a", key=None):
    res = {"X-Demo-User": user}
    if key:
        res["Idempotency-Key"] = key
    return res


def create_interaction(client, user="manager-a", org_id=None):
    body = {
        "title": "Взаимодействие для тестирования вложений",
        "organization_id": org_id or ("org-2" if user == "manager-b" else "org-1"),
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "cycle_label": "Цикл-Вложения",
        "owner_id": user,
    }
    response = client.post("/api/v1/interactions", json=body, headers=headers(user, str(uuid4())))
    assert response.status_code == 201, response.text
    return response.json()


def make_minimal_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("test.txt", "hello")
    return buf.getvalue()


SAMPLE_FILES = {
    "sample.png": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4",
    "sample.jpeg": b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07",
    "sample.pdf": b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<<>>\n%%EOF",
    "sample.zip": make_minimal_zip(),
    "sample.gzip": b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\x03\x03\x00\x00\x00\x00\x00\x00\x00\x00\x00",
    "sample.rar": b"Rar!\x1a\x07\x00\xcf\x90s\x00\x00\r\x00\x00\x00\x00\x00\x00\x00",
    "sample.doc": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 504,
    "sample.docx": make_minimal_zip(),
    "sample.xls": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 504,
    "sample.xlsx": make_minimal_zip(),
}


def test_upload_and_download_all_10_formats(client):
    item = create_interaction(client, "manager-a")
    iid = item["id"]

    for filename, content in SAMPLE_FILES.items():
        resp = client.post(
            f"/api/v1/interactions/{iid}/attachments",
            files={"file": (filename, content)},
            headers=headers("manager-a"),
        )
        assert resp.status_code == 201, f"Failed upload for {filename}: {resp.text}"
        data = resp.json()
        assert data["file_name"] == filename
        assert data["file_size"] == len(content)
        expected_hash = hashlib.sha256(content).hexdigest()
        assert data["checksum"] == expected_hash
        assert len(data["checksum"]) == 64
        att_id = data["id"]

        # Download and verify bit-for-bit integrity
        down = client.get(
            f"/api/v1/interactions/{iid}/attachments/{att_id}/download",
            headers=headers("manager-a"),
        )
        assert down.status_code == 200, down.text
        assert down.content == content
        assert "Content-Disposition" in down.headers
        assert filename in down.headers["Content-Disposition"]


def test_reject_dangerous_and_disallowed_formats(client):
    item = create_interaction(client, "manager-a")
    iid = item["id"]

    # Disallowed extensions
    bad_files = [
        ("malware.exe", b"MZ\x90\x00\x03\x00\x00\x00"),
        ("exploit.sh", b"#!/bin/bash\nrm -rf /"),
        ("backdoor.php", b"<?php phpinfo(); ?>"),
        ("script.bat", b"@echo off\ndir"),
    ]
    for fn, content in bad_files:
        resp = client.post(
            f"/api/v1/interactions/{iid}/attachments",
            files={"file": (fn, content)},
            headers=headers("manager-a"),
        )
        assert resp.status_code == 422, f"Expected 422 for {fn}, got {resp.status_code}"
        assert resp.json()["error"]["code"] == "FILE_TYPE_NOT_ALLOWED"


def test_reject_magic_byte_mismatch(client):
    item = create_interaction(client, "manager-a")
    iid = item["id"]

    # An executable renamed to .pdf
    disguised = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00"
    resp = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("report.pdf", disguised)},
        headers=headers("manager-a"),
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "FILE_TYPE_NOT_ALLOWED"


def test_reject_file_too_large(client):
    item = create_interaction(client, "manager-a")
    iid = item["id"]

    oversized = b"%PDF-1.4\n" + b"0" * (MAX_FILE_SIZE + 1)
    resp = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("huge.pdf", oversized)},
        headers=headers("manager-a"),
    )
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_path_traversal_sanitization(client):
    item = create_interaction(client, "manager-a")
    iid = item["id"]

    content = SAMPLE_FILES["sample.pdf"]
    resp = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("../../../../etc/passwd.pdf", content)},
        headers=headers("manager-a"),
    )
    assert resp.status_code == 201
    assert resp.json()["file_name"] == "passwd.pdf"


def test_scope_isolation_152_fz(client):
    # Manager A creates interaction
    item_a = create_interaction(client, "manager-a")
    iid_a = item_a["id"]

    # Manager A uploads attachment
    up_resp = client.post(
        f"/api/v1/interactions/{iid_a}/attachments",
        files={"file": ("secret.pdf", SAMPLE_FILES["sample.pdf"])},
        headers=headers("manager-a"),
    )
    assert up_resp.status_code == 201
    att_id = up_resp.json()["id"]

    # Manager B attempts to download Manager A's attachment -> 404 strictly
    down = client.get(
        f"/api/v1/interactions/{iid_a}/attachments/{att_id}/download",
        headers=headers("manager-b"),
    )
    assert down.status_code == 404
    assert down.json()["error"]["code"] == "NOT_FOUND"

    # Manager B attempts to list Manager A's attachments -> 404
    lst = client.get(
        f"/api/v1/interactions/{iid_a}/attachments",
        headers=headers("manager-b"),
    )
    assert lst.status_code == 404

    # Manager B attempts to upload to Manager A's interaction -> 404
    up_b = client.post(
        f"/api/v1/interactions/{iid_a}/attachments",
        files={"file": ("intruder.pdf", SAMPLE_FILES["sample.pdf"])},
        headers=headers("manager-b"),
    )
    assert up_b.status_code == 404


def test_attachments_in_detail_and_events(client):
    item = create_interaction(client, "manager-a")
    iid = item["id"]

    client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("document.pdf", SAMPLE_FILES["sample.pdf"])},
        headers=headers("manager-a"),
    )

    det = client.get(f"/api/v1/interactions/{iid}", headers=headers("manager-a")).json()
    assert len(det["attachments"]) == 1
    assert det["attachments"][0]["file_name"] == "document.pdf"
    assert any(e["type"] == "attachment_uploaded" for e in det["events"])


def test_attachment_cross_interaction_access_returns_404(client):
    """Attachment requested with mismatched interaction_id returns 404 even if user owns both interactions."""
    item1 = create_interaction(client, "manager-a")
    item2 = create_interaction(client, "manager-a")

    up_resp = client.post(
        f"/api/v1/interactions/{item1['id']}/attachments",
        files={"file": ("doc1.pdf", SAMPLE_FILES["sample.pdf"])},
        headers=headers("manager-a"),
    )
    assert up_resp.status_code == 201
    att_id1 = up_resp.json()["id"]

    # Request attachment of interaction 1 using interaction 2's URL
    cross_resp = client.get(
        f"/api/v1/interactions/{item2['id']}/attachments/{att_id1}/download",
        headers=headers("manager-a"),
    )
    assert cross_resp.status_code == 404
    assert cross_resp.json()["error"]["code"] == "NOT_FOUND"


def test_attachment_download_nonexistent_returns_404(client):
    """Downloading non-existent attachment ID returns 404 NOT_FOUND."""
    item = create_interaction(client, "manager-a")
    non_existent_id = str(uuid4())
    resp = client.get(
        f"/api/v1/interactions/{item['id']}/attachments/{non_existent_id}/download",
        headers=headers("manager-a"),
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_attachment_upload_with_cas_and_revision_increment(client):
    """Uploading attachment with valid expected_revision in multipart form increments revision and logs event."""
    item = create_interaction(client, "manager-a")
    iid = item["id"]
    initial_rev = item["revision"]

    resp = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("contract.pdf", SAMPLE_FILES["sample.pdf"])},
        data={"expected_revision": str(initial_rev)},
        headers=headers("manager-a"),
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["file_name"] == "contract.pdf"

    det = client.get(f"/api/v1/interactions/{iid}", headers=headers("manager-a")).json()
    assert det["revision"] == initial_rev + 1
    assert len(det["attachments"]) == 1
    assert any(e["type"] == "attachment_uploaded" for e in det["events"])


def test_attachment_upload_stale_revision_conflict(client):
    """Uploading attachment with stale expected_revision raises HTTP 409 REVISION_CONFLICT."""
    item = create_interaction(client, "manager-a")
    iid = item["id"]

    resp = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("stale.pdf", SAMPLE_FILES["sample.pdf"])},
        data={"expected_revision": "999"},
        headers=headers("manager-a"),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "REVISION_CONFLICT"

    # Confirm no attachment or event was persisted
    det = client.get(f"/api/v1/interactions/{iid}", headers=headers("manager-a")).json()
    assert len(det["attachments"]) == 0
    assert not any(e["type"] == "attachment_uploaded" for e in det["events"])


def test_attachment_upload_revision_via_query_and_headers(client):
    """expected_revision can be extracted from query parameters or headers."""
    item = create_interaction(client, "manager-a")
    iid = item["id"]
    rev = item["revision"]

    # Via query parameter
    resp_query = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        params={"expected_revision": rev},
        files={"file": ("query.pdf", SAMPLE_FILES["sample.pdf"])},
        headers=headers("manager-a"),
    )
    assert resp_query.status_code == 201, resp_query.text

    det = client.get(f"/api/v1/interactions/{iid}", headers=headers("manager-a")).json()
    assert det["revision"] == rev + 1

    # Via header
    hdrs = headers("manager-a")
    hdrs["expected_revision"] = str(rev + 1)
    resp_hdr = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("header.pdf", SAMPLE_FILES["sample.pdf"])},
        headers=hdrs,
    )
    assert resp_hdr.status_code == 201, resp_hdr.text

    det2 = client.get(f"/api/v1/interactions/{iid}", headers=headers("manager-a")).json()
    assert det2["revision"] == rev + 2


def test_attachment_upload_idempotency_replay_and_caching(client):
    """Replaying upload with the exact same Idempotency-Key returns cached response without side effects."""
    item = create_interaction(client, "manager-a")
    iid = item["id"]
    rev = item["revision"]
    idem_key = f"idem-att-{uuid4()}"

    # Request 1
    resp1 = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("doc.pdf", SAMPLE_FILES["sample.pdf"])},
        data={"expected_revision": str(rev)},
        headers=headers("manager-a", idem_key),
    )
    assert resp1.status_code == 201, resp1.text
    data1 = resp1.json()

    # Request 2 (replay)
    resp2 = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("doc.pdf", SAMPLE_FILES["sample.pdf"])},
        data={"expected_revision": str(rev)},
        headers=headers("manager-a", idem_key),
    )
    assert resp2.status_code == 201
    assert resp2.json() == data1

    # Request 3 (replay again)
    resp3 = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("doc.pdf", SAMPLE_FILES["sample.pdf"])},
        data={"expected_revision": str(rev)},
        headers=headers("manager-a", idem_key),
    )
    assert resp3.status_code == 201
    assert resp3.json() == data1

    # Verify zero side-effect duplication
    det = client.get(f"/api/v1/interactions/{iid}", headers=headers("manager-a")).json()
    assert det["revision"] == rev + 1
    assert len(det["attachments"]) == 1
    att_events = [e for e in det["events"] if e["type"] == "attachment_uploaded"]
    assert len(att_events) == 1


def test_attachment_upload_idempotency_payload_conflict(client):
    """Sending a different payload with the same Idempotency-Key yields 409 IDEMPOTENCY_CONFLICT."""
    item = create_interaction(client, "manager-a")
    iid = item["id"]
    rev = item["revision"]
    idem_key = f"idem-conflict-{uuid4()}"

    resp1 = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("first.pdf", SAMPLE_FILES["sample.pdf"])},
        data={"expected_revision": str(rev)},
        headers=headers("manager-a", idem_key),
    )
    assert resp1.status_code == 201

    # Second request with same key but different file
    resp2 = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("second.png", SAMPLE_FILES["sample.png"])},
        data={"expected_revision": str(rev)},
        headers=headers("manager-a", idem_key),
    )
    assert resp2.status_code == 409
    assert resp2.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_attachment_upload_invalid_idempotency_key_boundaries(client):
    """Invalid Idempotency-Key (empty, whitespace, >200 chars) is rejected with 422 VALIDATION_ERROR."""
    item = create_interaction(client, "manager-a")
    iid = item["id"]

    for bad_key in ["", "   ", "x" * 201]:
        resp = client.post(
            f"/api/v1/interactions/{iid}/attachments",
            files={"file": ("doc.pdf", SAMPLE_FILES["sample.pdf"])},
            headers={"X-Demo-User": "manager-a", "Idempotency-Key": bad_key},
        )
        assert resp.status_code == 422, f"Expected 422 for key {bad_key!r}, got {resp.status_code}"
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_attachment_upload_invalid_expected_revision(client):
    """Invalid expected_revision (non-integer, <= 0) is rejected with 422 VALIDATION_ERROR."""
    item = create_interaction(client, "manager-a")
    iid = item["id"]

    for bad_rev in ["not-an-int", "0", "-1"]:
        resp = client.post(
            f"/api/v1/interactions/{iid}/attachments",
            files={"file": ("doc.pdf", SAMPLE_FILES["sample.pdf"])},
            data={"expected_revision": bad_rev},
            headers=headers("manager-a"),
        )
        assert resp.status_code == 422, f"Expected 422 for rev {bad_rev!r}, got {resp.status_code}"
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_attachment_upload_hyphenated_header_and_query(client):
    """Hyphenated Expected-Revision header and query parameter are recognized and enforced."""
    item = create_interaction(client, "manager-a")
    iid = item["id"]
    rev = item["revision"]

    # Valid hyphenated header increments revision
    resp = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("doc_h1.pdf", SAMPLE_FILES["sample.pdf"])},
        headers={"X-Demo-User": "manager-a", "Expected-Revision": str(rev)},
    )
    assert resp.status_code == 201, resp.text

    # Stale hyphenated header raises 409
    resp_stale = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("doc_h2.pdf", SAMPLE_FILES["sample.pdf"])},
        headers={"X-Demo-User": "manager-a", "Expected-Revision": "999"},
    )
    assert resp_stale.status_code == 409
    assert resp_stale.json()["error"]["code"] == "REVISION_CONFLICT"

    # Valid hyphenated query param
    resp_q = client.post(
        f"/api/v1/interactions/{iid}/attachments?expected-revision={rev + 1}",
        files={"file": ("doc_h3.pdf", SAMPLE_FILES["sample.pdf"])},
        headers={"X-Demo-User": "manager-a"},
    )
    assert resp_q.status_code == 201, resp_q.text


def test_attachment_upload_idempotency_max_length_200(client):
    """Idempotency-Key of exactly 200 characters is accepted at the boundary."""
    item = create_interaction(client, "manager-a")
    iid = item["id"]
    key_200 = "k" * 200

    resp = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("doc_200.pdf", SAMPLE_FILES["sample.pdf"])},
        headers={"X-Demo-User": "manager-a", "Idempotency-Key": key_200},
    )
    assert resp.status_code == 201, resp.text


def test_attachment_upload_concurrency_cas_race(app):
    """Concurrent uploads with the same expected_revision: exactly 1 succeeds, others 409, 0 duplicate events."""
    import concurrent.futures

    c = TestClient(app)
    item = create_interaction(c, "manager-a")
    iid = item["id"]
    rev = item["revision"]

    def do_upload(i):
        client_thread = TestClient(app)
        return client_thread.post(
            f"/api/v1/interactions/{iid}/attachments",
            files={"file": (f"race_{i}.pdf", SAMPLE_FILES["sample.pdf"])},
            data={"expected_revision": str(rev)},
            headers={"X-Demo-User": "manager-a", "Idempotency-Key": f"race-{uuid4()}"},
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(do_upload, i) for i in range(5)]
        results = [f.result() for f in futures]

    statuses = [r.status_code for r in results]
    assert statuses.count(201) == 1, f"Expected exactly one 201, got {statuses}"
    assert statuses.count(409) == 4, f"Expected four 409s, got {statuses}"

    det = c.get(f"/api/v1/interactions/{iid}", headers=headers("manager-a")).json()
    assert det["revision"] == rev + 1
    assert len(det["attachments"]) == 1
    att_events = [e for e in det["events"] if e["type"] == "attachment_uploaded"]
    assert len(att_events) == 1


def test_attachment_upload_concurrency_identical_idempotency_key(app):
    """Concurrent uploads with identical Idempotency-Key all return 201 with 0 duplicate attachments/events."""
    import concurrent.futures

    c = TestClient(app)
    item = create_interaction(c, "manager-a")
    iid = item["id"]
    rev = item["revision"]
    shared_key = f"shared-idem-{uuid4()}"

    def do_upload(i):
        client_thread = TestClient(app)
        return client_thread.post(
            f"/api/v1/interactions/{iid}/attachments",
            files={"file": ("shared.pdf", SAMPLE_FILES["sample.pdf"])},
            data={"expected_revision": str(rev)},
            headers={"X-Demo-User": "manager-a", "Idempotency-Key": shared_key},
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(do_upload, i) for i in range(5)]
        results = [f.result() for f in futures]

    for r in results:
        assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
        assert r.json()["file_name"] == "shared.pdf"

    det = c.get(f"/api/v1/interactions/{iid}", headers=headers("manager-a")).json()
    assert det["revision"] == rev + 1
    assert len(det["attachments"]) == 1
    att_events = [e for e in det["events"] if e["type"] == "attachment_uploaded"]
    assert len(att_events) == 1


def test_attachment_upload_empty_multipart_revision_does_not_override_query_or_header(client):
    """Empty string expected_revision in multipart form must not overwrite query/header expected_revision."""
    item = create_interaction(client, "manager-a")
    iid = item["id"]
    rev = item["revision"]

    # 1. Stale revision in query param + empty string in form data -> 409 REVISION_CONFLICT
    resp_stale = client.post(
        f"/api/v1/interactions/{iid}/attachments?expected_revision=999",
        files={"file": ("stale_query.pdf", SAMPLE_FILES["sample.pdf"])},
        data={"expected_revision": ""},
        headers=headers("manager-a"),
    )
    assert resp_stale.status_code == 409
    assert resp_stale.json()["error"]["code"] == "REVISION_CONFLICT"

    # 2. Valid revision in header + empty string in form data -> 201 Created and CAS increments
    hdrs = headers("manager-a")
    hdrs["Expected-Revision"] = str(rev)
    resp_ok = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("valid_hdr.pdf", SAMPLE_FILES["sample.pdf"])},
        data={"expected_revision": ""},
        headers=hdrs,
    )
    assert resp_ok.status_code == 201
    det = client.get(f"/api/v1/interactions/{iid}", headers=headers("manager-a")).json()
    assert det["revision"] == rev + 1


def test_attachment_upload_raw_body_content_disposition_params_and_rfc5987(client):
    """Non-multipart upload supports Content-Disposition with trailing parameters and RFC 5987 UTF-8 names."""
    item = create_interaction(client, "manager-a")
    iid = item["id"]
    rev = item["revision"]
    idem_key = f"idem-raw-{uuid4()}"

    # 1. Content-Disposition with trailing parameters (e.g. '; size=1024')
    resp1 = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        content=SAMPLE_FILES["sample.pdf"],
        headers={
            "X-Demo-User": "manager-a",
            "Content-Type": "application/pdf",
            "Content-Disposition": 'attachment; filename="report_params.pdf"; size=1024',
            "Expected-Revision": str(rev),
            "Idempotency-Key": idem_key,
        },
    )
    assert resp1.status_code == 201, resp1.text
    data1 = resp1.json()
    assert data1["file_name"] == "report_params.pdf"

    # 2. Replay with identical key on raw body returns cached response (201)
    resp_replay = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        content=SAMPLE_FILES["sample.pdf"],
        headers={
            "X-Demo-User": "manager-a",
            "Content-Type": "application/pdf",
            "Content-Disposition": 'attachment; filename="report_params.pdf"; size=1024',
            "Expected-Revision": str(rev),
            "Idempotency-Key": idem_key,
        },
    )
    assert resp_replay.status_code == 201
    assert resp_replay.json() == data1

    # 3. Content-Disposition with RFC 5987 UTF-8 encoding: filename*=UTF-8''...
    resp_rfc = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        content=SAMPLE_FILES["sample.pdf"],
        headers={
            "X-Demo-User": "manager-a",
            "Content-Type": "application/pdf",
            "Content-Disposition": "attachment; filename*=UTF-8''%D0%BE%D1%82%D1%87%D0%B5%D1%82.pdf",
            "Expected-Revision": str(rev + 1),
        },
    )
    assert resp_rfc.status_code == 201, resp_rfc.text
    assert resp_rfc.json()["file_name"] == "отчет.pdf"

    det = client.get(f"/api/v1/interactions/{iid}", headers=headers("manager-a")).json()
    assert det["revision"] == rev + 2


def test_attachment_upload_idempotency_validation_failure_rollback_and_retry(client):
    """Validation errors on idempotent upload roll back session and permit retry with same key."""
    item = create_interaction(client, "manager-a")
    iid = item["id"]
    rev = item["revision"]
    idem_key = f"fail-retry-{uuid4()}"

    # 1. Invalid magic bytes fails with 422
    resp_bad = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("bad_content.pdf", b"NOT_A_VALID_PDF_MAGIC")},
        data={"expected_revision": str(rev)},
        headers=headers("manager-a", idem_key),
    )
    assert resp_bad.status_code == 422
    assert resp_bad.json()["error"]["code"] == "FILE_TYPE_NOT_ALLOWED"

    # 2. Retrying with the exact same key and a valid file succeeds with 201
    resp_ok = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("good_content.pdf", SAMPLE_FILES["sample.pdf"])},
        data={"expected_revision": str(rev)},
        headers=headers("manager-a", idem_key),
    )
    assert resp_ok.status_code == 201, resp_ok.text
    assert resp_ok.json()["file_name"] == "good_content.pdf"

    det = client.get(f"/api/v1/interactions/{iid}", headers=headers("manager-a")).json()
    assert det["revision"] == rev + 1
    assert len(det["attachments"]) == 1


def test_attachment_upload_idempotency_replay_after_intervening_revision_bump(client):
    """Idempotent replay succeeds with 201 even when interaction revision was incremented by another operation."""
    item = create_interaction(client, "manager-a")
    iid = item["id"]
    rev = item["revision"]
    idem_key = f"bump-replay-{uuid4()}"

    # 1. Initial upload with expected_revision=rev
    resp1 = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("orig.pdf", SAMPLE_FILES["sample.pdf"])},
        data={"expected_revision": str(rev)},
        headers=headers("manager-a", idem_key),
    )
    assert resp1.status_code == 201, resp1.text
    data1 = resp1.json()

    # 2. Intervening comment bumps revision to rev + 2
    resp_com = client.post(
        f"/api/v1/interactions/{iid}/comments",
        json={"body": "Intervening activity", "expected_revision": rev + 1},
        headers=headers("manager-a", str(uuid4())),
    )
    assert resp_com.status_code == 201

    det = client.get(f"/api/v1/interactions/{iid}", headers=headers("manager-a")).json()
    assert det["revision"] == rev + 2

    # 3. Replay original upload request with original expected_revision=rev (now stale compared to current rev+2)
    resp_replay = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("orig.pdf", SAMPLE_FILES["sample.pdf"])},
        data={"expected_revision": str(rev)},
        headers=headers("manager-a", idem_key),
    )
    assert resp_replay.status_code == 201
    assert resp_replay.json() == data1

    # Verify state remains at rev + 2 and zero side-effect duplication
    det2 = client.get(f"/api/v1/interactions/{iid}", headers=headers("manager-a")).json()
    assert det2["revision"] == rev + 2
    assert len(det2["attachments"]) == 1
    att_events = [e for e in det2["events"] if e["type"] == "attachment_uploaded"]
    assert len(att_events) == 1


def test_attachment_upload_cross_user_and_cross_interaction_idempotency_isolation(client):
    """Idempotency-Key is isolated per-user and per-interaction; no cross-talk or leakage."""
    item1_a = create_interaction(client, "manager-a")
    iid1 = item1_a["id"]
    rev1 = item1_a["revision"]
    shared_key = f"iso-idem-{uuid4()}"

    # 1. Manager A uploads to Interaction 1 with shared_key -> 201
    resp1 = client.post(
        f"/api/v1/interactions/{iid1}/attachments",
        files={"file": ("doc_a1.pdf", SAMPLE_FILES["sample.pdf"])},
        data={"expected_revision": str(rev1)},
        headers=headers("manager-a", shared_key),
    )
    assert resp1.status_code == 201
    data1 = resp1.json()

    # 2. Manager B (unauthorized on Interaction 1) attempts upload with same shared_key -> 404
    resp_b_leak = client.post(
        f"/api/v1/interactions/{iid1}/attachments",
        files={"file": ("doc_b_leak.pdf", SAMPLE_FILES["sample.pdf"])},
        headers=headers("manager-b", shared_key),
    )
    assert resp_b_leak.status_code == 404

    # 3. Manager B uploads to their OWN Interaction 2 with the same shared_key -> 201
    item2_b = create_interaction(client, "manager-b")
    iid2 = item2_b["id"]
    rev2 = item2_b["revision"]
    resp2 = client.post(
        f"/api/v1/interactions/{iid2}/attachments",
        files={"file": ("doc_b2.png", SAMPLE_FILES["sample.png"])},
        data={"expected_revision": str(rev2)},
        headers=headers("manager-b", shared_key),
    )
    assert resp2.status_code == 201
    data2 = resp2.json()
    assert data2["id"] != data1["id"]
    assert data2["file_name"] == "doc_b2.png"

    # 4. Manager A uploads to another of their OWN interactions (Interaction 3) with same shared_key -> 201
    item3_a = create_interaction(client, "manager-a")
    iid3 = item3_a["id"]
    rev3 = item3_a["revision"]
    resp3 = client.post(
        f"/api/v1/interactions/{iid3}/attachments",
        files={"file": ("doc_a3.pdf", SAMPLE_FILES["sample.pdf"])},
        data={"expected_revision": str(rev3)},
        headers=headers("manager-a", shared_key),
    )
    assert resp3.status_code == 201
    data3 = resp3.json()
    assert data3["id"] != data1["id"]
    assert data3["file_name"] == "doc_a3.pdf"


def test_attachment_upload_file_too_large_with_idempotency_key_permits_valid_retry(client):
    """Uploading oversized file (>25MB) with Idempotency-Key returns 413 and permits valid retry under same key."""
    item = create_interaction(client, "manager-a")
    iid = item["id"]
    rev = item["revision"]
    idem_key = f"oversize-retry-{uuid4()}"
    oversized_data = b"%PDF-1.4" + b"X" * (26 * 1024 * 1024)

    # 1. 26MB upload rejected with 413 FILE_TOO_LARGE
    resp_large = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("huge.pdf", oversized_data)},
        data={"expected_revision": str(rev)},
        headers=headers("manager-a", idem_key),
    )
    assert resp_large.status_code == 413
    assert resp_large.json()["error"]["code"] == "FILE_TOO_LARGE"

    # 2. Immediate retry under the same key with valid <=25MB file succeeds with 201
    resp_ok = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("valid_size.pdf", SAMPLE_FILES["sample.pdf"])},
        data={"expected_revision": str(rev)},
        headers=headers("manager-a", idem_key),
    )
    assert resp_ok.status_code == 201, resp_ok.text
    assert resp_ok.json()["file_name"] == "valid_size.pdf"

    det = client.get(f"/api/v1/interactions/{iid}", headers=headers("manager-a")).json()
    assert det["revision"] == rev + 1
    assert len(det["attachments"]) == 1


def test_attachment_upload_multiple_sequential_cas_and_event_sequence_integrity(client):
    """Multiple sequential uploads with CAS advance revision and maintain event sequence without collision."""
    item = create_interaction(client, "manager-a")
    iid = item["id"]
    rev = item["revision"]

    # Upload 1: expected_revision=rev -> becomes rev + 1
    resp1 = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("seq1.pdf", SAMPLE_FILES["sample.pdf"])},
        data={"expected_revision": str(rev)},
        headers=headers("manager-a"),
    )
    assert resp1.status_code == 201

    # Upload 2: expected_revision=rev + 1 -> becomes rev + 2
    resp2 = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("seq2.png", SAMPLE_FILES["sample.png"])},
        data={"expected_revision": str(rev + 1)},
        headers=headers("manager-a"),
    )
    assert resp2.status_code == 201

    # Upload 3 with stale revision (rev) -> 409 REVISION_CONFLICT
    resp_stale = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("seq3_stale.pdf", SAMPLE_FILES["sample.pdf"])},
        data={"expected_revision": str(rev)},
        headers=headers("manager-a"),
    )
    assert resp_stale.status_code == 409
    assert resp_stale.json()["error"]["code"] == "REVISION_CONFLICT"

    # Detail view confirms both attachments, revision = rev + 2, and strictly monotonic event sequences
    det = client.get(f"/api/v1/interactions/{iid}", headers=headers("manager-a")).json()
    assert det["revision"] == rev + 2
    assert len(det["attachments"]) == 2
    assert [a["file_name"] for a in det["attachments"]] == ["seq1.pdf", "seq2.png"]

    events = det["events"]
    att_events = [e for e in events if e["type"] == "attachment_uploaded"]
    assert len(att_events) == 2
    seqs = [e["sequence"] for e in events]
    assert seqs == sorted(seqs)
    assert len(seqs) == len(set(seqs))


def test_attachment_preview_inline_header(client):
    """disposition=inline returns Content-Disposition: inline with file stream."""
    item = create_interaction(client, "manager-a")
    iid = item["id"]

    resp = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("preview_doc.pdf", SAMPLE_FILES["sample.pdf"])},
        headers=headers("manager-a"),
    )
    assert resp.status_code == 201
    att_id = resp.json()["id"]

    # Inline disposition
    preview_resp = client.get(
        f"/api/v1/interactions/{iid}/attachments/{att_id}/download",
        params={"disposition": "inline"},
        headers=headers("manager-a"),
    )
    assert preview_resp.status_code == 200
    assert preview_resp.content == SAMPLE_FILES["sample.pdf"]
    assert preview_resp.headers["content-type"] == "application/pdf"
    assert "Content-Disposition" in preview_resp.headers
    cd = preview_resp.headers["Content-Disposition"]
    assert cd.startswith("inline")
    assert "preview_doc.pdf" in cd

    # Default (no disposition parameter) is attachment
    default_resp = client.get(
        f"/api/v1/interactions/{iid}/attachments/{att_id}/download",
        headers=headers("manager-a"),
    )
    assert default_resp.status_code == 200
    assert default_resp.headers["Content-Disposition"].startswith("attachment")

    # Invalid disposition value is rejected with 422
    invalid_resp = client.get(
        f"/api/v1/interactions/{iid}/attachments/{att_id}/download",
        params={"disposition": "invalid"},
        headers=headers("manager-a"),
    )
    assert invalid_resp.status_code == 422


def test_attachment_delete_success_and_audit_event(client, app):
    """Controlled deletion unlinks file from disk, deletes record from DB, logs attachment_deleted event, and increments revision."""
    from pathlib import Path
    from sqlalchemy import select
    from app.models import Attachment

    item = create_interaction(client, "manager-a")
    iid = item["id"]

    up = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("to_delete.png", SAMPLE_FILES["sample.png"])},
        headers=headers("manager-a"),
    )
    assert up.status_code == 201
    att_id = up.json()["id"]

    det_before = client.get(f"/api/v1/interactions/{iid}", headers=headers("manager-a")).json()
    rev_before = det_before["revision"]

    # Find file path on disk
    with app.state.session_factory() as session:
        att = session.scalar(select(Attachment).where(Attachment.id == att_id))
        assert att is not None
        file_path = Path(att.file_path)
        assert file_path.is_file()

    # Perform DELETE
    del_resp = client.delete(
        f"/api/v1/interactions/{iid}/attachments/{att_id}",
        headers=headers("manager-a"),
    )
    assert del_resp.status_code == 200, del_resp.text
    del_data = del_resp.json()
    assert del_data["status"] == "ok"
    assert del_data["deleted_attachment_id"] == att_id
    assert del_data["revision"] == rev_before + 1

    # Verify physical file is gone
    assert not file_path.exists(), "File was not removed from disk"

    # Verify DB record is gone
    with app.state.session_factory() as session:
        att_check = session.scalar(select(Attachment).where(Attachment.id == att_id))
        assert att_check is None, "Attachment record was not deleted from DB"

    # Verify detail view has 0 attachments, incremented revision in DB, and has attachment_deleted event
    det = client.get(f"/api/v1/interactions/{iid}", headers=headers("manager-a")).json()
    assert len(det["attachments"]) == 0
    assert det["revision"] == rev_before + 1
    del_events = [e for e in det["events"] if e["type"] == "attachment_deleted"]
    assert len(del_events) == 1
    ev = del_events[0]
    assert ev["attachment_id"] == att_id
    assert ev["file_name"] == "to_delete.png"
    assert ev["file_size"] == len(SAMPLE_FILES["sample.png"])
    assert ev["checksum"] == hashlib.sha256(SAMPLE_FILES["sample.png"]).hexdigest()
    assert ev["actor_name"] == "Анна Смирнова"

    # Verify attempting to download deleted attachment returns 404 NOT_FOUND
    dl_after = client.get(
        f"/api/v1/interactions/{iid}/attachments/{att_id}/download",
        headers=headers("manager-a"),
    )
    assert dl_after.status_code == 404
    assert dl_after.json()["error"]["code"] == "NOT_FOUND"


def test_attachment_delete_rbac_and_scope(client):
    """Scope isolation returns 404 for foreign interaction; non-author manager returns 403; supervisor/admin returns 200."""
    # Manager A creates interaction and uploads attachment
    item_a = create_interaction(client, "manager-a")
    iid_a = item_a["id"]

    up = client.post(
        f"/api/v1/interactions/{iid_a}/attachments",
        files={"file": ("rbac_doc.pdf", SAMPLE_FILES["sample.pdf"])},
        headers=headers("manager-a"),
    )
    assert up.status_code == 201
    att_id = up.json()["id"]

    # 1. 152-ФЗ Scope isolation: Manager B (foreign interaction) attempts delete -> 404 NOT_FOUND
    del_foreign = client.delete(
        f"/api/v1/interactions/{iid_a}/attachments/{att_id}",
        headers=headers("manager-b"),
    )
    assert del_foreign.status_code == 404
    assert del_foreign.json()["error"]["code"] == "NOT_FOUND"

    # Non-existent attachment returns 404
    del_nonexistent = client.delete(
        f"/api/v1/interactions/{iid_a}/attachments/{str(uuid4())}",
        headers=headers("manager-a"),
    )
    assert del_nonexistent.status_code == 404
    assert del_nonexistent.json()["error"]["code"] == "NOT_FOUND"

    det_a = client.get(f"/api/v1/interactions/{iid_a}", headers=headers("manager-a")).json()
    rev_a = det_a["revision"]

    # 2. Assign interaction to Manager B so Manager B now has scoped access,
    # but Manager B is NOT the author of the attachment uploaded by Manager A
    assign_resp = client.post(
        f"/api/v1/interactions/{iid_a}/assignments",
        json={"owner_id": "manager-b", "expected_revision": rev_a, "reason": "Передача для проверки прав"},
        headers=headers("supervisor", str(uuid4())),
    )
    assert assign_resp.status_code == 200

    # Manager B attempts delete: scoped, but not author and not supervisor/admin -> 403 FORBIDDEN
    del_non_author = client.delete(
        f"/api/v1/interactions/{iid_a}/attachments/{att_id}",
        headers=headers("manager-b"),
    )
    assert del_non_author.status_code == 403
    assert del_non_author.json()["error"]["code"] == "FORBIDDEN"

    # 3. Supervisor can delete attachment -> 200 OK
    del_sup = client.delete(
        f"/api/v1/interactions/{iid_a}/attachments/{att_id}",
        headers=headers("supervisor"),
    )
    assert del_sup.status_code == 200
    assert del_sup.json()["status"] == "ok"


def test_attachment_delete_cas_optimistic_lock(client, app):
    """Deletion with stale expected_revision raises 409 REVISION_CONFLICT and leaves file and DB intact."""
    from pathlib import Path
    from sqlalchemy import select
    from app.models import Attachment

    item = create_interaction(client, "manager-a")
    iid = item["id"]

    up = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("cas_doc.pdf", SAMPLE_FILES["sample.pdf"])},
        headers=headers("manager-a"),
    )
    assert up.status_code == 201
    att_id = up.json()["id"]

    with app.state.session_factory() as session:
        att = session.scalar(select(Attachment).where(Attachment.id == att_id))
        assert att is not None
        file_path = Path(att.file_path)
        assert file_path.is_file()

    det_before = client.get(f"/api/v1/interactions/{iid}", headers=headers("manager-a")).json()
    current_rev = det_before["revision"]

    # 1. Stale revision -> 409 Conflict
    stale_resp = client.delete(
        f"/api/v1/interactions/{iid}/attachments/{att_id}",
        params={"expected_revision": 999},
        headers=headers("manager-a"),
    )
    assert stale_resp.status_code == 409
    assert stale_resp.json()["error"]["code"] == "REVISION_CONFLICT"

    # Confirm file and DB record are untouched
    assert file_path.exists()
    with app.state.session_factory() as session:
        assert session.scalar(select(Attachment).where(Attachment.id == att_id)) is not None

    det = client.get(f"/api/v1/interactions/{iid}", headers=headers("manager-a")).json()
    assert det["revision"] == current_rev
    assert len(det["attachments"]) == 1
    assert not any(e["type"] == "attachment_deleted" for e in det["events"])

    # 2. Correct expected_revision -> 200 OK and revision increments
    ok_resp = client.delete(
        f"/api/v1/interactions/{iid}/attachments/{att_id}",
        params={"expected_revision": current_rev},
        headers=headers("manager-a"),
    )
    assert ok_resp.status_code == 200
    assert ok_resp.json()["revision"] == current_rev + 1
    assert not file_path.exists()


def test_attachment_delete_idempotency(client):
    """Replaying DELETE with the same Idempotency-Key returns cached response without side effects."""
    item = create_interaction(client, "manager-a")
    iid = item["id"]

    up = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("idem_doc.pdf", SAMPLE_FILES["sample.pdf"])},
        headers=headers("manager-a"),
    )
    assert up.status_code == 201
    att_id = up.json()["id"]

    det_before = client.get(f"/api/v1/interactions/{iid}", headers=headers("manager-a")).json()
    current_rev = det_before["revision"]
    idem_key = f"del-idem-{uuid4()}"

    # Request 1
    del1 = client.delete(
        f"/api/v1/interactions/{iid}/attachments/{att_id}",
        params={"expected_revision": current_rev},
        headers=headers("manager-a", idem_key),
    )
    assert del1.status_code == 200, del1.text
    data1 = del1.json()
    assert data1["status"] == "ok"
    assert data1["deleted_attachment_id"] == att_id
    assert data1["revision"] == current_rev + 1

    # Request 2 (replay)
    del2 = client.delete(
        f"/api/v1/interactions/{iid}/attachments/{att_id}",
        params={"expected_revision": current_rev},
        headers=headers("manager-a", idem_key),
    )
    assert del2.status_code == 200
    assert del2.json() == data1

    # Request 3 (replay again)
    del3 = client.delete(
        f"/api/v1/interactions/{iid}/attachments/{att_id}",
        params={"expected_revision": current_rev},
        headers=headers("manager-a", idem_key),
    )
    assert del3.status_code == 200
    assert del3.json() == data1

    # Verify detail: only 1 attachment_deleted event, revision unchanged
    det = client.get(f"/api/v1/interactions/{iid}", headers=headers("manager-a")).json()
    assert det["revision"] == current_rev + 1
    assert len(det["attachments"]) == 0
    del_events = [e for e in det["events"] if e["type"] == "attachment_deleted"]
    assert len(del_events) == 1

    # Mismatched payload with same key returns 409 IDEMPOTENCY_CONFLICT
    conflict_resp = client.delete(
        f"/api/v1/interactions/{iid}/attachments/{att_id}",
        params={"expected_revision": current_rev + 5},
        headers=headers("manager-a", idem_key),
    )
    assert conflict_resp.status_code == 409
    assert conflict_resp.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_attachment_delete_missing_file_on_disk_still_cleans_up_db_and_events(client, app):
    """If file is already deleted on disk, delete_attachment does not crash and cleans up DB + logs event."""
    from pathlib import Path
    from sqlalchemy import select
    from app.models import Attachment, InteractionEvent

    item = create_interaction(client, "manager-a")
    iid = item["id"]

    up = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("ghost.png", SAMPLE_FILES["sample.png"])},
        headers=headers("manager-a"),
    )
    att_id = up.json()["id"]

    # Delete physical file behind the scenes
    with app.state.session_factory() as session:
        att = session.scalar(select(Attachment).where(Attachment.id == att_id))
        p = Path(att.file_path)
        if p.exists():
            p.unlink()

    # Call DELETE endpoint
    del_resp = client.delete(
        f"/api/v1/interactions/{iid}/attachments/{att_id}",
        headers=headers("manager-a"),
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "ok"

    # Verify DB record is gone and audit event recorded
    with app.state.session_factory() as session:
        assert session.scalar(select(Attachment).where(Attachment.id == att_id)) is None
        events = list(session.scalars(
            select(InteractionEvent).where(
                InteractionEvent.interaction_id == iid,
                InteractionEvent.type == "attachment_deleted"
            )
        ))
        assert len(events) == 1
        assert events[0].payload.get("file_name") == "ghost.png"


def test_attachment_delete_expected_revision_boundary_validation(client):
    """Validation rejects non-positive expected_revision."""
    item = create_interaction(client, "manager-a")
    iid = item["id"]
    fake_att = str(uuid4())

    # 0 is rejected
    r0 = client.delete(
        f"/api/v1/interactions/{iid}/attachments/{fake_att}",
        params={"expected_revision": 0},
        headers=headers("manager-a"),
    )
    assert r0.status_code == 422

    # Negative is rejected
    r_neg = client.delete(
        f"/api/v1/interactions/{iid}/attachments/{fake_att}",
        params={"expected_revision": -1},
        headers=headers("manager-a"),
    )
    assert r_neg.status_code == 422

    # Non-digit header is rejected
    r_str = client.delete(
        f"/api/v1/interactions/{iid}/attachments/{fake_att}",
        headers={**headers("manager-a"), "expected-revision": "not-a-number"},
    )
    assert r_str.status_code == 422


def test_attachment_delete_idempotency_key_length_and_whitespace(client):
    """Whitespace-only and over-200-char Idempotency-Key are rejected."""
    item = create_interaction(client, "manager-a")
    iid = item["id"]
    fake_att = str(uuid4())

    # Whitespace only
    r_ws = client.delete(
        f"/api/v1/interactions/{iid}/attachments/{fake_att}",
        headers=headers("manager-a", "   "),
    )
    assert r_ws.status_code == 422

    # Over 200 chars
    r_long = client.delete(
        f"/api/v1/interactions/{iid}/attachments/{fake_att}",
        headers=headers("manager-a", "k" * 201),
    )
    assert r_long.status_code == 422


def test_attachment_delete_cross_interaction_isolation(client, app):
    """Deleting attachment via a different interaction ID returns 404 NOT_FOUND and leaves file untouched."""
    from pathlib import Path
    from sqlalchemy import select
    from app.models import Attachment

    item1 = create_interaction(client, "manager-a")
    item2 = create_interaction(client, "manager-a")
    iid1, iid2 = item1["id"], item2["id"]

    up = client.post(
        f"/api/v1/interactions/{iid1}/attachments",
        files={"file": ("cross_test.pdf", SAMPLE_FILES["sample.pdf"])},
        headers=headers("manager-a"),
    )
    assert up.status_code == 201
    att_id = up.json()["id"]

    with app.state.session_factory() as session:
        att = session.scalar(select(Attachment).where(Attachment.id == att_id))
        assert att is not None
        p = Path(att.file_path)
        assert p.is_file()

    # Manager A tries to delete attachment of iid1 using iid2 in the path -> 404 NOT_FOUND
    cross_del = client.delete(
        f"/api/v1/interactions/{iid2}/attachments/{att_id}",
        headers=headers("manager-a"),
    )
    assert cross_del.status_code == 404
    assert cross_del.json()["error"]["code"] == "NOT_FOUND"

    # File and DB record are intact
    assert p.is_file()
    with app.state.session_factory() as session:
        assert session.scalar(select(Attachment).where(Attachment.id == att_id)) is not None

    # Interaction 2 has no events
    det2 = client.get(f"/api/v1/interactions/{iid2}", headers=headers("manager-a")).json()
    assert not any(e["type"] == "attachment_deleted" for e in det2["events"])


def test_attachment_delete_administrator_rbac_and_scope(client, app):
    """Administrator access follows 152-ФЗ scope and interactions.write permission invariants."""
    from app.models import OrganizationAccess, User

    item = create_interaction(client, "manager-a")
    iid = item["id"]
    org_id = item["organization_id"]

    up = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("admin_test.pdf", SAMPLE_FILES["sample.pdf"])},
        headers=headers("manager-a"),
    )
    assert up.status_code == 201
    att_id = up.json()["id"]

    # 1. Administrator without OrganizationAccess -> 404 NOT_FOUND (152-ФЗ scope concealment)
    r_unscoped = client.delete(
        f"/api/v1/interactions/{iid}/attachments/{att_id}",
        headers=headers("administrator"),
    )
    assert r_unscoped.status_code == 404

    # 2. Grant OrganizationAccess(read_all=True) to administrator, but without interactions.write -> 403 FORBIDDEN
    with app.state.session_factory() as session:
        grant = OrganizationAccess(user_id="administrator", organization_id=org_id, read_all=True, can_create=False)
        session.merge(grant)
        admin = session.get(User, "administrator")
        admin.permissions = ["reports.read"]
        session.commit()

    r_no_perm = client.delete(
        f"/api/v1/interactions/{iid}/attachments/{att_id}",
        headers=headers("administrator"),
    )
    assert r_no_perm.status_code == 403
    assert r_no_perm.json()["error"]["code"] == "FORBIDDEN"

    # 3. Grant interactions.write to administrator -> 200 OK
    with app.state.session_factory() as session:
        admin = session.get(User, "administrator")
        admin.permissions = ["interactions.write", "reports.read"]
        session.commit()

    r_ok = client.delete(
        f"/api/v1/interactions/{iid}/attachments/{att_id}",
        headers=headers("administrator"),
    )
    assert r_ok.status_code == 200
    assert r_ok.json()["status"] == "ok"


def test_attachment_download_disposition_boundary_validation(client):
    """Boundary testing of disposition query parameter."""
    item = create_interaction(client, "manager-a")
    iid = item["id"]

    up = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("disp_test.png", SAMPLE_FILES["sample.png"])},
        headers=headers("manager-a"),
    )
    att_id = up.json()["id"]

    # Uppercase INLINE is rejected (strict regex)
    r_upper = client.get(
        f"/api/v1/interactions/{iid}/attachments/{att_id}/download",
        params={"disposition": "INLINE"},
        headers=headers("manager-a"),
    )
    assert r_upper.status_code == 422

    # Empty string disposition is rejected
    r_empty = client.get(
        f"/api/v1/interactions/{iid}/attachments/{att_id}/download",
        params={"disposition": ""},
        headers=headers("manager-a"),
    )
    assert r_empty.status_code == 422

    # Valid attachment disposition
    r_att = client.get(
        f"/api/v1/interactions/{iid}/attachments/{att_id}/download",
        params={"disposition": "attachment"},
        headers=headers("manager-a"),
    )
    assert r_att.status_code == 200
    assert r_att.headers["content-disposition"].startswith("attachment")


def test_attachment_delete_concurrency_race(client):
    """Concurrent deletion of the same attachment results in exactly one success and one conflict/not found."""
    import concurrent.futures

    item = create_interaction(client, "manager-a")
    iid = item["id"]

    up = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("race_doc.pdf", SAMPLE_FILES["sample.pdf"])},
        headers=headers("manager-a"),
    )
    att_id = up.json()["id"]

    def perform_delete(key):
        return client.delete(
            f"/api/v1/interactions/{iid}/attachments/{att_id}",
            headers=headers("manager-a", key),
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(perform_delete, f"key-race-{uuid4()}")
        f2 = executor.submit(perform_delete, f"key-race-{uuid4()}")
        r1 = f1.result()
        r2 = f2.result()

    statuses = sorted([r1.status_code, r2.status_code])
    # Exactly one must succeed (200) and one must fail (404 Not Found or 409 Conflict)
    assert statuses[0] == 200
    assert statuses[1] in (404, 409)

    det = client.get(f"/api/v1/interactions/{iid}", headers=headers("manager-a")).json()
    assert len(det["attachments"]) == 0
    del_events = [e for e in det["events"] if e["type"] == "attachment_deleted"]
    assert len(del_events) == 1


def test_swe23_attachment_preview_contract(client):
    """Verify swe_23 contract: direct window.open preview without AttachmentPreviewModal,
    inline disposition streaming with correct MIME type (PDF, PNG, JPEG), 152-FZ access scope enforcement,
    disposition validation, and popup blocker/window lifecycle safety."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]

    # 1. Backend contract: check PDF, PNG, and JPEG inline streaming
    item = create_interaction(client, "manager-a")
    iid = item["id"]
    pdf_up = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("contract_preview.pdf", SAMPLE_FILES["sample.pdf"])},
        headers=headers("manager-a"),
    )
    assert pdf_up.status_code == 201
    pdf_id = pdf_up.json()["id"]

    pdf_resp = client.get(
        f"/api/v1/interactions/{iid}/attachments/{pdf_id}/download",
        params={"disposition": "inline"},
        headers=headers("manager-a"),
    )
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert "inline" in pdf_resp.headers.get("content-disposition", "")
    assert "contract_preview.pdf" in pdf_resp.headers.get("content-disposition", "")

    # PNG inline streaming check
    png_up = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("diagram_preview.png", SAMPLE_FILES["sample.png"])},
        headers=headers("manager-a"),
    )
    assert png_up.status_code == 201
    png_id = png_up.json()["id"]

    png_resp = client.get(
        f"/api/v1/interactions/{iid}/attachments/{png_id}/download",
        params={"disposition": "inline"},
        headers=headers("manager-a"),
    )
    assert png_resp.status_code == 200
    assert png_resp.headers["content-type"] == "image/png"
    assert "inline" in png_resp.headers.get("content-disposition", "")

    # JPEG inline streaming check
    jpeg_up = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("photo_preview.jpeg", SAMPLE_FILES["sample.jpeg"])},
        headers=headers("manager-a"),
    )
    assert jpeg_up.status_code == 201
    jpeg_id = jpeg_up.json()["id"]

    jpeg_resp = client.get(
        f"/api/v1/interactions/{iid}/attachments/{jpeg_id}/download",
        params={"disposition": "inline"},
        headers=headers("manager-a"),
    )
    assert jpeg_resp.status_code == 200
    assert jpeg_resp.headers["content-type"] == "image/jpeg"
    assert "inline" in jpeg_resp.headers.get("content-disposition", "")

    # Default disposition is attachment when omitted
    def_resp = client.get(
        f"/api/v1/interactions/{iid}/attachments/{pdf_id}/download",
        headers=headers("manager-a"),
    )
    assert def_resp.status_code == 200
    assert "attachment" in def_resp.headers.get("content-disposition", "")

    # Invalid disposition parameter rejected with 422
    inv_resp = client.get(
        f"/api/v1/interactions/{iid}/attachments/{pdf_id}/download",
        params={"disposition": "invalid_value"},
        headers=headers("manager-a"),
    )
    assert inv_resp.status_code == 422

    # 152-FZ scope isolation: unauthorized manager receives 404
    unauth_resp = client.get(
        f"/api/v1/interactions/{iid}/attachments/{pdf_id}/download",
        params={"disposition": "inline"},
        headers=headers("manager-b"),
    )
    assert unauth_resp.status_code == 404

    # 2. Frontend contract: verify InteractionPage.tsx directly uses window.open, has no AttachmentPreviewModal,
    # and handles popup blocker / targetWindow.closed safely.
    frontend_page = root / "frontend" / "src" / "views" / "InteractionPage.tsx"
    assert frontend_page.exists()
    content = frontend_page.read_text(encoding="utf-8")
    assert "AttachmentPreviewModal" not in content, "AttachmentPreviewModal must be eliminated to prevent CSP iframe block"
    assert "window.open('about:blank', '_blank')" in content, "Must open blank target window synchronously to prevent popup blocking"
    assert "targetWindow.closed" in content, "Must guard targetWindow against user close"
    assert "disposition=inline" in content, "Preview must request inline disposition"
    assert "safeCleanup" in content, "Lifecycle cleanup must be safe and idempotent"



