"""B15a — a minimal RFC 6455 WebSocket client on the standard library.

Hand-rolled because no dependency may be added to this project and `logsSubscribe` is websocket
only. This is deliberately the smallest client that is correct for the one job it has: connect,
send text, receive text, answer pings, close cleanly, and fail visibly.

What it does NOT do, on purpose: no extensions, no compression, no continuation across a
fragmented control frame, no subprotocol negotiation. Each of those is a place to be subtly wrong,
and none is needed to read a JSON-RPC subscription.

Two properties matter more than features here:

- **Frames are never silently dropped.** Anything unexpected raises. A transport that swallows a
  malformed frame turns a provider fault into a quiet gap in the evidence.
- **The credential never leaves the environment.** The URL is used to connect and is then reduced
  to scheme and host for every receipt; the path and query, which carry the API key, are not
  retained on the object.
"""
import base64
import hashlib
import json
import os
import secrets
import socket
import ssl
import struct
from urllib.parse import urlsplit

SCHEMA_VERSION = "1.0.0"

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OPCODE_CONTINUATION = 0x0
OPCODE_TEXT = 0x1
OPCODE_BINARY = 0x2
OPCODE_CLOSE = 0x8
OPCODE_PING = 0x9
OPCODE_PONG = 0xA


class WebSocketRefused(RuntimeError):
    """The transport could not do what it was asked, and says so rather than continuing."""


def endpoint_receipt(url):
    """Scheme and host only. The path and query carry the credential and never appear anywhere."""
    parts = urlsplit(url)
    if not parts.scheme or not parts.hostname:
        raise WebSocketRefused("endpoint has no scheme or host")
    return f"{parts.scheme}://{parts.hostname}"


