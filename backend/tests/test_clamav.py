import io
from pathlib import Path
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
from app.files import CHUNK_SIZE, scan_clamav_stream
from app.main import create_app
from app.seed import seed_database


def headers(user="manager-a", key=None):
    res = {"X-Demo-User": user}
    if key:
        res["Idempotency-Key"] = key
    return res


def create_interaction(client, user="manager-a", org_id=None):
    body = {
        "title": "Взаимодействие для тестирования ClamAV",
        "organization_id": org_id or "org-1",
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "cycle_label": "Цикл-ClamAV",
        "owner_id": user,
    }
    response = client.post("/api/v1/interactions", json=body, headers=headers(user, str(uuid4())))
    assert response.status_code == 201, response.text
    return response.json()


def make_clean_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("clean.txt", "This is a clean test file.")
    return buf.getvalue()


class MockClamAVServer:
    def __init__(
        self,
        response: bytes = b"stream: OK\0",
        delay: float = 0.0,
        abort_after_chunks: int | None = None,
    ):
        self.response = response
        self.delay = delay
        self.abort_after_chunks = abort_after_chunks
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        self.is_running = True
        self.received_command = b""
        self.raw_received_data = b""
        self.received_chunks = []
        self.done_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while self.is_running:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                break
            threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()

    def _handle_client(self, conn: socket.socket):
        with conn:
            try:
                # Read command up to \0 or \n
                cmd = b""
                while b"\0" not in cmd and b"\n" not in cmd:
                    b = conn.recv(1)
                    if not b:
                        break
                    cmd += b
                self.received_command = cmd

                # Read INSTREAM chunks
                while True:
                    len_bytes = b""
                    while len(len_bytes) < 4:
                        part = conn.recv(4 - len(len_bytes))
                        if not part:
                            break
                        len_bytes += part
                    if len(len_bytes) < 4:
                        break
                    self.raw_received_data += len_bytes
                    (chunk_len,) = struct.unpack(">I", len_bytes)
                    if chunk_len == 0:
                        self.received_chunks.append((0, b""))
                        self.done_event.set()
                        break
                    chunk = b""
                    while len(chunk) < chunk_len:
                        part = conn.recv(chunk_len - len(chunk))
                        if not part:
                            break
                        chunk += part
                    self.raw_received_data += chunk
                    self.received_chunks.append((chunk_len, chunk))

                    if self.abort_after_chunks is not None and len(self.received_chunks) >= self.abort_after_chunks:
                        return

                if self.delay > 0:
                    time.sleep(self.delay)

                if self.response:
                    conn.sendall(self.response)
            except Exception:
                pass

    def stop(self):
        self.is_running = False
        try:
            self.sock.close()
        except OSError:
            pass
        self.thread.join(timeout=1.0)


def get_free_closed_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def make_test_client(tmp_path: Path, **settings_kwargs) -> TestClient:
    s = Settings(
        database_url=f"sqlite:///{(tmp_path / f'test_{uuid4().hex}.db').as_posix()}",
        app_env="development",
        auth_mode="demo",
        storage_dir=str(tmp_path / "storage"),
        **settings_kwargs,
    )
    application = create_app(s)
    Base.metadata.create_all(application.state.engine)
    with application.state.session_factory() as session:
        seed_database(session)
        session.commit()
    return TestClient(application)


# --- Unit tests for scan_clamav_stream ---


def test_scan_clamav_stream_clean_returns_none():
    server = MockClamAVServer(response=b"stream: OK\0")
    try:
        result = scan_clamav_stream(b"hello world", "127.0.0.1", server.port)
        assert result is None
    finally:
        server.stop()


