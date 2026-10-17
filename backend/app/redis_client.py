"""Pure Python standard library Redis client implementing RESP (REdis Serialization Protocol).

Zero external dependencies: uses only socket, ssl, urllib.parse, threading, queue, io.
Provides thread-safe connection pooling, timeouts, URL parsing, and offline resilience.
"""
from __future__ import annotations

import io
import logging
import os
import queue
import socket
import ssl
import threading
import urllib.parse
from typing import Any

logger = logging.getLogger(__name__)


class RedisError(Exception):
    """Base exception for Redis errors."""
    pass


class Connection:
    """Represents a single TCP/TLS socket connection to a Redis server with RESP parsing."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 6379,
        timeout: float = 1.0,
        password: str | None = None,
        db: int = 0,
        use_ssl: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.password = password
        self.db = db
        self.use_ssl = use_ssl
        self._sock: socket.socket | None = None
        self._reader: io.BufferedReader | None = None

    def connect(self) -> None:
        if self._sock is not None:
            return
        sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        sock.settimeout(self.timeout)
        if self.use_ssl:
            context = ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=self.host)
        self._sock = sock
        self._reader = sock.makefile("rb")

        # Initial handshake: AUTH and SELECT
        if self.password:
            self.send_command("AUTH", self.password)
        if self.db != 0:
            self.send_command("SELECT", str(self.db))

    def close(self) -> None:
        if self._reader is not None:
            try:
                self._reader.close()
            except Exception:
                pass
            self._reader = None
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def is_connected(self) -> bool:
        return self._sock is not None

    def _read_exact(self, n: int) -> bytes:
        if self._reader is None:
            raise RedisError("Connection not open")
        buf = bytearray()
        while len(buf) < n:
            chunk = self._reader.read(n - len(buf))
            if not chunk:
                raise RedisError("Unexpected EOF while reading socket")
            buf.extend(chunk)
        return bytes(buf)

    def _read_reply(self) -> Any:
        if self._reader is None:
            raise RedisError("Connection not open")
        line = self._reader.readline()
        if not line:
            raise RedisError("Connection closed by server")
        if not line.endswith(b"\r\n"):
            raise RedisError(f"Malformed RESP line ending: {line!r}")

        prefix = line[:1]
        payload = line[1:-2]

        if prefix == b"+":
            # Simple string
            return payload.decode("utf-8", errors="replace")
        elif prefix == b"-":
            # Error
            err_msg = payload.decode("utf-8", errors="replace")
            raise RedisError(err_msg)
        elif prefix == b":":
            # Integer
            return int(payload)
        elif prefix == b"$":
            # Bulk string
            length = int(payload)
            if length == -1:
                return None
            data = self._read_exact(length)
            crlf = self._reader.read(2)
            if crlf != b"\r\n":
                raise RedisError(f"Protocol error: expected CRLF after bulk string, got {crlf!r}")
            return data
        elif prefix == b"*":
            # Array
            count = int(payload)
            if count == -1:
                return None
            return [self._read_reply() for _ in range(count)]
        else:
            raise RedisError(f"Unknown RESP prefix: {prefix!r}")

    def send_command(self, *args: str | bytes | int) -> Any:
        self.connect()
        assert self._sock is not None
        parts = [f"*{len(args)}\r\n".encode("ascii")]
        for arg in args:
            if isinstance(arg, bytes):
                raw = arg
            elif isinstance(arg, str):
                raw = arg.encode("utf-8")
            elif isinstance(arg, (int, float)):
                raw = str(arg).encode("ascii")
            else:
                raw = str(arg).encode("utf-8")
            parts.append(f"${len(raw)}\r\n".encode("ascii"))
            parts.append(raw)
            parts.append(b"\r\n")

        self._sock.sendall(b"".join(parts))
        return self._read_reply()


class ConnectionPool:
    """Thread-safe connection pool for Redis connections using a LIFO queue."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 6379,
        timeout: float = 1.0,
        max_connections: int = 20,
        password: str | None = None,
        db: int = 0,
        use_ssl: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.max_connections = max_connections
        self.password = password
        self.db = db
        self.use_ssl = use_ssl
        self._pool: queue.LifoQueue[Connection] = queue.LifoQueue(maxsize=max_connections)
        self._created_connections = 0
        self._lock = threading.Lock()

    def get_connection(self) -> Connection:
        try:
            return self._pool.get_nowait()
        except queue.Empty:
            with self._lock:
                if self._created_connections < self.max_connections:
                    self._created_connections += 1
                    return Connection(
                        host=self.host,
                        port=self.port,
                        timeout=self.timeout,
                        password=self.password,
                        db=self.db,
                        use_ssl=self.use_ssl,
                    )
            # Pool full, wait with timeout
            try:
                return self._pool.get(timeout=self.timeout)
            except queue.Empty:
                raise RedisError("Connection pool exhausted (timeout waiting for free connection)")

    def release_connection(self, conn: Connection, discard: bool = False) -> None:
        if discard:
            conn.close()
            with self._lock:
                self._created_connections = max(0, self._created_connections - 1)
        else:
            try:
                self._pool.put_nowait(conn)
            except queue.Full:
                conn.close()
                with self._lock:
                    self._created_connections = max(0, self._created_connections - 1)

    def close(self) -> None:
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except queue.Empty:
                break
        with self._lock:
            self._created_connections = 0


