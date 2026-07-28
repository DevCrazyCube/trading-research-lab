"""Minimal RFC 6455 WebSocket client. Standard library only - no dependency added.

Deliberately dependency-free: this project is local-only and its own repository review
(research/MEMECOIN_BOT_REPOSITORY_REVIEW.md) flagged unvetted dependencies around
signing-capable software as a recurring failure. Receive path preserves raw bytes so a
caller can persist provider frames unchanged (capture-first).

Supports: TLS, client-masked sends, continuation frames, ping/pong, close.
Not supported: permessage-deflate (we ask for no extensions), redirects.
"""
import base64
import hashlib
import os
import socket
import ssl
import struct
from urllib.parse import urlparse

OP_CONT, OP_TEXT, OP_BIN, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA


class WSError(Exception):
    pass


class WebSocket:
    def __init__(self, url, timeout=60):
        u = urlparse(url)
        secure = u.scheme in ("wss", "https")
        port = u.port or (443 if secure else 80)
        host = u.hostname
        path = (u.path or "/") + (f"?{u.query}" if u.query else "")

        raw = socket.create_connection((host, port), timeout=timeout)
        if secure:
            ctx = ssl.create_default_context()
            raw = ctx.wrap_socket(raw, server_hostname=host)
        self.sock = raw
        self.sock.settimeout(timeout)
        self._buf = b""

        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        self.sock.sendall(req.encode())
        head = self._read_until(b"\r\n\r\n")
        status = head.split(b"\r\n", 1)[0].decode(errors="replace")
        if " 101 " not in status:
            raise WSError(f"handshake failed: {status} :: {head[:300]!r}")
        headers = {}
        for line in head.split(b"\r\n")[1:]:
            if b":" in line:
                name, value = line.split(b":", 1)
                headers[name.strip().lower()] = value.strip()
        expected = base64.b64encode(hashlib.sha1(
            (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()
        ).digest())
        if headers.get(b"sec-websocket-accept") != expected:
            self.sock.close()
            raise WSError("invalid Sec-WebSocket-Accept")

    # ---------------------------------------------------------------- low level
    def _read_until(self, marker):
        while marker not in self._buf:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise WSError("connection closed during handshake")
            self._buf += chunk
        idx = self._buf.index(marker) + len(marker)
        out, self._buf = self._buf[:idx], self._buf[idx:]
        return out

    def _read_exact(self, n):
        while len(self._buf) < n:
            chunk = self.sock.recv(max(65536, n - len(self._buf)))
            if not chunk:
                raise WSError("connection closed")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def _read_frame(self):
        b0, b1 = self._read_exact(2)
        fin = bool(b0 & 0x80)
        if b0 & 0x70:
            raise WSError("unsupported RSV bits")
        opcode = b0 & 0x0F
        masked = bool(b1 & 0x80)
        if masked:
            raise WSError("server frame must not be masked")
        ln = b1 & 0x7F
        if ln == 126:
            ln = struct.unpack("!H", self._read_exact(2))[0]
        elif ln == 127:
            ln = struct.unpack("!Q", self._read_exact(8))[0]
        payload = self._read_exact(ln) if ln else b""
        if opcode >= OP_CLOSE and (not fin or ln > 125):
            raise WSError("invalid control frame")
        return fin, opcode, payload

    def _send_frame(self, opcode, payload=b""):
        header = bytearray()
        header.append(0x80 | opcode)
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < (1 << 16):
            header.append(0x80 | 126)
            header += struct.pack("!H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack("!Q", n)
        mask = os.urandom(4)
        header += mask
        masked = bytes(c ^ mask[i % 4] for i, c in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    # ---------------------------------------------------------------- public
    def send_text(self, text: str):
        self._send_frame(OP_TEXT, text.encode())

    def recv(self):
        """Return (kind, payload_bytes). kind is 'text' | 'binary' | 'close'.

        Control frames are handled internally. Payload bytes are returned unmodified
        so the caller can persist them verbatim.
        """
        chunks = []
        first_op = None
        while True:
            fin, op, payload = self._read_frame()
            if op == OP_PING:
                self._send_frame(OP_PONG, payload)
                continue
            if op == OP_PONG:
                continue
            if op == OP_CLOSE:
                code = struct.unpack("!H", payload[:2])[0] if len(payload) >= 2 else None
                return "close", payload[2:] if payload else b"", code
            if op in (OP_TEXT, OP_BIN):
                first_op = op
                chunks = [payload]
            elif op == OP_CONT:
                chunks.append(payload)
            if fin:
                return ("text" if first_op == OP_TEXT else "binary"), b"".join(chunks), None

    def close(self):
        try:
            self._send_frame(OP_CLOSE, struct.pack("!H", 1000))
        except Exception:  # noqa: BLE001
            pass
        try:
            self.sock.close()
        except Exception:  # noqa: BLE001
            pass