def test_scan_clamav_stream_virus_eicar_detected():
    server = MockClamAVServer(response=b"stream: Eicar-Signature FOUND\0")
    try:
        result = scan_clamav_stream(b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR", "127.0.0.1", server.port)
        assert result == "Eicar-Signature"
    finally:
        server.stop()


def test_scan_clamav_stream_virus_variant_signature():
    server = MockClamAVServer(response=b"stream: Win.Test.EICAR_HDB-1 FOUND\n")
    try:
        result = scan_clamav_stream(b"sample bytes", "127.0.0.1", server.port)
        assert result == "Win.Test.EICAR_HDB-1"
    finally:
        server.stop()


def test_scan_clamav_stream_error_raises_runtime_error():
    server = MockClamAVServer(response=b"stream: Out of memory ERROR\0")
    try:
        with pytest.raises(RuntimeError, match="ClamAV scan error"):
            scan_clamav_stream(b"test", "127.0.0.1", server.port)
    finally:
        server.stop()


def test_scan_clamav_stream_connection_refused():
    closed_port = get_free_closed_port()
    with pytest.raises(OSError):
        scan_clamav_stream(b"test", "127.0.0.1", closed_port, timeout=0.5)


def test_scan_clamav_stream_timeout():
    server = MockClamAVServer(response=b"stream: OK\0", delay=0.5)
    try:
        with pytest.raises(TimeoutError):
            scan_clamav_stream(b"test", "127.0.0.1", server.port, timeout=0.05)
    finally:
        server.stop()


def test_instream_protocol_framing_and_chunking():
    # Test data larger than CHUNK_SIZE (64KB) to verify chunk splitting
    total_bytes = 150_000
    test_data = b"B" * total_bytes

    server = MockClamAVServer(response=b"stream: OK\0")
    try:
        res = scan_clamav_stream(test_data, "127.0.0.1", server.port)
        assert res is None
        assert server.done_event.wait(timeout=2.0)

        # 1. Command must be zINSTREAM\0
        assert server.received_command == b"zINSTREAM\0"

        # 2. Check chunks: all except terminator must be <= CHUNK_SIZE
        assert len(server.received_chunks) == 4  # 65536 + 65536 + 18928 + 0
        expected_lengths = [65536, 65536, 18928, 0]
        actual_lengths = [length for length, _ in server.received_chunks]
        assert actual_lengths == expected_lengths

        # 3. Final chunk must be length 0
        assert server.received_chunks[-1] == (0, b"")

        # 4. Reassembled data must be identical to sent data
        reassembled = b"".join(chunk for length, chunk in server.received_chunks if length > 0)
        assert reassembled == test_data

        # 5. Verify byte framing: each chunk starts with struct.pack(">I", length)
        offset = 0
        for length in expected_lengths:
            expected_prefix = struct.pack(">I", length)
            assert server.raw_received_data[offset : offset + 4] == expected_prefix
            offset += 4 + length
        assert offset == len(server.raw_received_data)
    finally:
        server.stop()


# --- HTTP API integration tests ---


def test_upload_clean_file_passes_when_clamav_enabled(tmp_path: Path):
    server = MockClamAVServer(response=b"stream: OK\0")
    try:
        with make_test_client(
            tmp_path,
            clamav_enabled=True,
            clamav_host="127.0.0.1",
            clamav_port=server.port,
        ) as client:
            item = create_interaction(client)
            clean_content = make_clean_zip()

            resp = client.post(
                f"/api/v1/interactions/{item['id']}/attachments",
                files={"file": ("clean_doc.zip", clean_content)},
                headers=headers("manager-a"),
            )
            assert resp.status_code == 201, resp.text
            data = resp.json()
            assert data["file_name"] == "clean_doc.zip"
            assert data["file_size"] == len(clean_content)

            # Verify download works
            down = client.get(
                f"/api/v1/interactions/{item['id']}/attachments/{data['id']}/download",
                headers=headers("manager-a"),
            )
            assert down.status_code == 200
            assert down.content == clean_content
    finally:
        server.stop()


def test_upload_virus_blocked_with_422_virus_detected(tmp_path: Path):
    server = MockClamAVServer(response=b"stream: Eicar-Signature FOUND\0")
    try:
        with make_test_client(
            tmp_path,
            clamav_enabled=True,
            clamav_host="127.0.0.1",
            clamav_port=server.port,
        ) as client:
            item = create_interaction(client)
            eicar_zip = make_clean_zip()

            resp = client.post(
                f"/api/v1/interactions/{item['id']}/attachments",
                files={"file": ("infected.zip", eicar_zip)},
                headers=headers("manager-a"),
            )
            assert resp.status_code == 422, resp.text
            err = resp.json().get("error", {})
            assert err.get("code") == "VIRUS_DETECTED"
            assert "Eicar-Signature" in err.get("message", "")
            assert "Обнаружена вредоносная сигнатура" in err.get("message", "")

            # Verify no attachment was saved in DB
            list_resp = client.get(
                f"/api/v1/interactions/{item['id']}/attachments",
                headers=headers("manager-a"),
            )
            assert list_resp.status_code == 200
            assert len(list_resp.json()) == 0

            # Verify no file was written to disk in attachment directory
            att_dir = tmp_path / "storage" / "attachments" / item["id"]
            if att_dir.exists():
                assert list(att_dir.iterdir()) == []
    finally:
        server.stop()


def test_upload_clamav_unavailable_connection_refused_503(tmp_path: Path):
    closed_port = get_free_closed_port()
    with make_test_client(
        tmp_path,
        clamav_enabled=True,
        clamav_host="127.0.0.1",
        clamav_port=closed_port,
        clamav_timeout=0.5,
    ) as client:
        item = create_interaction(client)
        content = make_clean_zip()

        resp = client.post(
            f"/api/v1/interactions/{item['id']}/attachments",
            files={"file": ("test.zip", content)},
            headers=headers("manager-a"),
        )
        assert resp.status_code == 503, resp.text
        err = resp.json().get("error", {})
        assert err.get("code") == "ANTIVIRUS_UNAVAILABLE"
        assert "Сервис антивирусной проверки временно недоступен" in err.get("message", "")


def test_upload_clamav_timeout_503(tmp_path: Path):
    server = MockClamAVServer(response=b"stream: OK\0", delay=0.5)
    try:
        with make_test_client(
            tmp_path,
            clamav_enabled=True,
            clamav_host="127.0.0.1",
            clamav_port=server.port,
            clamav_timeout=0.05,
        ) as client:
            item = create_interaction(client)
            content = make_clean_zip()

            resp = client.post(
                f"/api/v1/interactions/{item['id']}/attachments",
                files={"file": ("test.zip", content)},
                headers=headers("manager-a"),
            )
            assert resp.status_code == 503, resp.text
            err = resp.json().get("error", {})
            assert err.get("code") == "ANTIVIRUS_UNAVAILABLE"
            assert "Сервис антивирусной проверки временно недоступен" in err.get("message", "")
    finally:
        server.stop()


def test_upload_disabled_clamav_skips_socket_entirely(tmp_path: Path):
    # Port is closed and would refuse connection if called
    closed_port = get_free_closed_port()
    with make_test_client(
        tmp_path,
        clamav_enabled=False,
        clamav_host="127.0.0.1",
        clamav_port=closed_port,
    ) as client:
        item = create_interaction(client)
        content = make_clean_zip()

        resp = client.post(
            f"/api/v1/interactions/{item['id']}/attachments",
            files={"file": ("clean.zip", content)},
            headers=headers("manager-a"),
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["file_name"] == "clean.zip"


def test_config_settings_clamav_env_parsing(monkeypatch):
    monkeypatch.setenv("CLAMAV_HOST", "clamav-node-1")
    monkeypatch.setenv("CLAMAV_PORT", "3311")
    monkeypatch.setenv("CLAMAV_ENABLED", "true")
    monkeypatch.setenv("CLAMAV_TIMEOUT", "15.5")

    get_settings.cache_clear()
    try:
        s = get_settings()
        assert s.clamav_host == "clamav-node-1"
        assert s.clamav_port == 3311
        assert s.clamav_enabled is True
        assert s.clamav_timeout == 15.5
    finally:
        get_settings.cache_clear()


def test_scan_clamav_stream_empty_data():
    server = MockClamAVServer(response=b"stream: OK\0")
    try:
        res = scan_clamav_stream(b"", "127.0.0.1", server.port)
        assert res is None
        assert server.done_event.wait(timeout=2.0)
        assert len(server.received_chunks) == 1
        assert server.received_chunks[0] == (0, b"")
    finally:
        server.stop()


def test_scan_clamav_stream_exact_64k_boundary():
    data = b"A" * CHUNK_SIZE
    server = MockClamAVServer(response=b"stream: OK\0")
    try:
        res = scan_clamav_stream(data, "127.0.0.1", server.port)
        assert res is None
        assert server.done_event.wait(timeout=2.0)
        assert len(server.received_chunks) == 2
        assert server.received_chunks[0] == (CHUNK_SIZE, data)
        assert server.received_chunks[1] == (0, b"")
    finally:
        server.stop()


def test_scan_clamav_stream_64k_plus_one_boundary():
    data = b"C" * (CHUNK_SIZE + 1)
    server = MockClamAVServer(response=b"stream: OK\0")
    try:
        res = scan_clamav_stream(data, "127.0.0.1", server.port)
        assert res is None
        assert server.done_event.wait(timeout=2.0)
        assert len(server.received_chunks) == 3
        assert server.received_chunks[0] == (CHUNK_SIZE, data[:CHUNK_SIZE])
        assert server.received_chunks[1] == (1, data[CHUNK_SIZE:])
        assert server.received_chunks[2] == (0, b"")
    finally:
        server.stop()


def test_scan_clamav_stream_error_containing_found_word():
    # ClamAV error description containing "FOUND" must not be misidentified as a virus detection
    server = MockClamAVServer(response=b"stream: Database not FOUND ERROR\0")
    try:
        with pytest.raises(RuntimeError, match="ClamAV scan error"):
            scan_clamav_stream(b"test", "127.0.0.1", server.port)
    finally:
        server.stop()


def test_scan_clamav_stream_error_containing_ok_token():
    # ClamAV error description containing "OK" must not be misidentified as clean
    server = MockClamAVServer(response=b"stream: TOKEN_VALIDATION_ERROR\0")
    try:
        with pytest.raises(RuntimeError, match="ClamAV scan error"):
            scan_clamav_stream(b"test", "127.0.0.1", server.port)
    finally:
        server.stop()


def test_scan_clamav_stream_virus_with_ok_in_name():
    # Virus signature whose name contains 'OK' (e.g. Loki variant) must be properly detected
    server = MockClamAVServer(response=b"stream: Win.Trojan.LOKI FOUND\0")
    try:
        res = scan_clamav_stream(b"virus-bytes", "127.0.0.1", server.port)
        assert res == "Win.Trojan.LOKI"
    finally:
        server.stop()


def test_scan_clamav_stream_instream_size_limit_exceeded():
    server = MockClamAVServer(response=b"INSTREAM size limit exceeded. ERROR\0")
    try:
        with pytest.raises(RuntimeError, match="ClamAV scan error"):
            scan_clamav_stream(b"big data", "127.0.0.1", server.port)
    finally:
        server.stop()


def test_scan_clamav_stream_connection_aborted_mid_stream():
    # Server disconnects after receiving 1st chunk
    server = MockClamAVServer(response=b"stream: OK\0", abort_after_chunks=1)
    try:
        data = b"M" * (CHUNK_SIZE * 3)
        with pytest.raises(OSError):
            scan_clamav_stream(data, "127.0.0.1", server.port, timeout=1.0)
    finally:
        server.stop()


def test_upload_clamav_error_with_found_word_returns_503(tmp_path: Path):
    server = MockClamAVServer(response=b"stream: Database not FOUND ERROR\0")
    try:
        with make_test_client(
            tmp_path,
            clamav_enabled=True,
            clamav_host="127.0.0.1",
            clamav_port=server.port,
        ) as client:
            item = create_interaction(client)
            content = make_clean_zip()
            resp = client.post(
                f"/api/v1/interactions/{item['id']}/attachments",
                files={"file": ("doc.zip", content)},
                headers=headers("manager-a"),
            )
            assert resp.status_code == 503, resp.text
            err = resp.json().get("error", {})
            assert err.get("code") == "ANTIVIRUS_UNAVAILABLE"
    finally:
        server.stop()


def test_upload_clamav_instream_size_limit_exceeded_503(tmp_path: Path):
    server = MockClamAVServer(response=b"INSTREAM size limit exceeded. ERROR\0")
    try:
        with make_test_client(
            tmp_path,
            clamav_enabled=True,
            clamav_host="127.0.0.1",
            clamav_port=server.port,
        ) as client:
            item = create_interaction(client)
            content = make_clean_zip()
            resp = client.post(
                f"/api/v1/interactions/{item['id']}/attachments",
                files={"file": ("doc.zip", content)},
                headers=headers("manager-a"),
            )
            assert resp.status_code == 503, resp.text
            err = resp.json().get("error", {})
            assert err.get("code") == "ANTIVIRUS_UNAVAILABLE"
    finally:
        server.stop()


def test_upload_clamav_aborted_connection_503(tmp_path: Path):
    server = MockClamAVServer(abort_after_chunks=1)
    try:
        with make_test_client(
            tmp_path,
            clamav_enabled=True,
            clamav_host="127.0.0.1",
            clamav_port=server.port,
        ) as client:
            item = create_interaction(client)
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("large.txt", "A" * (CHUNK_SIZE * 3))
            multi_chunk_zip = buf.getvalue()

            resp = client.post(
                f"/api/v1/interactions/{item['id']}/attachments",
                files={"file": ("multichunk.zip", multi_chunk_zip)},
                headers=headers("manager-a"),
            )
            assert resp.status_code == 503, resp.text
            err = resp.json().get("error", {})
            assert err.get("code") == "ANTIVIRUS_UNAVAILABLE"
    finally:
        server.stop()


def test_upload_clean_multichunk_file_e2e(tmp_path: Path):
    server = MockClamAVServer(response=b"stream: OK\0")
    try:
        with make_test_client(
            tmp_path,
            clamav_enabled=True,
            clamav_host="127.0.0.1",
            clamav_port=server.port,
        ) as client:
            item = create_interaction(client)
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
                zf.writestr("clean_large.txt", "L" * 150_000)
            clean_payload = buf.getvalue()

            resp = client.post(
                f"/api/v1/interactions/{item['id']}/attachments",
                files={"file": ("clean_multi.zip", clean_payload)},
                headers=headers("manager-a"),
            )
            assert resp.status_code == 201, resp.text
            data = resp.json()
            assert data["file_name"] == "clean_multi.zip"
            assert data["file_size"] == len(clean_payload)

            down = client.get(
                f"/api/v1/interactions/{item['id']}/attachments/{data['id']}/download",
                headers=headers("manager-a"),
            )
            assert down.status_code == 200
            assert down.content == clean_payload
    finally:
        server.stop()


def test_config_settings_clamav_env_resilience(monkeypatch):
    monkeypatch.setenv("CLAMAV_HOST", "")
    monkeypatch.setenv("CLAMAV_PORT", "not-a-port")
    monkeypatch.setenv("CLAMAV_ENABLED", "invalid_bool")
    monkeypatch.setenv("CLAMAV_TIMEOUT", "-5.0")

    get_settings.cache_clear()
    try:
        s = get_settings()
        assert s.clamav_host == "clamav"
        assert s.clamav_port == 3310
        assert s.clamav_enabled is False
        assert s.clamav_timeout == 10.0
    finally:
        get_settings.cache_clear()
