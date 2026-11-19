import json
import struct

PKG_HANDSHAKE = 1
PKG_HANDSHAKE_ACK = 2
PKG_HEARTBEAT = 3
PKG_DATA = 4
PKG_KICK = 5

MSG_REQUEST = 0
MSG_NOTIFY = 1
MSG_RESPONSE = 2
MSG_PUSH = 3


def encode_package(pkg_type: int, body: bytes = b"") -> bytes:
    length = len(body)
    header = bytes([
        pkg_type & 0xFF,
        (length >> 16) & 0xFF,
        (length >> 8) & 0xFF,
        length & 0xFF,
    ])
    return header + body


def decode_packages(buf: bytes):
    offset = 0
    while offset + 4 <= len(buf):
        pkg_type = buf[offset]
        length = (buf[offset + 1] << 16) | (buf[offset + 2] << 8) | buf[offset + 3]
        offset += 4
        body = buf[offset : offset + length]
        offset += length
        yield pkg_type, body


def _decode_varint(buf: bytes, offset: int):
    val = 0
    shift = 0
    while offset < len(buf):
        b = buf[offset]
        offset += 1
        val |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return val, offset


def _encode_varint(val: int) -> bytes:
    out = bytearray()
    while True:
        byte = val & 0x7F
        val >>= 7
        if val:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            break
    return bytes(out)


def decode_message(buf: bytes, id_to_route=None):
    offset = 0
    flag = buf[offset]
    offset += 1
    compress_route = flag & 0x01
    msg_type = (flag >> 1) & 0x07

    msg_id = 0
    if msg_type in (MSG_REQUEST, MSG_RESPONSE):
        msg_id, offset = _decode_varint(buf, offset)

    route = ""
    if msg_type in (MSG_REQUEST, MSG_NOTIFY, MSG_PUSH):
        if compress_route:
            code = struct.unpack_from(">H", buf, offset)[0]
            offset += 2
            route = id_to_route.get(code, str(code)) if id_to_route else str(code)
        else:
            rlen = buf[offset]
            offset += 1
            route = buf[offset : offset + rlen].decode("utf-8", errors="replace")
            offset += rlen

    raw_body = buf[offset:]
    try:
        body = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception:
        body = raw_body
    return {"id": msg_id, "type": msg_type, "route": route, "body": body}


def encode_message(msg_id: int, msg_type: int, route: str, body_obj, route_to_id=None) -> bytes:
    compress_route = 0
    route_bytes = b""
    if msg_type in (MSG_REQUEST, MSG_NOTIFY, MSG_PUSH):
        if route_to_id and route in route_to_id:
            compress_route = 1
            route_bytes = struct.pack(">H", route_to_id[route])
        else:
            rb = route.encode("utf-8")
            route_bytes = bytes([len(rb)]) + rb

    flag = ((msg_type & 0x07) << 1) | (compress_route & 0x01)
    out = bytearray([flag])
    if msg_type in (MSG_REQUEST, MSG_RESPONSE):
        out.extend(_encode_varint(msg_id))
    out.extend(route_bytes)

    if isinstance(body_obj, (bytes, bytearray)):
        out.extend(body_obj)
    else:
        out.extend(json.dumps(body_obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    return bytes(out)
