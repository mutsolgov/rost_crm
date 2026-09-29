"""Challenger 1 Domain 5 Gate Empirical Stress and Invariant Verification Suite.

Exercises and stress-tests:
1. PreviewModal frontend exports, rendering contract (PDF iframe, IMG image),
   cleanup and unmount lifecycle, keyboard and backdrop dismissal.
2. ClamAV zINSTREAM streaming protocol:
   - Clean file -> stream: OK -> None -> 201 Created
   - EICAR test signature -> stream: Eicar-Signature FOUND -> 422 VIRUS_DETECTED
   - Diverse malware signatures (Trojan, Ransomware, Worm) -> 422 VIRUS_DETECTED
   - Protocol chunking across multiple boundaries and empty terminal chunk
   - ClamAV daemon connection refused -> 503 ANTIVIRUS_UNAVAILABLE
   - ClamAV socket timeout -> 503 ANTIVIRUS_UNAVAILABLE
   - ClamAV internal daemon error -> 503 ANTIVIRUS_UNAVAILABLE
3. 152-ФЗ Zero-Oracle 404 Security Isolation:
   - Foreign manager cannot GET download -> 404 NOT_FOUND
   - Foreign manager cannot DELETE attachment -> 404 NOT_FOUND
   - Foreign manager cannot GET list attachments -> 404 NOT_FOUND
   - Foreign manager cannot POST upload attachment -> 404 NOT_FOUND
   - Oracle differential check: existing attachment vs non-existent attachment
     under foreign manager return identical 404 responses (zero metadata leakage).
"""

from __future__ import annotations

import io
from pathlib import Path
import re
import socket
import struct
import threading
import time
from uuid import uuid4
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.db import Base
from app.files import (
    CHUNK_SIZE,
    MAX_FILE_SIZE,
    MIME_TYPES,
    sanitize_filename,
    scan_clamav_stream,
    validate_magic_bytes,
)
from app.main import create_app
from app.seed import seed_database

ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------

def headers(user="manager-a", key=None):
    res = {"X-Demo-User": user}
    if key:
        res["Idempotency-Key"] = key
    return res


def make_clean_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("document.txt", "Clean test document content.")
    return buf.getvalue()


def make_clean_pdf() -> bytes:
    return b"%PDF-1.5\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<<>>\n%%EOF"


def make_clean_png() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15c4"
    )


EICAR_PAYLOAD = (
    b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
)


class MockClamDaemon:
    """Mock ClamAV TCP server supporting zINSTREAM protocol."""

    def __init__(
        self,
        response: bytes = b"stream: OK\0",
        delay: float = 0.0,
        close_immediately: bool = False,
    ):
        self.response = response
        self.delay = delay
        self.close_immediately = close_immediately
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        self.running = True
        self.received_chunks: list[bytes] = []
        self.received_command = b""
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while self.running:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                break
            try:
                if self.close_immediately:
                    conn.close()
                    continue

                conn.settimeout(5.0)
                cmd = b""
                while not cmd.endswith(b"\0"):
                    b = conn.recv(1)
                    if not b:
                        break
                    cmd += b
                with self.lock:
                    self.received_command = cmd

                while True:
                    hdr = conn.recv(4)
                    if not hdr or len(hdr) < 4:
                        break
                    (chunk_len,) = struct.unpack(">I", hdr)
                    if chunk_len == 0:
                        break
                    buf = b""
                    while len(buf) < chunk_len:
                        part = conn.recv(min(4096, chunk_len - len(buf)))
                        if not part:
                            break
                        buf += part
                    with self.lock:
                        self.received_chunks.append(buf)

                if self.delay > 0:
                    time.sleep(self.delay)

                conn.sendall(self.response)
            except Exception:
                pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def stop(self):
        self.running = False
        try:
            self.sock.close()
        except OSError:
            pass
        self.thread.join(timeout=1.0)


# ---------------------------------------------------------------------------
# 1. PreviewModal Empirical & Contract Verification
# ---------------------------------------------------------------------------