class RedisClient:
    """Lightweight stdlib Redis client implementing basic RESP operations."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 6379,
        timeout: float = 1.0,
        pool: ConnectionPool | None = None,
        **kwargs: Any,
    ) -> None:
        if pool is not None:
            self.pool = pool
        else:
            self.pool = ConnectionPool(host=host, port=port, timeout=timeout, **kwargs)

    @classmethod
    def from_url(cls, url: str, timeout: float = 1.0, max_connections: int = 20) -> RedisClient:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 6379
        db = 0
        if parsed.path and parsed.path != "/":
            try:
                db = int(parsed.path.lstrip("/"))
            except ValueError:
                db = 0
        password = parsed.password
        use_ssl = parsed.scheme == "rediss"

        pool = ConnectionPool(
            host=host,
            port=port,
            timeout=timeout,
            max_connections=max_connections,
            password=password,
            db=db,
            use_ssl=use_ssl,
        )
        return cls(pool=pool)

    def execute_command(self, *args: str | bytes | int) -> Any:
        conn = self.pool.get_connection()
        discard = False
        try:
            return conn.send_command(*args)
        except Exception:
            discard = True
            raise
        finally:
            self.pool.release_connection(conn, discard=discard)

    def ping(self) -> bool:
        """Check server connectivity. Returns True if PONG received, False otherwise."""
        try:
            reply = self.execute_command("PING")
            return reply == "PONG" or reply == b"PONG"
        except Exception:
            return False

    def get(self, key: str) -> bytes | None:
        """Get the binary value of a key. Returns bytes, or None if key missing or server offline."""
        try:
            reply = self.execute_command("GET", key)
            if reply is None:
                return None
            if isinstance(reply, bytes):
                return reply
            if isinstance(reply, str):
                return reply.encode("utf-8")
            return None
        except Exception:
            return None

    def set(self, key: str, value: bytes | str) -> bool:
        """Set key to hold binary string value. Returns True on success, False otherwise."""
        try:
            reply = self.execute_command("SET", key, value)
            return reply == "OK" or reply == b"OK"
        except Exception:
            return False

    def setex(self, key: str, seconds: int, value: bytes | str) -> bool:
        """Set key with expiration in seconds. Returns True on success, False otherwise."""
        try:
            reply = self.execute_command("SETEX", key, int(seconds), value)
            return reply == "OK" or reply == b"OK"
        except Exception:
            return False

    def delete(self, key: str) -> bool:
        """Delete a key. Returns True if deleted (count > 0), False otherwise."""
        try:
            reply = self.execute_command("DEL", key)
            return isinstance(reply, int) and reply > 0
        except Exception:
            return False

    def close(self) -> None:
        """Close connection pool and release all sockets."""
        try:
            self.pool.close()
        except Exception:
            pass


_DEFAULT_CLIENT: RedisClient | None = None
_CLIENT_LOCK = threading.Lock()


def get_redis_client(url: str | None = None) -> RedisClient:
    """Return a shared RedisClient instance configured from settings or REDIS_URL."""
    global _DEFAULT_CLIENT
    if url is not None:
        return RedisClient.from_url(url)

    with _CLIENT_LOCK:
        if _DEFAULT_CLIENT is None:
            redis_url = os.getenv("REDIS_URL")
            if not redis_url:
                try:
                    from .config import get_settings
                    redis_url = get_settings().redis_url
                except Exception:
                    redis_url = "redis://127.0.0.1:6379/0"
            _DEFAULT_CLIENT = RedisClient.from_url(redis_url)
        return _DEFAULT_CLIENT
