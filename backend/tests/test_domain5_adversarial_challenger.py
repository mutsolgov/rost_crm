"""
Domain 5 Adversarial & Boundary Condition Verification Suite.
Written by Challenger 2 for empirical verification of:
1. File size boundaries: 26,214,400 bytes (allowed) vs 26,214,401 bytes (rejected with 413).
2. Spoofed extensions: PE/ELF/Script headers inside .png, .pdf, .docx, .jpeg (rejected with 422).
3. Path traversal & null bytes: ../../etc/passwd, null bytes, sanitize to basename.
4. CAS concurrency: invalid expected_revision on upload and delete (rejected with 409).
5. Zero-Oracle 152-FZ access isolation (404 Not Found).
"""

import hashlib
import io
import zipfile
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.files import MAX_FILE_SIZE


def headers(user="manager-a", key=None):
    h = {"X-Demo-User": user}
    if key:
        h["Idempotency-Key"] = key
    return h


def create_test_interaction(client: TestClient, user="manager-a", org_id="org-1"):
    body = {
        "title": "Adversarial Test Interaction",
        "organization_id": org_id,
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "cycle_label": "Cycle-Adversarial",
        "owner_id": user,
    }
    resp = client.post("/api/v1/interactions", json=body, headers=headers(user, str(uuid4())))
    assert resp.status_code == 201, resp.text
    return resp.json()


# =========================================================================
# 1. FILE SIZE BOUNDARY TESTING (26,214,400 vs 26,214,401)
# =========================================================================

def test_file_size_boundary_exact_max_allowed(client: TestClient):
    """Exactly 26,214,400 bytes (25 MB) must be accepted with 201 Created."""
    item = create_test_interaction(client, "manager-a")
    iid = item["id"]

    # Construct exact 26,214,400 byte PDF
    prefix = b"%PDF-1.4\n"
    padding_len = MAX_FILE_SIZE - len(prefix)
    exact_bytes = prefix + (b"A" * padding_len)
    assert len(exact_bytes) == 26_214_400

    # Test via raw body stream upload
    resp = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        content=exact_bytes,
        headers={
            **headers("manager-a"),
            "Content-Type": "application/pdf",
            "Content-Disposition": 'attachment; filename="exact_25mb.pdf"',
        },
    )
    assert resp.status_code == 201, f"Expected 201 for exactly 26,214,400 bytes, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["file_size"] == 26_214_400
    assert data["checksum"] == hashlib.sha256(exact_bytes).hexdigest()
    att_id = data["id"]

    # Verify download preserves all 26,214,400 bytes
    down = client.get(
        f"/api/v1/interactions/{iid}/attachments/{att_id}/download",
        headers=headers("manager-a"),
    )
    assert down.status_code == 200
    assert len(down.content) == 26_214_400
    assert hashlib.sha256(down.content).hexdigest() == data["checksum"]


def test_file_size_boundary_one_byte_over_rejected(client: TestClient):
    """Exactly 26,214,401 bytes (25 MB + 1 byte) must be rejected with 413 FILE_TOO_LARGE."""
    item = create_test_interaction(client, "manager-a")
    iid = item["id"]

    prefix = b"%PDF-1.4\n"
    padding_len = (MAX_FILE_SIZE + 1) - len(prefix)
    oversized_bytes = prefix + (b"B" * padding_len)
    assert len(oversized_bytes) == 26_214_401

    # Raw upload test
    resp = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        content=oversized_bytes,
        headers={
            **headers("manager-a"),
            "Content-Type": "application/pdf",
            "Content-Disposition": 'attachment; filename="over_limit.pdf"',
        },
    )
    assert resp.status_code == 413, f"Expected 413 for 26,214,401 bytes, got {resp.status_code}: {resp.text}"
    err = resp.json()
    assert err["error"]["code"] == "FILE_TOO_LARGE"


# =========================================================================
# 2. SPOOFED EXTENSIONS & MALICIOUS HEADERS TESTING
# =========================================================================

@pytest.mark.parametrize(
    "spoofed_filename,payload,description",
    [
        ("fake.png", b"MZ\x90\x00\x03\x00\x00\x00" + b"A" * 50, "PE EXE header disguised as PNG"),
        ("fake.pdf", b"MZ\x90\x00\x03\x00\x00\x00" + b"B" * 50, "PE EXE header disguised as PDF"),
        ("fake.docx", b"\x7fELF\x02\x01\x01\x00" + b"C" * 50, "ELF binary header disguised as DOCX"),
        ("script.pdf", b"#!/bin/bash\necho bad\n" + b"D" * 50, "Bash script disguised as PDF"),
        ("webshell.png", b"<?php phpinfo(); ?>\n" + b"E" * 50, "PHP script disguised as PNG"),
        ("xss.jpeg", b"<script>alert(1)</script>" + b"F" * 50, "HTML/JS payload disguised as JPEG"),
        ("macho.pdf", b"\xca\xfe\xba\xbe" + b"G" * 50, "Mach-O / Java fat binary header disguised as PDF"),
        ("macho32.doc", b"\xfe\xed\xfa\xce" + b"H" * 50, "Mach-O 32-bit binary header disguised as DOC"),
        ("macho64.xls", b"\xfe\xed\xfa\xcf" + b"I" * 50, "Mach-O 64-bit binary header disguised as XLS"),
    ],
)
def test_spoofed_extension_magic_byte_rejection(client: TestClient, spoofed_filename, payload, description):
    """Malicious binary headers hidden behind allowed extensions must be rejected with 422 FILE_TYPE_NOT_ALLOWED."""
    item = create_test_interaction(client, "manager-a")
    iid = item["id"]

    resp = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": (spoofed_filename, payload)},
        headers=headers("manager-a"),
    )
    assert resp.status_code == 422, f"Failed for {description}: got {resp.status_code}: {resp.text}"
    err = resp.json()
    assert err["error"]["code"] == "FILE_TYPE_NOT_ALLOWED"


