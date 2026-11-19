import time

from core.router import route
from core.db import (
    load_db,
    save_db,
    make_default_player,
    ensure_player_fields,
    next_mail_id,
)
from core import session as sess
from core import push, activity, tasks
from core.schema import recalc_power


class EntryConfig:
    public_host = "127.0.0.1"
    connector_port = 3050
    max_players = 8


def _now_ms():
    return int(time.time() * 1000)


@route("gate.gateHandler.queryEntry")
def query_entry(req: dict, session: dict):
    uid = req.get("uid")
    if uid is not None:
        session["uid"] = int(uid)
    return {
        "code": 200,
        "host": EntryConfig.public_host,
        "port": EntryConfig.connector_port,
    }


@route("connector.entryHandler.entry")
def connector_entry(req: dict, session: dict):
    db = load_db()
    token = req.get("token")
    uid = sess.resolve_token(db, token) if token else None
    if uid is None and session.get("uid") is None:
        return {"code": 500, "msg": "登录已过期，请重新登录"}
    if uid is not None:
        session["uid"] = uid
    session["token"] = token
    session["serverId"] = int(req.get("serverId") or 1)
    session["oldServerId"] = int(req.get("oldServerId") or session["serverId"])
    return {"code": 200, "serverTime": _now_ms()}


@route("connector.playerHandler.getPlayers")
def get_players(req: dict, session: dict):
    db = load_db()
    uid = session.get("uid")
    if uid is None:
        return {"code": 500, "msg": "未登录"}
    players = [sess.player_summary(p) for p in sess.players_of_uid(db, uid)]
    return {"code": 200, "players": players}


def _starter_mail(db, player):
    try:
        mails = player.setdefault("extra", {}).setdefault("mails", [])
        if mails:
            return
        mails.append({
            "_id": next_mail_id(db),
            "isSys": True,
            "status": 1,
            "type": 1,
            "senderId": 9999999999,
            "senderName": "系统消息",
            "title": "欢迎来到忍界",
            "body": "集结你的忍者小队，开始你的忍道之路！",
            "ctime": _now_ms(),
            "expireTime": _now_ms() + 604800000,
            "dropList": [
                {"entityId": 101, "count": 50000, "extra": 0},
                {"entityId": 102, "count": 500, "extra": 0},
                {"entityId": 20002, "count": 2, "extra": 0},
            ],
            "isReceived": False,
        })
    except Exception:
        pass


def _prepare_player(player):
    """Ensure activities and tasks are populated before sending player snapshot."""
    activity.refresh_activity(player)
    tasks.ensure_main_task(player)
    tasks.ensure_daily_tasks(player)


@route("connector.playerHandler.createPlayer")
def create_player(req: dict, session: dict):
    db = load_db()
    uid = session.get("uid")
    if uid is None:
        return {"code": 500, "msg": "未登录"}

    existing = sess.players_of_uid(db, uid)
    if len(existing) >= EntryConfig.max_players:
        return {"code": 500, "msg": "角色数量已达上限"}

    name = (req.get("name") or "").strip()
    if not name:
        return {"code": 500, "msg": "名字不能为空"}
    if sess.name_taken(db, name):
        return {"code": 500, "msg": "名字已被使用"}

    pid = db.get("next_pid", 178471)
    db["next_pid"] = pid + 1
    server_id = int(session.get("serverId") or 1)
    player = make_default_player(pid, uid, name, session.get("userName", name))
    player["serverId"] = server_id
    player["oldServerId"] = int(session.get("oldServerId") or server_id)
    player["name"] = name
    db["players"][str(pid)] = player
    _starter_mail(db, player)
    _prepare_player(player)
    recalc_power(player)
    save_db(db)

    session["playerId"] = pid
    try:
        push.register(pid, session.get("_sender")) if session.get("_sender") else None
    except Exception:
        pass
    return {"code": 200, "player": player}


@route("connector.playerHandler.entry")
def player_entry(req: dict, session: dict):
    db = load_db()
    uid = session.get("uid")
    pid = req.get("playerId")
    if uid is None:
        return {"code": 500, "msg": "未登录"}
    if not pid:
        return {"code": 500, "msg": "缺少playerId"}
    if not sess.owns_player(db, pid, uid):
        return {"code": 500, "msg": "无权登录该角色"}

    player = db["players"].get(str(pid))
    if player is None:
        return {"code": 500, "msg": "角色不存在"}

    ensure_player_fields(player)
    player["atime"] = _now_ms()
    player["sid"] = "connector-server-1"
    player["logicSid"] = "logic-server-1"
    session["playerId"] = int(pid)
    session["isReconnect"] = bool(req.get("isReconnect"))

    _recover_points(player)
    _prepare_player(player)
    recalc_power(player)
    save_db(db)

    sender = session.get("_sender")
    if sender is not None:
        try:
            push.register(int(pid), sender)
        except Exception:
            pass
    return {"code": 200, "player": player}


def _recover_points(player):
    """Action point / skill point regeneration (30s per point, driven by nextRecoverTimeMap)."""
    now = _now_ms()
    rec = player.setdefault("nextRecoverTimeMap", {})
    caps = player.setdefault("timesMaxMap", {})
    for key, max_key in (("actionPoint", "actionPoint"), ("skillPoint", "skillPoint")):
        cap = int(caps.get(max_key) or player.get(max_key + "Max") or 0)
        if cap <= 0:
            continue
        cur = int(player.get(key) or 0)
        next_time = int(rec.get(key) or 0)
        if next_time <= 0:
            rec[key] = now + 300000
            continue
        if cur >= cap:
            rec[key] = now + 300000
            continue
        gained = (now - next_time) // 300000
        if gained >= 1:
            player[key] = min(cap, cur + gained)
            rec[key] = next_time + gained * 300000
            if player[key] >= cap:
                rec[key] = now + 300000
