import os
import json
import asyncio
import argparse
import threading
from datetime import datetime
from http.server import ThreadingHTTPServer

import websockets

from core.db import load_db_from_supabase, start_db_sync_loop, flush_to_supabase
from core import push
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
from core.router import dispatch, registered_count
from core.templates import get_templates
from http_api.gateway import GatewayHTTPHandler, GatewayConfig
from handlers.entry import EntryConfig
import handlers  # noqa: F401  (auto-registers all handler modules)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRAFFIC_LOG = os.path.join(BASE_DIR, "server_traffic.jsonl")

DEFAULT_HTTP_PORT = int(os.environ.get("PORT", "20003"))
GATE_PORT = 20100
CONNECTOR_PORT = 3050

HANDSHAKE_RES = {
    "code": 200,
    "sys": {
        "heartbeat": 30,
        "dict": {},
        "protos": {"version": 0, "server": {}, "client": {}},
    },
}


def log_traffic(kind: str, route_name: str, req, res):
    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "kind": kind,
        "route": route_name,
        "req": req,
        "res": res,
    }
    if route_name != "logic.playerHandler.incOnlineTime":
        print(f"[{entry['ts']}] [{kind}] {route_name} | req={json.dumps(req, ensure_ascii=False)[:120]}")
    try:
        with open(TRAFFIC_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


async def handle_pomelo_ws(ws, role: str):
    session = {}
    loop = asyncio.get_running_loop()

    def _sender(frame_bytes: bytes):
        asyncio.run_coroutine_threadsafe(ws.send(frame_bytes), loop)

    session["_sender"] = _sender
    try:
        async for raw in ws:
            if isinstance(raw, str):
                continue
            for pkg_type, body in decode_packages(raw):
                if pkg_type == PKG_HANDSHAKE:
                    await ws.send(encode_package(PKG_HANDSHAKE, json.dumps(HANDSHAKE_RES).encode("utf-8")))
                elif pkg_type == PKG_HANDSHAKE_ACK:
                    pass
                elif pkg_type == PKG_HEARTBEAT:
                    await ws.send(encode_package(PKG_HEARTBEAT, b""))
                elif pkg_type == PKG_DATA:
                    msg = decode_message(body)
                    route_name = msg["route"]
                    req = msg["body"] if isinstance(msg["body"], dict) else {}
                    res = dispatch(route_name, req, session)
                    log_traffic(f"WS_{role}", route_name, req, res)
                    if msg["type"] == MSG_REQUEST:
                        resp_bytes = encode_message(msg["id"], MSG_RESPONSE, route_name, res)
                        await ws.send(encode_package(PKG_DATA, resp_bytes))
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        if session.get("playerId"):
            push.unregister(session["playerId"], _sender)


async def run_ws_servers(public_host: str):
    push.set_loop(asyncio.get_running_loop())
    await websockets.serve(lambda ws: handle_pomelo_ws(ws, "GATE"), "0.0.0.0", GATE_PORT)
    await websockets.serve(lambda ws: handle_pomelo_ws(ws, "CONN"), "0.0.0.0", CONNECTOR_PORT)
    print(f"[+] Pomelo Gate WS      : ws://{public_host}:{GATE_PORT}")
    print(f"[+] Pomelo Connector WS : ws://{public_host}:{CONNECTOR_PORT}")
    await asyncio.Future()


def main():
    render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "")
    is_render = bool(os.environ.get("RENDER") or render_host)

    parser = argparse.ArgumentParser(description="Naruto Odysses Modular Private Server")
    parser.add_argument("--host", default=render_host or os.environ.get("PUBLIC_HOST", "127.0.0.1"), help="Public host/IP returned to client")
    parser.add_argument("--port", type=int, default=DEFAULT_HTTP_PORT, help="Primary HTTP+WS port (Render uses $PORT)")
    parser.add_argument("--ws-port", type=int, default=int(os.environ.get("PUBLIC_WS_PORT", "0")), help="Public WS port returned by queryEntry")
    parser.add_argument("--single-port", action="store_true", default=is_render, help="Serve HTTP and WS only on primary --port (Render mode)")
    args = parser.parse_args()

    load_db_from_supabase()
    start_db_sync_loop(10.0)

    if args.single_port:
        public_ws_port = args.ws_port or (443 if render_host else args.port)
        GatewayConfig.gate_port = public_ws_port
        EntryConfig.connector_port = public_ws_port
    else:
        GatewayConfig.gate_port = GATE_PORT
        EntryConfig.connector_port = CONNECTOR_PORT

    GatewayConfig.public_host = args.host
    GatewayConfig.http_port = args.port
    GatewayConfig.traffic_logger = log_traffic
    EntryConfig.public_host = args.host

    http_srv = ThreadingHTTPServer(("0.0.0.0", args.port), GatewayHTTPHandler)
    tpls = get_templates()
    print(f"[+] Registered routes   : {registered_count()} explicit + 39 module prefixes")
    print(f"[+] Loaded templates    : {len(tpls['http'])} HTTP, {len(tpls['ws'])} WS")
    print(f"[+] HTTP + WS Primary   : http://{args.host}:{args.port} (single_port={args.single_port})")
    print(f"[+] Traffic log         : {TRAFFIC_LOG}")

    try:
        if args.single_port:
            http_srv.serve_forever()
        else:
            t = threading.Thread(target=http_srv.serve_forever, daemon=True)
            t.start()
            asyncio.run(run_ws_servers(args.host))
    except KeyboardInterrupt:
        flush_to_supabase()


if __name__ == "__main__":
    main()