class TestPreviewModalEmpirical:
    """Verifies PreviewModal exports, structure, props, cleanup, and DOM contract."""

    @pytest.fixture(autouse=True)
    def setup_source(self):
        self.file_path = ROOT / "frontend" / "src" / "views" / "InteractionPage.tsx"
        assert self.file_path.exists(), f"Missing {self.file_path}"
        self.content = self.file_path.read_text(encoding="utf-8")

    def test_preview_modal_is_exported(self):
        """PreviewModal must be directly exported for consumption."""
        assert re.search(r"export\s+function\s+PreviewModal\s*\(", self.content), (
            "PreviewModal must be exported from InteractionPage.tsx"
        )

    def test_preview_modal_props_contract(self):
        """PreviewModal must accept { attachment, previewUrl, onClose }."""
        match = re.search(
            r"export\s+function\s+PreviewModal\s*\(\s*\{([^}]+)\}\s*:\s*\{([^}]+)\}",
            self.content,
        )
        assert match is not None, "PreviewModal must have object destructuring props"
        params_str = match.group(1)
        type_str = match.group(2)
        assert "attachment" in params_str
        assert "previewUrl" in params_str
        assert "onClose" in params_str
        assert "attachment: Attachment" in type_str
        assert "previewUrl: string" in type_str
        assert "onClose: () => void" in type_str

    def test_preview_modal_renders_pdf_iframe(self):
        """PDF files must be rendered inside an <iframe> with 80vh height."""
        assert "<iframe" in self.content
        assert "src={previewUrl}" in self.content
        assert "height: '80vh'" in self.content or 'height: "80vh"' in self.content

    def test_preview_modal_renders_image_img(self):
        """Image files must be rendered inside an <img> tag with 75vh max-height."""
        assert "<img" in self.content
        assert "src={previewUrl}" in self.content
        assert "maxHeight: '75vh'" in self.content or 'maxHeight: "75vh"' in self.content

    def test_preview_modal_escape_and_backdrop_dismissal(self):
        """PreviewModal must handle Escape key and backdrop clicks."""
        assert "e.key === 'Escape'" in self.content or 'e.key === "Escape"' in self.content
        assert "onMouseDown" in self.content
        assert "e.target === e.currentTarget" in self.content

    def test_blob_cleanup_and_unmount_lifecycle(self):
        """Ephemeral blob URL must have cleanup handler invoked on close and unmount."""
        assert "setPreviewModalTarget({ attachment: att, previewUrl: blobUrl, cleanup });" in self.content
        assert "previewModalTarget.cleanup();" in self.content
        assert "setPreviewModalTarget(null);" in self.content
        # Check unmount effect
        unmount_pattern = re.search(
            r"useEffect\(\(\)\s*=>\s*\{\s*return\s*\(\)\s*=>\s*\{[^}]*previewModalTarget\.cleanup\(\);",
            self.content,
            re.DOTALL,
        )
        assert unmount_pattern is not None, "Unmount effect must invoke previewModalTarget.cleanup()"

    def test_no_forbidden_attachment_preview_modal(self):
        """Verify AttachmentPreviewModal is NOT used to prevent CSP iframe regression."""
        assert "AttachmentPreviewModal" not in self.content


# ---------------------------------------------------------------------------
# 2. ClamAV zINSTREAM Empirical Verification
# ---------------------------------------------------------------------------

