import os
import json
import time
import base64
import struct
import hashlib
import threading
from urllib.parse import parse_qs, urlparse
from http.server import BaseHTTPRequestHandler

from core.db import load_db, save_db
from core import session as sess
from core import push
from core.templates import get_http_template
from core.router import dispatch, registered_count
from core.pomelo_proto import (
    PKG_HANDSHAKE,
    PKG_HANDSHAKE_ACK,
    PKG_HEARTBEAT,
    PKG_DATA,
    MSG_REQUEST,
    MSG_RESPONSE,
    encode_package,
    decode_packages,
    decode_message,
    encode_message,
)

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
HANDSHAKE_RES = {
    "code": 200,
    "sys": {
        "heartbeat": 30,
        "dict": {},
        "protos": {"version": 0, "server": {}, "client": {}},
    },
}


class GatewayConfig:
    public_host = "127.0.0.1"
    http_port = 20003
    gate_port = 20100
    traffic_logger = None
    active_ws = 0
    ws_lock = threading.Lock()


def _recv_exact(conn, n: int):
    buf = bytearray()
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


def _send_ws_frame(conn, opcode: int, payload: bytes):
    header = bytearray([0x80 | (opcode & 0x0F)])
    length = len(payload)
    if length < 126:
        header.append(length)
    elif length < 65536:
        header.append(126)
        header.extend(struct.pack(">H", length))
    else:
        header.append(127)
        header.extend(struct.pack(">Q", length))
    conn.sendall(bytes(header) + payload)


class GatewayHTTPHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        pass

    def _send_json(self, obj, status=200):
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(raw)

    def _send_html(self, html_str: str, status=200):
        raw = html_str.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(raw)

    def _read_body_params(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8", errors="replace") if length > 0 else ""
        if raw.startswith("{"):
            try:
                return json.loads(raw)
            except Exception:
                pass
        parsed = parse_qs(raw)
        return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}

    def _log(self, kind, path, req, res):
        if GatewayConfig.traffic_logger:
            GatewayConfig.traffic_logger(kind, path, req, res)

    def _handle_websocket_upgrade(self):
        ws_key = self.headers.get("Sec-WebSocket-Key")
        if not ws_key:
            self._send_json({"code": 400, "msg": "Missing Sec-WebSocket-Key"}, status=400)
            return
        accept = base64.b64encode(hashlib.sha1((ws_key + WS_GUID).encode("utf-8")).digest()).decode("ascii")
        resp = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
        )
        self.wfile.write(resp.encode("ascii"))
        self.wfile.flush()
        self.close_connection = True

        conn = self.connection
        conn.settimeout(None)
        session = {}
        send_lock = threading.Lock()

        def _sender(frame_bytes: bytes):
            with send_lock:
                _send_ws_frame(conn, 0x02, frame_bytes)

        session["_sender"] = _sender
        with GatewayConfig.ws_lock:
            GatewayConfig.active_ws += 1

        try:
            while True:
                h = _recv_exact(conn, 2)
                if not h:
                    break
                b1, b2 = h[0], h[1]
                opcode = b1 & 0x0F
                masked = (b2 & 0x80) != 0
                plen = b2 & 0x7F
                if plen == 126:
                    ext = _recv_exact(conn, 2)
                    if not ext:
                        break
                    plen = struct.unpack(">H", ext)[0]
                elif plen == 127:
                    ext = _recv_exact(conn, 8)
                    if not ext:
                        break
                    plen = struct.unpack(">Q", ext)[0]

                mask_key = _recv_exact(conn, 4) if masked else None
                if masked and not mask_key:
                    break
                payload = _recv_exact(conn, plen) if plen > 0 else b""
                if plen > 0 and payload is None:
                    break
                if masked and payload:
                    payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

                if opcode == 0x08:
                    with send_lock:
                        _send_ws_frame(conn, 0x08, b"")
                    break
                if opcode == 0x09:
                    with send_lock:
                        _send_ws_frame(conn, 0x0A, payload)
                    continue
                if opcode not in (0x01, 0x02):
                    continue

                for pkg_type, body in decode_packages(payload):
                    if pkg_type == PKG_HANDSHAKE:
                        with send_lock:
                            _send_ws_frame(conn, 0x02, encode_package(PKG_HANDSHAKE, json.dumps(HANDSHAKE_RES).encode("utf-8")))
                    elif pkg_type == PKG_HANDSHAKE_ACK:
                        pass
                    elif pkg_type == PKG_HEARTBEAT:
                        with send_lock:
                            _send_ws_frame(conn, 0x02, encode_package(PKG_HEARTBEAT, b""))
                    elif pkg_type == PKG_DATA:
                        msg = decode_message(body)
                        route_name = msg["route"]
                        req = msg["body"] if isinstance(msg["body"], dict) else {}
                        res = dispatch(route_name, req, session)
                        self._log("WS_SINGLE", route_name, req, res)
                        if msg["type"] == MSG_REQUEST:
                            resp_bytes = encode_message(msg["id"], MSG_RESPONSE, route_name, res)
                            with send_lock:
                                _send_ws_frame(conn, 0x02, encode_package(PKG_DATA, resp_bytes))
        except Exception:
            pass
        finally:
            if session.get("playerId"):
                push.unregister(session["playerId"], _sender)
            with GatewayConfig.ws_lock:
                GatewayConfig.active_ws = max(0, GatewayConfig.active_ws - 1)

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Connection", "close")
        self.end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Connection", "close")
        self.end_headers()

    def do_GET(self):
        if self.headers.get("Upgrade", "").lower() == "websocket":
            self._handle_websocket_upgrade()
            return

        parsed = urlparse(self.path)
        if parsed.path in ("/", "/status"):
            db = load_db()
            supa_on = bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_KEY"))
            if parsed.path == "/status":
                self._send_json({
                    "status": "online",
                    "port": GatewayConfig.http_port,
                    "gatePort": GatewayConfig.gate_port,
                    "onlineWs": GatewayConfig.active_ws,
                    "users": len(db.get("users", {})),
                    "players": len(db.get("players", {})),
                    "guilds": len(db.get("guilds", {})),
                    "registeredRoutes": registered_count(),
                    "supabase": supa_on,
                    "serverTime": int(time.time() * 1000),
                })
                return
            html = (
                "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Naruto Odysses Server</title></head>"
                "<body style='font-family:sans-serif;background:#161822;color:#eee;padding:28px;'>"
                "<h1>Naruto Odysses Private Server</h1>"
                f"<p><b>Status:</b> <span style='color:#4caf50'>ONLINE</span></p>"
                f"<p><b>HTTP / WS Port:</b> {GatewayConfig.http_port} (Gate WS: {GatewayConfig.gate_port})</p>"
                f"<p><b>Registered Users:</b> {len(db.get('users', {}))} | <b>Players:</b> {len(db.get('players', {}))}</p>"
                f"<p><b>Registered Routes:</b> {registered_count()} explicit + 39 module prefixes</p>"
                f"<p><b>Supabase Cloud Sync:</b> {'ENABLED' if supa_on else 'LOCAL ONLY'}</p>"
                "</body></html>"
            )
            self._send_html(html)
            return

        if parsed.path == "/user/clientConfig":
            res = get_http_template("/user/clientConfig", {
                "inReviewPackageInfos": [],
                "runScriptInfo": {
                    "script": "buildExt.isHideStarSign = false;buildExt.isHideStarSignMap = false;"
                },
            })
            self._log("HTTP_GET", parsed.path, parsed.query, res)
            self._send_json(res)
            return

        if parsed.path == "/notice.json":
            res = get_http_template("/notice.json", [])
            self._log("HTTP_GET", parsed.path, parsed.query, res)
            self._send_json(res)
            return

        if parsed.path == "/user/languageFiles":
            res = []
            self._log("HTTP_GET", parsed.path, parsed.query, res)
            self._send_json(res)
            return

        self._send_json({"code": 200})

    def do_POST(self):
        parsed = urlparse(self.path)
        params = self._read_body_params()
        db = load_db()

        if parsed.path == "/sdk/verifyToken":
            name = params.get("userId") or "local_user"
            res = {"code": 200, "userName": str(name), "accountId": str(name)}
            self._log("HTTP_POST", parsed.path, params, res)
            self._send_json(res)
            return

        if parsed.path in ("/user/login", "/user/register"):
            name = params.get("name") or params.get("userName") or "player1"
            password = params.get("password", "")
            server_id = int(params.get("serverId") or 1)
            res, user = sess.login(db, name, password, server_id)
            if user is not None:
                res["userName"] = user["name"]
                save_db(db)
            self._log("HTTP_POST", parsed.path, params, res)
            self._send_json(res)
            return

        if parsed.path == "/user/serverInfo":
            uname = params.get("userName", "player1")
            user = db["users"].get(uname)
            plist = []
            if user:
                for p in db["players"].values():
                    if p.get("userId") == user["uid"]:
                        plist.append({
                            "serverId": p.get("serverId", 1),
                            "oldServerId": p.get("oldServerId", 1),
                            "playerId": p["id"],
                            "name": p["name"],
                        })
            res = {
                "code": 200,
                "players": plist,
                "serverList": [
                    {
                        "serverId": 1,
                        "oldServerId": 1,
                        "name": "S1 Local Private",
                        "gateHost": GatewayConfig.public_host,
                        "gatePort": GatewayConfig.gate_port,
                    }
                ],
            }
            self._log("HTTP_POST", parsed.path, params, res)
            self._send_json(res)
            return

        res = {"code": 200}
        self._log("HTTP_POST", parsed.path, params, res)
        self._send_json(res)