@pytest.mark.parametrize(
    "raw_filename,payload,description",
    [
        ("malware.exe", b"MZ\x90\x00\x03\x00\x00\x00" + b"A" * 50, "Direct PE executable"),
        ("trojan.dll", b"MZ\x90\x00\x03\x00\x00\x00" + b"B" * 50, "Direct DLL file"),
        ("script.sh", b"#!/bin/sh\nrm -rf /", "Direct shell script"),
        ("backdoor.php", b"<?php system($_GET['c']); ?>", "Direct PHP webshell"),
        ("batch.bat", b"@echo off\ndir", "Direct batch file"),
        ("exploit.py", b"import os; os.system('id')", "Direct Python script"),
        ("unknown.bin", b"\x00\x01\x02\x03\x04\x05", "Direct generic binary"),
    ],
)
def test_disallowed_extension_rejection(client: TestClient, raw_filename, payload, description):
    """Disallowed file extensions must be rejected with 422 FILE_TYPE_NOT_ALLOWED."""
    item = create_test_interaction(client, "manager-a")
    iid = item["id"]

    resp = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": (raw_filename, payload)},
        headers=headers("manager-a"),
    )
    assert resp.status_code == 422, f"Failed for {description}: got {resp.status_code}: {resp.text}"
    err = resp.json()
    assert err["error"]["code"] == "FILE_TYPE_NOT_ALLOWED"


# =========================================================================
# 3. PATH TRAVERSAL & FILENAME SANITIZATION TESTING
# =========================================================================

def test_path_traversal_no_allowed_extension(client: TestClient):
    """Path traversal filename without allowed extension must be rejected with 422."""
    item = create_test_interaction(client, "manager-a")
    iid = item["id"]

    payload = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    resp = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("../../../../etc/passwd", payload)},
        headers=headers("manager-a"),
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "FILE_TYPE_NOT_ALLOWED"


def test_path_traversal_sanitized_to_basename(client: TestClient):
    """Path traversal attempts with valid extension must be sanitized to basename."""
    item = create_test_interaction(client, "manager-a")
    iid = item["id"]

    payload = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    traversal_names = [
        ("..\\..\\..\\windows\\system32\\drivers.pdf", "drivers.pdf"),
        ("../../../../../var/log/syslog.pdf", "syslog.pdf"),
        ("./././secret.pdf", "secret.pdf"),
    ]
    for traversal_name, expected_basename in traversal_names:
        resp = client.post(
            f"/api/v1/interactions/{iid}/attachments",
            files={"file": (traversal_name, payload)},
            headers=headers("manager-a"),
        )
        assert resp.status_code == 201, f"Failed for {traversal_name}: {resp.text}"
        assert resp.json()["file_name"] == expected_basename


def test_null_byte_in_filename_rejected(client: TestClient):
    """Filenames with null bytes (poison null byte attack) must be rejected with 422."""
    item = create_test_interaction(client, "manager-a")
    iid = item["id"]

    payload = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    resp = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("innocent.pdf\x00.exe", payload)},
        headers=headers("manager-a"),
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "FILE_TYPE_NOT_ALLOWED"


# =========================================================================
# 4. CAS CONCURRENCY & REVISION TESTING ON UPLOAD AND DELETE
# =========================================================================

def test_upload_cas_invalid_expected_revision_conflict(client: TestClient):
    """Uploading with mismatched expected_revision must return 409 Conflict."""
    item = create_test_interaction(client, "manager-a")
    iid = item["id"]
    current_rev = item["revision"]

    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"

    # Send stale revision (current_rev + 10)
    resp = client.post(
        f"/api/v1/interactions/{iid}/attachments?expected_revision={current_rev + 10}",
        files={"file": ("cas_test.pdf", pdf_bytes)},
        headers=headers("manager-a"),
    )
    assert resp.status_code == 409, f"Expected 409, got {resp.status_code}: {resp.text}"
    err = resp.json()
    assert err["error"]["code"] == "REVISION_CONFLICT"