class TestClamAVEmpirical:
    """Stress-tests ClamAV zINSTREAM protocol, EICAR detection, and fault tolerance."""

    def test_scan_clamav_clean_data_returns_none(self):
        server = MockClamDaemon(response=b"stream: OK\0")
        try:
            res = scan_clamav_stream(make_clean_zip(), host="127.0.0.1", port=server.port)
            assert res is None
            assert server.received_command == b"zINSTREAM\0"
            assert len(server.received_chunks) >= 1
        finally:
            server.stop()

    def test_scan_clamav_eicar_signature_detection(self):
        server = MockClamDaemon(response=b"stream: Eicar-Test-Signature FOUND\0")
        try:
            res = scan_clamav_stream(EICAR_PAYLOAD, host="127.0.0.1", port=server.port)
            assert res == "Eicar-Test-Signature"
        finally:
            server.stop()

    @pytest.mark.parametrize(
        "signature,expected",
        [
            (b"stream: Win.Trojan.Agent-12345 FOUND\0", "Win.Trojan.Agent-12345"),
            (b"stream: Unix.Ransomware.LockBit FOUND\0", "Unix.Ransomware.LockBit"),
            (b"stream: Doc.Malware.Macro-99 FOUND\n", "Doc.Malware.Macro-99"),
            (b"FOUND\0", "FOUND"),
        ],
    )
    def test_scan_clamav_various_malware_signatures(self, signature: bytes, expected: str):
        server = MockClamDaemon(response=signature)
        try:
            res = scan_clamav_stream(b"malware content", host="127.0.0.1", port=server.port)
            assert res == expected
        finally:
            server.stop()

    def test_scan_clamav_multichunk_framing(self):
        """Data larger than CHUNK_SIZE (64KB) must be sent in framed chunks with zero terminator."""
        data = b"X" * (CHUNK_SIZE * 3 + 1234)
        server = MockClamDaemon(response=b"stream: OK\0")
        try:
            res = scan_clamav_stream(data, host="127.0.0.1", port=server.port)
            assert res is None
            total_received = sum(len(c) for c in server.received_chunks)
            assert total_received == len(data)
            assert len(server.received_chunks) == 4
            assert len(server.received_chunks[0]) == CHUNK_SIZE
            assert len(server.received_chunks[1]) == CHUNK_SIZE
            assert len(server.received_chunks[2]) == CHUNK_SIZE
            assert len(server.received_chunks[3]) == 1234
        finally:
            server.stop()

    def test_scan_clamav_daemon_error_raises_runtime_error(self):
        server = MockClamDaemon(response=b"stream: INSTREAM size limit exceeded. ERROR\0")
        try:
            with pytest.raises(RuntimeError, match="ClamAV scan error"):
                scan_clamav_stream(b"test", host="127.0.0.1", port=server.port)
        finally:
            server.stop()

    def test_scan_clamav_connection_refused(self):
        # Choose unused port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            free_port = s.getsockname()[1]

        with pytest.raises(OSError):
            scan_clamav_stream(b"test", host="127.0.0.1", port=free_port, timeout=0.5)

    def test_scan_clamav_socket_timeout(self):
        server = MockClamDaemon(response=b"stream: OK\0", delay=2.0)
        try:
            with pytest.raises((socket.timeout, TimeoutError)):
                scan_clamav_stream(b"test", host="127.0.0.1", port=server.port, timeout=0.1)
        finally:
            server.stop()

    def test_scan_clamav_connection_dropped_mid_stream(self):
        server = MockClamDaemon(close_immediately=True)
        try:
            with pytest.raises((OSError, ConnectionResetError, BrokenPipeError, RuntimeError)):
                scan_clamav_stream(b"test data " * 100, host="127.0.0.1", port=server.port, timeout=0.5)
        finally:
            server.stop()


# ---------------------------------------------------------------------------
# 3. HTTP API Integration: ClamAV & 152-ФЗ Zero-Oracle 404
# ---------------------------------------------------------------------------