class WebSocket:
    """One connection. Not reusable after close: a reconnect is a new object and a new session."""

    def __init__(self, url, timeout=30.0):
        parts = urlsplit(url)
        if parts.scheme not in ("ws", "wss"):
            raise WebSocketRefused(
                f"{parts.scheme!r} is not a websocket scheme; refusing rather than guessing")
        self.receipt = endpoint_receipt(url)
        self._host = parts.hostname
        self._port = parts.port or (443 if parts.scheme == "wss" else 80)
        self._secure = parts.scheme == "wss"
        # Kept only for the duration of the handshake. Not stored on the instance beyond it.
        self._resource = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        self.timeout = timeout
        self.sock = None
        self._buffer = b""
        self.closed = False
        self.close_reason = None

    # -- connection -----------------------------------------------------------------------

    def connect(self):
        raw = socket.create_connection((self._host, self._port), timeout=self.timeout)
        if self._secure:
            context = ssl.create_default_context()
            raw = context.wrap_socket(raw, server_hostname=self._host)
        self.sock = raw
        key = base64.b64encode(secrets.token_bytes(16)).decode()
        request = (
            f"GET {self._resource} HTTP/1.1\r\n"
            f"Host: {self._host}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        self.sock.sendall(request.encode())
        # The resource carries the credential; drop it the moment the handshake is written so it
        # cannot be reached from the object afterwards, by a traceback, a repr or a logger.
        self._resource = None
        header = self._read_until(b"\r\n\r\n")
        self._verify_handshake(header, key)
        return self

    def _verify_handshake(self, header, key):
        text = header.decode(errors="replace")
        status = text.split("\r\n", 1)[0]
        if "101" not in status:
            raise WebSocketRefused(f"upgrade refused: {status}")
        expected = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        accept = None
        for line in text.split("\r\n")[1:]:
            name, _, value = line.partition(":")
            if name.strip().lower() == "sec-websocket-accept":
                accept = value.strip()
        if accept != expected:
            # Not cosmetic: a wrong accept means whatever answered is not speaking this protocol,
            # and reading frames from it would be reading noise as evidence.
            raise WebSocketRefused("Sec-WebSocket-Accept did not match; peer is not a websocket")

    def _read_until(self, marker):
        while marker not in self._buffer:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise WebSocketRefused("connection closed during handshake")
            self._buffer += chunk
        header, _, rest = self._buffer.partition(marker)
        self._buffer = rest
        return header

    def _read_exactly(self, count):
        while len(self._buffer) < count:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise WebSocketRefused("connection closed mid-frame")
            self._buffer += chunk
        out, self._buffer = self._buffer[:count], self._buffer[count:]
        return out

    # -- frames ---------------------------------------------------------------------------

    def _send_frame(self, opcode, payload=b""):
        if self.closed:
            raise WebSocketRefused("send on a closed socket")
        header = bytearray()
        header.append(0x80 | opcode)
        length = len(payload)
        # A client MUST mask. An unmasked client frame is a protocol violation and servers close on
        # it, which would look like an unexplained disconnect in the evidence.
        if length < 126:
            header.append(0x80 | length)
        elif length < (1 << 16):
            header.append(0x80 | 126)
            header += struct.pack(">H", length)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", length)
        mask = secrets.token_bytes(4)
        header += mask
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def send_text(self, text):
        self._send_frame(OPCODE_TEXT, text.encode())

    def send_json(self, document):
        self.send_text(json.dumps(document, separators=(",", ":")))

    def ping(self, payload=b"hb"):
        self._send_frame(OPCODE_PING, payload)

    def recv(self):
        """One application message, or None when the peer closed.

        Control frames are answered here and never returned: a caller that had to distinguish a
        pong from a notification would eventually forget to.
        """
        while True:
            first, second = self._read_exactly(2)
            final = bool(first & 0x80)
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._read_exactly(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._read_exactly(8))[0]
            if masked:
                # Servers must not mask. If one does, the framing is not what we think it is.
                raise WebSocketRefused("server sent a masked frame, which RFC 6455 forbids")
            payload = self._read_exactly(length)

            if opcode == OPCODE_PING:
                self._send_frame(OPCODE_PONG, payload)
                continue
            if opcode == OPCODE_PONG:
                continue
            if opcode == OPCODE_CLOSE:
                code = struct.unpack(">H", payload[:2])[0] if len(payload) >= 2 else None
                self.close_reason = f"peer close code={code}"
                self.closed = True
                return None
            if opcode == OPCODE_BINARY:
                raise WebSocketRefused("binary frame on a JSON subscription; refusing to guess")
            if opcode not in (OPCODE_TEXT, OPCODE_CONTINUATION):
                raise WebSocketRefused(f"unknown opcode {opcode}")

            data = payload
            while not final:
                first, second = self._read_exactly(2)
                final = bool(first & 0x80)
                continuation = first & 0x0F
                if continuation not in (OPCODE_CONTINUATION,):
                    raise WebSocketRefused(
                        f"expected a continuation frame, got opcode {continuation}")
                length = second & 0x7F
                if length == 126:
                    length = struct.unpack(">H", self._read_exactly(2))[0]
                elif length == 127:
                    length = struct.unpack(">Q", self._read_exactly(8))[0]
                data += self._read_exactly(length)
            return data.decode(errors="replace")

    def close(self, code=1000):
        if self.closed or self.sock is None:
            return
        try:
            self._send_frame(OPCODE_CLOSE, struct.pack(">H", code))
        except OSError:
            pass
        finally:
            self.closed = True
            try:
                self.sock.close()
            except OSError:
                pass


def websocket_url_from_env(variable="SOLANA_RPC_URL"):
    """The subscription endpoint, derived from the HTTP endpoint in the environment.

    Environment only. Never an argument, never read from a file this project wrote, and never
    written to one.
    """
    url = os.environ.get(variable)
    if not url:
        raise WebSocketRefused(
            f"{variable} is not set. Credentials are environment-only and this process never "
            "reads one from a file it wrote")
    parts = urlsplit(url)
    scheme = "wss" if parts.scheme == "https" else "ws"
    return f"{scheme}://{parts.netloc}{parts.path}" + (f"?{parts.query}" if parts.query else "")
