import hashlib
import io
import zipfile
from uuid import uuid4

import pytest

from app.files import MAX_FILE_SIZE


def headers(user="manager-a", key=None):
    res = {"X-Demo-User": user}
    if key:
        res["Idempotency-Key"] = key
    return res


def create_interaction(client, user="manager-a"):
    body = {
        "title": "Взаимодействие для тестирования вложений",
        "organization_id": "org-1",
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

