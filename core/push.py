"""Push (MSG_PUSH) channel: server -> client unsolicited messages.

The client registers listeners for onSync / onSyncZip / onRewardPop / onNewMail /
onChat / onKick / onGuildBattle / ... ; without MSG_PUSH none of these ever fire.
"""
import json
import asyncio
import threading

from core.pomelo_proto import MSG_PUSH, PKG_DATA, encode_package, encode_message
from core.payload import encode_field

ZIP_EVENTS = {"onSyncZip", "onUpdatePrestigeBattleCreateTeamInfo", "onUpdateTeamBattleCreateTeamInfo"}

_sessions = {}
_lock = threading.RLock()
_loop = None


def set_loop(loop):
    global _loop
    _loop = loop


def register(player_id, sender):
    """sender: callable(bytes) -> None that writes one WS frame."""
    with _lock:
        _sessions[int(player_id)] = sender


def unregister(player_id, sender=None):
    with _lock:
        cur = _sessions.get(int(player_id))
        if cur is not None and (sender is None or cur is sender):
            _sessions.pop(int(player_id), None)


def online_players():
    with _lock:
        return list(_sessions.keys())


def is_online(player_id):
    with _lock:
        return int(player_id) in _sessions


def _frame(event: str, payload) -> bytes:
    if event in ZIP_EVENTS:
        body = encode_field(payload)
    else:
        body = payload
    msg = encode_message(0, MSG_PUSH, event, body)
    return encode_package(PKG_DATA, msg)


def send_to(player_id, event: str, payload):
    with _lock:
        sender = _sessions.get(int(player_id))
    if sender is None:
        return False
    try:
        sender(_frame(event, payload))
        return True
    except Exception:
        unregister(player_id)
        return False


def send_many(player_ids, event: str, payload):
    sent = 0
    for pid in list(player_ids):
        if send_to(pid, event, payload):
            sent += 1
    return sent


def broadcast(event: str, payload, exclude=()):
    exclude = {int(x) for x in exclude}
    with _lock:
        targets = [pid for pid in _sessions if pid not in exclude]
    return send_many(targets, event, payload)


# ---------- convenience helpers used by handlers ----------

def sync(player_id, payload: dict):
    """Push a partial player delta (same shape as a request response body)."""
    return send_to(player_id, "onSync", payload)


def sync_zip(player_id, payload: dict):
    return send_to(player_id, "onSyncZip", payload)


def reward_pop(player_id, entity_count_map: dict, is_pop_now: bool = True):
    return send_to(
        player_id,
        "onRewardPop",
        {"entityCountMap": entity_count_map, "isPopNow": is_pop_now},
    )


def new_mail(player_id, mail: dict):
    return send_to(player_id, "onNewMail", {"mail": mail})


def chat(player_id, message: dict):
    return send_to(player_id, "onChat", message)


def kick(player_id, reason: str = "账号在其他设备登录"):
    send_to(player_id, "onKick", {"msg": reason})
    unregister(player_id)
