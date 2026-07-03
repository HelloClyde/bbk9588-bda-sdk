"""Small WebSocket helpers for the BBK 9588 frontend."""

from __future__ import annotations

import base64
import hashlib


WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def websocket_accept_key(client_key: str) -> str:
    digest = hashlib.sha1((client_key + WS_GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def encode_ws_frame(opcode: int, payload: bytes, mask: bytes | None = None) -> bytes:
    masked = mask is not None
    if mask is not None and len(mask) != 4:
        raise ValueError("WebSocket mask must be exactly 4 bytes")

    header = bytearray([0x80 | (opcode & 0x0F)])
    length = len(payload)
    mask_bit = 0x80 if masked else 0
    if length < 126:
        header.append(mask_bit | length)
    elif length < 65536:
        header.extend((mask_bit | 126, (length >> 8) & 0xFF, length & 0xFF))
    else:
        header.append(mask_bit | 127)
        header.extend(length.to_bytes(8, "big"))

    if not masked:
        return bytes(header) + payload
    masked_payload = bytes(value ^ mask[idx % 4] for idx, value in enumerate(payload))
    return bytes(header) + mask + masked_payload


def _recv_exact(connection, size: int) -> bytes | None:
    out = bytearray()
    while len(out) < size:
        chunk = connection.recv(size - len(out))
        if not chunk:
            return None
        out.extend(chunk)
    return bytes(out)


def read_ws_frame(connection) -> tuple[int, bytes] | None:
    first = _recv_exact(connection, 2)
    if first is None:
        return None
    opcode = first[0] & 0x0F
    masked = bool(first[1] & 0x80)
    length = first[1] & 0x7F
    if length == 126:
        raw_length = _recv_exact(connection, 2)
        if raw_length is None:
            return None
        length = int.from_bytes(raw_length, "big")
    elif length == 127:
        raw_length = _recv_exact(connection, 8)
        if raw_length is None:
            return None
        length = int.from_bytes(raw_length, "big")

    mask = b""
    if masked:
        mask = _recv_exact(connection, 4)
        if mask is None:
            return None

    payload = _recv_exact(connection, length)
    if payload is None:
        return None
    if masked:
        payload = bytes(value ^ mask[idx % 4] for idx, value in enumerate(payload))
    return opcode, payload


def recv_ws_text(connection) -> str | None:
    frame = read_ws_frame(connection)
    if frame is None:
        return None
    opcode, payload = frame
    if opcode == 0x8:
        return None
    if opcode != 0x1:
        return ""
    return payload.decode("utf-8", errors="replace")
