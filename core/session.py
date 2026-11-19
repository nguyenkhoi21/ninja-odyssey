"""Token auth, player ownership, and per-connection session state."""
import time
import hashlib
import secrets

from core.db import load_db, save_db, ensure_player_fields


def _now_ms():
    return int(time.time() * 1000)


def issue_token(db, uid, account_id=""):
    """Create (or reuse) a login token bound to a uid."""
    with_tokens = db.setdefault("tokens", {})
    for tok, info in list(with_tokens.items()):
        if info.get("uid") == uid and not info.get("consumed"):
            info["atime"] = _now_ms()
            return tok
    token = hashlib.sha256(
        f"{uid}:{_now_ms()}:{secrets.token_hex(16)}".encode("utf-8")
    ).hexdigest()
    with_tokens[token] = {
        "uid": uid,
        "accountId": str(account_id or ""),
        "ctime": _now_ms(),
        "atime": _now_ms(),
    }
    return token


def resolve_token(db, token):
    if not token:
        return None
    info = db.get("tokens", {}).get(token)
    if not info:
        return None
    return info.get("uid")


def revoke_token(db, token):
    db.get("tokens", {}).pop(token, None)


def login(db, name, password="", server_id=1):
    """Login or auto-register. Returns (result_dict, user_dict)."""
    name = (name or "").strip()
    if not name:
        name = "player"
    users = db.setdefault("users", {})
    user = users.get(name)
    if user is None:
        uid = db.get("next_uid", 55924)
        db["next_uid"] = uid + 1
        user = {
            "uid": uid,
            "name": name,
            "password": password or "",
            "serverId": server_id or 1,
            "ctime": _now_ms(),
            "atime": _now_ms(),
        }
        users[name] = user
    if password and user.get("password") and password != user["password"]:
        return {"code": 500, "msg": "密码错误"}, None
    user["atime"] = _now_ms()
    user.setdefault("serverId", server_id or 1)
    token = issue_token(db, user["uid"], user.get("accountId", ""))
    res = {
        "code": 200,
        "token": token,
        "uid": user["uid"],
        "accountId": str(user.get("accountId") or user["uid"]),
        "atime": user["atime"],
        "ctime": user.get("ctime") or user["atime"],
        "loginIp": "127.0.0.1",
    }
    return res, user


def register(db, name, password="", server_id=1, account_id=""):
    """Explicit account registration for built-in loginPanel; returns (result_dict, user_dict)."""
    name = (name or "").strip()
    if not name:
        return {"code": 500, "msg": "账号不能为空"}, None
    users = db.setdefault("users", {})
    if name in users:
        return {"code": 500, "msg": "账号已存在"}, None
    uid = db.get("next_uid", 55924)
    db["next_uid"] = uid + 1
    now = _now_ms()
    user = {
        "uid": uid,
        "name": name,
        "password": password or "",
        "accountId": str(account_id or uid),
        "serverId": server_id or 1,
        "ctime": now,
        "atime": now,
    }
    users[name] = user
    token = issue_token(db, uid, user["accountId"])
    res = {
        "code": 200,
        "token": token,
        "uid": uid,
        "accountId": user["accountId"],
        "atime": now,
        "ctime": now,
        "loginIp": "127.0.0.1",
    }
    return res, user


def bind_uid(session, uid):
    session["uid"] = uid


def players_of_uid(db, uid):
    return [p for p in db.get("players", {}).values() if p.get("userId") == uid]


def owns_player(db, player_id, uid):
    if not player_id:
        return False
    p = db.get("players", {}).get(str(player_id))
    if not p:
        return False
    if uid is None:
        return False
    return p.get("userId") == uid


def current_player(db, session):
    """Return the player bound to this connection, or None."""
    pid = session.get("playerId")
    if not pid:
        return None
    p = db.get("players", {}).get(str(pid))
    if not p:
        return None
    ensure_player_fields(p)
    return p


def require_player(session):
    """Handler helper: (player, error_response)."""
    db = load_db()
    p = current_player(db, session)
    if p is None:
        return None, None, {"code": 500, "msg": "未登录"}
    return db, p, None


def player_summary(p):
    return {
        "_id": p["id"],
        "id": p["id"],
        "name": p.get("name", ""),
        "userId": p.get("userId", 0),
        "serverId": p.get("serverId", 1),
        "oldServerId": p.get("oldServerId", 1),
        "level": p.get("level", 1),
    }


def name_taken(db, name, exclude_pid=None):
    for p in db.get("players", {}).values():
        if p.get("name") == name and p.get("id") != exclude_pid:
            return True
    return False


def save(db=None):
    save_db(db if db is not None else load_db())