def test_upload_cas_valid_revision_increments(client: TestClient):
    """Uploading with matching expected_revision succeeds and bumps revision."""
    item = create_test_interaction(client, "manager-a")
    iid = item["id"]
    initial_rev = item["revision"]

    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"

    resp = client.post(
        f"/api/v1/interactions/{iid}/attachments?expected_revision={initial_rev}",
        files={"file": ("cas_success.pdf", pdf_bytes)},
        headers=headers("manager-a"),
    )
    assert resp.status_code == 201

    # Check updated revision on interaction
    detail = client.get(f"/api/v1/interactions/{iid}", headers=headers("manager-a")).json()
    assert detail["revision"] == initial_rev + 1


def test_delete_cas_invalid_expected_revision_conflict(client: TestClient):
    """Deleting an attachment with mismatched expected_revision must return 409 Conflict."""
    item = create_test_interaction(client, "manager-a")
    iid = item["id"]

    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    up_resp = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("to_delete.pdf", pdf_bytes)},
        headers=headers("manager-a"),
    )
    assert up_resp.status_code == 201
    att_id = up_resp.json()["id"]

    # Current revision after upload
    detail = client.get(f"/api/v1/interactions/{iid}", headers=headers("manager-a")).json()
    current_rev = detail["revision"]

    # Attempt delete with wrong expected_revision
    del_resp = client.delete(
        f"/api/v1/interactions/{iid}/attachments/{att_id}?expected_revision={current_rev + 5}",
        headers=headers("manager-a"),
    )
    assert del_resp.status_code == 409, f"Expected 409, got {del_resp.status_code}: {del_resp.text}"
    assert del_resp.json()["error"]["code"] == "REVISION_CONFLICT"

    # Successful delete with correct expected_revision
    del_ok = client.delete(
        f"/api/v1/interactions/{iid}/attachments/{att_id}?expected_revision={current_rev}",
        headers=headers("manager-a"),
    )
    assert del_ok.status_code == 200
    assert del_ok.json()["status"] == "ok"
    assert del_ok.json()["revision"] == current_rev + 1


def test_delete_negative_or_zero_expected_revision_rejected(client: TestClient):
    """Deleting with non-positive expected_revision must return 422 Validation Error."""
    item = create_test_interaction(client, "manager-a")
    iid = item["id"]

    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    up_resp = client.post(
        f"/api/v1/interactions/{iid}/attachments",
        files={"file": ("boundary_rev.pdf", pdf_bytes)},
        headers=headers("manager-a"),
    )
    assert up_resp.status_code == 201
    att_id = up_resp.json()["id"]

    # expected_revision=0
    resp0 = client.delete(
        f"/api/v1/interactions/{iid}/attachments/{att_id}?expected_revision=0",
        headers=headers("manager-a"),
    )
    assert resp0.status_code == 422

    # expected_revision=-1
    resp_neg = client.delete(
        f"/api/v1/interactions/{iid}/attachments/{att_id}?expected_revision=-1",
        headers=headers("manager-a"),
    )
    assert resp_neg.status_code == 422


# =========================================================================
# 5. ZERO-ORACLE 152-FZ ACCESS ISOLATION
# =========================================================================

def test_zero_oracle_cross_manager_isolation(client: TestClient):
    """Manager B must receive strict 404 for all operations on Manager A's attachments."""
    item_a = create_test_interaction(client, "manager-a", org_id="org-1")
    iid_a = item_a["id"]

    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    up_resp = client.post(
        f"/api/v1/interactions/{iid_a}/attachments",
        files={"file": ("manager_a_secret.pdf", pdf_bytes)},
        headers=headers("manager-a"),
    )
    assert up_resp.status_code == 201
    att_id = up_resp.json()["id"]

    # 1. Manager B tries to list attachments -> 404
    list_b = client.get(f"/api/v1/interactions/{iid_a}/attachments", headers=headers("manager-b"))
    assert list_b.status_code == 404
    assert list_b.json()["error"]["code"] == "NOT_FOUND"

    # 2. Manager B tries to download attachment -> 404
    down_b = client.get(f"/api/v1/interactions/{iid_a}/attachments/{att_id}/download", headers=headers("manager-b"))
    assert down_b.status_code == 404
    assert down_b.json()["error"]["code"] == "NOT_FOUND"

    # 3. Manager B tries to upload to Manager A's interaction -> 404
    up_b = client.post(
        f"/api/v1/interactions/{iid_a}/attachments",
        files={"file": ("injected.pdf", pdf_bytes)},
        headers=headers("manager-b"),
    )
    assert up_b.status_code == 404
    assert up_b.json()["error"]["code"] == "NOT_FOUND"

    # 4. Manager B tries to delete Manager A's attachment -> 404
    del_b = client.delete(
        f"/api/v1/interactions/{iid_a}/attachments/{att_id}",
        headers=headers("manager-b"),
    )
    assert del_b.status_code == 404
    assert del_b.json()["error"]["code"] == "NOT_FOUND"