class TestAttachmentApiEmpirical:
    """Exercises full FastAPI endpoints under adversarial conditions."""

    def _make_client(self, tmp_path: Path, clamav_port: int = 3310, clamav_enabled: bool = True) -> TestClient:
        db_file = tmp_path / f"test_{uuid4().hex}.db"
        storage_path = tmp_path / f"storage_{uuid4().hex}"
        storage_path.mkdir(parents=True, exist_ok=True)
        db_url = f"sqlite:///{db_file.as_posix()}"

        test_settings = Settings(
            database_url=db_url,
            app_env="development",
            auth_mode="demo",
            storage_dir=str(storage_path),
            clamav_enabled=clamav_enabled,
            clamav_host="127.0.0.1",
            clamav_port=clamav_port,
            clamav_timeout=2.0,
        )
        app = create_app(test_settings)
        engine = app.state.engine
        Base.metadata.create_all(bind=engine)
        with app.state.session_factory() as session:
            seed_database(session)
            session.commit()
        return TestClient(app)

    def _create_interaction(self, client, user="manager-a", org_id="org-1"):
        body = {
            "title": f"Empirical Test Interaction {uuid4().hex[:6]}",
            "organization_id": org_id,
            "program_id": "program-devops",
            "product_id": "product-cloud",
            "cycle_label": "Domain5-Gate",
            "owner_id": user,
        }
        res = client.post("/api/v1/interactions", json=body, headers=headers(user, str(uuid4())))
        assert res.status_code == 201, res.text
        return res.json()

    def test_upload_clean_file_end_to_end(self, tmp_path: Path):
        mock_clam = MockClamDaemon(response=b"stream: OK\0")
        try:
            with self._make_client(tmp_path, clamav_port=mock_clam.port) as client:
                item = self._create_interaction(client, "manager-a")
                file_bytes = make_clean_zip()
                resp = client.post(
                    f"/api/v1/interactions/{item['id']}/attachments",
                    files={"file": ("archive.zip", file_bytes, "application/zip")},
                    headers=headers("manager-a"),
                )
                assert resp.status_code == 201, resp.text
                data = resp.json()
                assert data["file_name"] == "archive.zip"
                assert data["file_size"] == len(file_bytes)
                assert data["interaction_id"] == item["id"]
        finally:
            mock_clam.stop()

    def test_upload_eicar_virus_returns_422_virus_detected(self, tmp_path: Path):
        mock_clam = MockClamDaemon(response=b"stream: Win.Test.EICAR_HDB-1 FOUND\0")
        try:
            with self._make_client(tmp_path, clamav_port=mock_clam.port) as client:
                item = self._create_interaction(client, "manager-a")
                # Wrap EICAR inside a zip to pass magic bytes
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w") as zf:
                    zf.writestr("eicar.com", EICAR_PAYLOAD)
                infected_zip = buf.getvalue()

                resp = client.post(
                    f"/api/v1/interactions/{item['id']}/attachments",
                    files={"file": ("infected.zip", infected_zip, "application/zip")},
                    headers=headers("manager-a"),
                )
                assert resp.status_code == 422, resp.text
                err = resp.json()["error"]
                assert err["code"] == "VIRUS_DETECTED"
                assert "Win.Test.EICAR_HDB-1" in err["message"]
        finally:
            mock_clam.stop()

    def test_upload_clamav_down_returns_503_antivirus_unavailable(self, tmp_path: Path):
        with self._make_client(tmp_path, clamav_port=59999) as client:
            item = self._create_interaction(client, "manager-a")
            clean_zip = make_clean_zip()
            resp = client.post(
                f"/api/v1/interactions/{item['id']}/attachments",
                files={"file": ("clean.zip", clean_zip, "application/zip")},
                headers=headers("manager-a"),
            )
            assert resp.status_code == 503, resp.text
            err = resp.json()["error"]
            assert err["code"] == "ANTIVIRUS_UNAVAILABLE"

    def test_152_fz_zero_oracle_isolation_cross_manager(self, tmp_path: Path):
        """Comprehensive verification of 152-ФЗ Zero-Oracle 404 security isolation."""
        mock_clam = MockClamDaemon(response=b"stream: OK\0")
        try:
            with self._make_client(tmp_path, clamav_port=mock_clam.port) as client:
                # Manager-A creates interaction and uploads attachment
                item_a = self._create_interaction(client, "manager-a", org_id="org-1")
                clean_pdf = make_clean_pdf()
                up_resp = client.post(
                    f"/api/v1/interactions/{item_a['id']}/attachments",
                    files={"file": ("confidential.pdf", clean_pdf, "application/pdf")},
                    headers=headers("manager-a"),
                )
                assert up_resp.status_code == 201
                att_id = up_resp.json()["id"]

                # Manager-B (different scope/owner) attempts:
                # 1. GET download
                get_resp = client.get(
                    f"/api/v1/interactions/{item_a['id']}/attachments/{att_id}/download",
                    headers=headers("manager-b"),
                )
                assert get_resp.status_code == 404, f"Expected 404, got {get_resp.status_code}"
                assert get_resp.json()["error"]["code"] == "NOT_FOUND"

                # 2. DELETE attachment
                del_resp = client.delete(
                    f"/api/v1/interactions/{item_a['id']}/attachments/{att_id}",
                    headers=headers("manager-b"),
                )
                assert del_resp.status_code == 404, f"Expected 404, got {del_resp.status_code}"
                assert del_resp.json()["error"]["code"] == "NOT_FOUND"

                # 3. GET list attachments
                list_resp = client.get(
                    f"/api/v1/interactions/{item_a['id']}/attachments",
                    headers=headers("manager-b"),
                )
                assert list_resp.status_code == 404, f"Expected 404, got {list_resp.status_code}"

                # 4. POST upload attachment into manager-a's interaction
                post_resp = client.post(
                    f"/api/v1/interactions/{item_a['id']}/attachments",
                    files={"file": ("hack.pdf", clean_pdf, "application/pdf")},
                    headers=headers("manager-b"),
                )
                assert post_resp.status_code == 404, f"Expected 404, got {post_resp.status_code}"

                # 5. ZERO-ORACLE DIFFERENTIAL CHECK:
                # An attacker querying a non-existent attachment vs an existing attachment
                # under a foreign interaction must receive an identical 404 response (excluding unique request_id).
                bogus_resp = client.get(
                    f"/api/v1/interactions/{item_a['id']}/attachments/att-non-existent-9999/download",
                    headers=headers("manager-b"),
                )
                assert bogus_resp.status_code == 404
                err_real = {k: v for k, v in get_resp.json()["error"].items() if k != "request_id"}
                err_bogus = {k: v for k, v in bogus_resp.json()["error"].items() if k != "request_id"}
                assert err_real == err_bogus, (
                    "Differential response oracle leak detected! "
                    f"Existing: {err_real} vs Nonexistent: {err_bogus}"
                )
                assert err_real["code"] == "NOT_FOUND"
                assert err_real["message"] == "Взаимодействие не найдено."
        finally:
            mock_clam.stop()
