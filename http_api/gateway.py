import os
import re
import copy
import json
import time
import base64
import struct
import hashlib
import threading
import urllib.request
from urllib.parse import parse_qs, urlparse
from http.server import BaseHTTPRequestHandler

from core.db import load_db, save_db, flush_to_supabase, push_mail, next_mail_id
from core import session as sess
from core import push, gm_service, rewards
from core.templates import get_http_template
from core.router import dispatch, registered_count
from http_api.gm_web import render_gm_html
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


_OFFICIAL_HTTP_BASE = "http://hykp2-yiwei.miaomuxian.cn:20003"
_OFFICIAL_STATIC_BASE = "http://hykp2-yiwei.miaomuxian.cn:20001"
_OFFICIAL_CACHE = {}
_OFFICIAL_CACHE_LOCK = threading.Lock()


def _strip_force_update(data):
    if isinstance(data, dict):
        data = dict(data)
        data.pop("forceUpdate", None)
    return data


def _strip_language_prefix(data):
    if isinstance(data, list):
        return [
            p[9:] if isinstance(p, str) and p.startswith("/language/") else p
            for p in data
        ]
    return data


def _fetch_official_cached(cache_key: str, url: str, fallback, ttl: int = 300, transform=None):
    now = time.time()
    with _OFFICIAL_CACHE_LOCK:
        cached = _OFFICIAL_CACHE.get(cache_key)
        if cached and now < cached[0]:
            return copy.deepcopy(cached[1])
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        if transform is not None:
            data = transform(data)
        with _OFFICIAL_CACHE_LOCK:
            _OFFICIAL_CACHE[cache_key] = (now + ttl, data)
        return copy.deepcopy(data)
    except Exception:
        with _OFFICIAL_CACHE_LOCK:
            if cache_key in _OFFICIAL_CACHE:
                return copy.deepcopy(_OFFICIAL_CACHE[cache_key][1])
        return copy.deepcopy(fallback)


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
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-GM-Key")
        self.send_header("Connection", "close")
        self.end_headers()

    def _check_gm_auth(self, parsed) -> bool:
        expected = os.environ.get("GM_KEY", "").strip()
        if not expected:
            return True
        qs = parse_qs(parsed.query)
        provided = (self.headers.get("X-GM-Key") or (qs.get("key") or [""])[0]).strip()
        if provided == expected:
            return True
        self._send_json({"code": 401, "msg": "Sai hoặc thiếu GM Key (X-GM-Key)"}, status=401)
        return False

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
                "<p><a href='/gm' style='color:#ffb020;font-weight:bold;text-decoration:none;'>"
                "Mở Bảng Điều Khiển GM (/gm) &rarr;</a></p>"
                "</body></html>"
            )
            self._send_html(html)
            return

        if parsed.path in ("/gm", "/gm/"):
            gm_key_required = bool(os.environ.get("GM_KEY", "").strip())
            self._send_html(render_gm_html(gm_key_required))
            return

        if parsed.path == "/gm/api/players":
            if not self._check_gm_auth(parsed):
                return
            db = load_db()
            self._send_json({"code": 200, "players": gm_service.list_players(db)})
            return

        if parsed.path == "/gm/api/catalog":
            if not self._check_gm_auth(parsed):
                return
            qs = parse_qs(parsed.query)
            q = (qs.get("q") or [""])[0]
            cat = (qs.get("type") or ["all"])[0]
            try:
                limit = int((qs.get("limit") or ["80"])[0])
            except (TypeError, ValueError):
                limit = 80
            res = gm_service.search_catalog(query=q, category=cat, limit=limit)
            self._send_json({"code": 200, **res})
            return

        if parsed.path == "/user/clientConfig":
            qs = parse_qs(parsed.query)
            platform = re.sub(r"[^a-zA-Z0-9_-]", "", (qs.get("platform") or ["android"])[0]) or "android"
            fallback = get_http_template("/user/clientConfig", {
                "inReviewPackageInfos": [],
                "runScriptInfo": {
                    "script": "buildExt.isHideStarSign = false;buildExt.isHideStarSignMap = false;"
                },
            })
            res = _fetch_official_cached(
                f"clientConfig:{platform}",
                f"{_OFFICIAL_HTTP_BASE}/user/clientConfig?platform={platform}",
                fallback,
                ttl=300,
                transform=_strip_force_update,
            )
            self._log("HTTP_GET", parsed.path, parsed.query, res)
            self._send_json(res)
            return

        if parsed.path == "/notice.json":
            fallback = get_http_template("/notice.json", [])
            res = _fetch_official_cached(
                "notice.json",
                f"{_OFFICIAL_STATIC_BASE}/notice.json",
                fallback,
                ttl=300,
            )
            self._log("HTTP_GET", parsed.path, parsed.query, res)
            self._send_json(res)
            return

        if parsed.path == "/user/languageFiles":
            qs = parse_qs(parsed.query)
            lang = re.sub(r"[^a-zA-Z0-9_-]", "", (qs.get("language") or ["vi"])[0]) or "vi"
            res = _fetch_official_cached(
                f"languageFiles:{lang}",
                f"{_OFFICIAL_HTTP_BASE}/user/languageFiles?language={lang}",
                [],
                ttl=300,
                transform=_strip_language_prefix,
            )
            self._log("HTTP_GET", parsed.path, parsed.query, f"{len(res) if isinstance(res, list) else 0} files")
            self._send_json(res)
            return

        self._send_json({"code": 200})

    def _handle_gm_action(self, db: dict, params: dict):
        action = str(params.get("action") or "").strip()
        if action == "flush_db":
            ok = flush_to_supabase()
            return 200, {
                "code": 200,
                "ok": True,
                "message": "Đã lưu & đồng bộ lên Supabase!" if ok else "Đã lưu DB cục bộ (chưa cấu hình Supabase hoặc lỗi mạng).",
            }

        player = gm_service.resolve_player(db, params.get("target"))
        if player is None:
            return 404, {"code": 404, "msg": "Không tìm thấy nhân vật (hãy đăng nhập và tạo nhân vật trước)."}

        try:
            if action == "preset":
                via_mail = bool(params.get("viaMail"))
                msg, info, _ = gm_service.apply_preset(db, player, params.get("preset"), via_mail=via_mail)
                return 200, {
                    "code": 200,
                    "ok": True,
                    "message": msg,
                    "pushed": info.get("pushed", False),
                    "player": gm_service.player_brief(db, player),
                }

            if action == "add_items":
                via_mail = bool(params.get("viaMail"))
                title = str(params.get("title") or "GM 福利礼包")
                body = str(params.get("body") or "来自 GM 的专属福利，请查收！")
                info, _ = gm_service.add_items(
                    db, player, params.get("items") or [], via_mail=via_mail, title=title, body=body
                )
                return 200, {
                    "code": 200,
                    "ok": True,
                    "message": f"Đã gửi {info.get('itemTypes', 0)} loại vật phẩm cho {player['name']}",
                    "pushed": info.get("pushed", False),
                    "player": gm_service.player_brief(db, player),
                }

            if action == "add_role":
                rid = params.get("kindId") or params.get("classId")
                if not rid:
                    raise ValueError("Thiếu kindId hoặc classId tướng")
                res = gm_service.add_role(
                    db,
                    player,
                    int(rid),
                    level=int(params.get("level") or player.get("level") or 1),
                    star=int(params.get("star") or 5),
                )
                return 200, {
                    "code": 200,
                    "ok": True,
                    "message": f"Đã thêm tướng {res['roleName']} ({res['star']}★) vào đội của {player['name']}",
                    "pushed": res.get("pushed", False),
                    "player": gm_service.player_brief(db, player),
                }

            if action == "set_stats":
                info, _ = gm_service.set_stats(
                    db,
                    player,
                    coin=params.get("coin"),
                    gem=params.get("gem"),
                    action_point=params.get("actionPoint"),
                    skill_point=params.get("skillPoint"),
                    level=params.get("level"),
                    vip_level=params.get("vipLevel"),
                    mode=params.get("mode") or "add",
                )
                return 200, {
                    "code": 200,
                    "ok": True,
                    "message": f"Đã cập nhật chỉ số cho {player['name']}",
                    "pushed": info.get("pushed", False),
                    "player": info.get("player"),
                }

            if action == "send_mail":
                title = str(params.get("title") or "Quà tặng từ GM")
                body = str(params.get("body") or "")
                drop_desc = str(params.get("dropDesc") or "").strip()
                items = rewards.parse_drop_desc(drop_desc) if drop_desc else []
                if items:
                    info, _ = gm_service.add_items(db, player, items, via_mail=True, title=title, body=body)
                    pushed = info.get("pushed", False)
                else:
                    mail = {
                        "_id": next_mail_id(db),
                        "isSys": True,
                        "status": 1,
                        "type": 1,
                        "senderId": 9999999999,
                        "senderName": "GM 管理员",
                        "title": title,
                        "body": body,
                        "ctime": int(time.time() * 1000),
                        "expireTime": int(time.time() * 1000) + 604800000,
                        "dropList": [],
                        "isReceived": False,
                    }
                    push_mail(db, player["id"], mail)
                    save_db(db)
                    pushed = push.new_mail(player["id"], mail) if push.is_online(player["id"]) else False
                return 200, {
                    "code": 200,
                    "ok": True,
                    "message": f"Đã gửi thư hệ thống cho {player['name']} ({len(items)} loại vật phẩm)",
                    "pushed": pushed,
                    "player": gm_service.player_brief(db, player),
                }

            return 400, {"code": 400, "msg": f"Action GM không hợp lệ: {action}"}
        except ValueError as e:
            return 400, {"code": 400, "msg": str(e)}

    def do_POST(self):
        parsed = urlparse(self.path)
        params = self._read_body_params()
        db = load_db()

        if parsed.path == "/gm/api/action":
            if not self._check_gm_auth(parsed):
                return
            status_code, res = self._handle_gm_action(db, params if isinstance(params, dict) else {})
            self._log("HTTP_GM", parsed.path, params, res)
            self._send_json(res, status=status_code)
            return

        if parsed.path == "/sdk/verifyToken":
            name = params.get("userId") or "local_user"
            res = {"code": 200, "userName": str(name), "accountId": str(name)}
            self._log("HTTP_POST", parsed.path, params, res)
            self._send_json(res)
            return

        if parsed.path == "/user/register":
            name = params.get("name") or params.get("userName") or ""
            password = params.get("password", "")
            server_id = int(params.get("serverId") or 1)
            account_id = params.get("accountId", "")
            res, user = sess.register(db, name, password, server_id, account_id)
            if user is not None:
                res["userName"] = user["name"]
                save_db(db)
            self._log("HTTP_POST", parsed.path, params, res)
            self._send_json(res)
            return

        if parsed.path == "/user/login":
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
                        "name": "S1 Ninja Odyssey",
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
