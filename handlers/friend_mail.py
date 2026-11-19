from core.router import route
from core.db import find_player_by_id, push_mail, next_mail_id
from core import rewards, push
from handlers import common


def _friend_summary(p: dict):
    return {
        "playerId": p["id"],
        "playerName": p.get("name", "Ninja"),
        "playerLevel": p.get("level", 1),
        "power": p.get("power", 0),
        "playerPhotoInfo": p.get("photoInfo", {"photoImgId": 1003, "shipImgId": 900}),
        "atime": p.get("atime", common.now_ms()),
        "isOnline": push.is_online(p["id"]),
    }


def _friend_bucket(player: dict):
    fr = player.setdefault("friend", {"infoMap": {}, "list": [], "actionPointReceiveTimes": 0, "count": 0})
    fr.setdefault("infoMap", {})
    fr.setdefault("requests", [])
    return fr


# ---------- logic.friendHandler (14/14) ----------

@route("logic.friendHandler.myFriendList")
def friend_list(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    fr = _friend_bucket(ctx.player)
    entries = []
    for fid in list(fr["infoMap"].keys()):
        target = find_player_by_id(ctx.db, fid)
        if target:
            entries.append(_friend_summary(target))
    return ctx.ok(friend=fr, _temp={"list": entries})


@route("logic.friendHandler.recommendList")
def friend_recommend(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    my_id = ctx.player["id"]
    fr = _friend_bucket(ctx.player)
    recs = []
    for pid, p in ctx.db.get("players", {}).items():
        if str(pid) != str(my_id) and str(pid) not in fr["infoMap"]:
            recs.append(_friend_summary(p))
            if len(recs) >= 10:
                break
    return ctx.ok(_temp={"list": recs})


@route("logic.friendHandler.findTarget")
def friend_find_target(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    q = str(req.get("content") or "").strip().lower()
    hits = []
    for pid, p in ctx.db.get("players", {}).items():
        if q and (q == str(pid) or q in str(p.get("name") or "").lower()):
            hits.append(_friend_summary(p))
    return ctx.ok(_temp={"list": hits})


@route("logic.friendHandler.requestAddFriend")
def friend_request_add(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tid = str(req.get("targetId") or "")
    target = find_player_by_id(ctx.db, tid)
    if target:
        tfr = _friend_bucket(target)
        if ctx.player["id"] not in tfr["requests"]:
            tfr["requests"].append(ctx.player["id"])
        ctx.save()
    return ctx.ok()


@route("logic.friendHandler.requestAddFriendList")
def friend_request_list(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    fr = _friend_bucket(ctx.player)
    reqs = []
    for rid in fr.get("requests", []):
        p = find_player_by_id(ctx.db, rid)
        if p:
            reqs.append(_friend_summary(p))
    return ctx.ok(_temp={"list": reqs})


@route("logic.friendHandler.acceptAddFriend")
def friend_accept(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tid = str(req.get("targetId") or "")
    fr = _friend_bucket(ctx.player)
    if tid.isdigit() and int(tid) in fr["requests"]:
        fr["requests"].remove(int(tid))
    target = find_player_by_id(ctx.db, tid)
    if target:
        fr["infoMap"][tid] = {"giveGift": False, "receiveGift": False}
        fr["count"] = len(fr["infoMap"])
        tfr = _friend_bucket(target)
        tfr["infoMap"][str(ctx.player["id"])] = {"giveGift": False, "receiveGift": False}
        tfr["count"] = len(tfr["infoMap"])
        ctx.save()
    return ctx.ok(friend=fr)


@route("logic.friendHandler.acceptAllAddFriend")
def friend_accept_all(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    fr = _friend_bucket(ctx.player)
    for rid in list(fr.get("requests", [])):
        friend_accept({"targetId": rid}, session)
    return ctx.ok(friend=_friend_bucket(ctx.player))


@route("logic.friendHandler.refuseAddFriend")
def friend_refuse(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tid = req.get("targetId")
    fr = _friend_bucket(ctx.player)
    if tid in fr["requests"]:
        fr["requests"].remove(tid)
        ctx.save()
    return ctx.ok(friend=fr)


@route("logic.friendHandler.refuseAllAddFriend")
def friend_refuse_all(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    fr = _friend_bucket(ctx.player)
    fr["requests"] = []
    ctx.save()
    return ctx.ok(friend=fr)


@route("logic.friendHandler.removeFriend")
def friend_remove(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tid = str(req.get("targetId") or "")
    fr = _friend_bucket(ctx.player)
    fr["infoMap"].pop(tid, None)
    fr["count"] = len(fr["infoMap"])
    target = find_player_by_id(ctx.db, tid)
    if target:
        tfr = _friend_bucket(target)
        tfr["infoMap"].pop(str(ctx.player["id"]), None)
        tfr["count"] = len(tfr["infoMap"])
    ctx.save()
    return ctx.ok(friend=fr)


@route("logic.friendHandler.giveGift")
def friend_give_gift(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tid = str(req.get("targetId") or "")
    fr = _friend_bucket(ctx.player)
    if tid in fr["infoMap"]:
        fr["infoMap"][tid]["giveGift"] = True
        ctx.save()
    return ctx.ok(friend=fr)


@route("logic.friendHandler.giveGiftAll")
def friend_give_gift_all(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    fr = _friend_bucket(ctx.player)
    for info in fr["infoMap"].values():
        if isinstance(info, dict):
            info["giveGift"] = True
    ctx.save()
    return ctx.ok(friend=fr)


@route("logic.friendHandler.receiveGift")
def friend_receive_gift(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tid = str(req.get("targetId") or "")
    fr = _friend_bucket(ctx.player)
    if tid in fr["infoMap"]:
        fr["infoMap"][tid]["receiveGift"] = True
    fr["actionPointReceiveTimes"] = int(fr.get("actionPointReceiveTimes") or 0) + 1
    ctx.player["actionPoint"] = int(ctx.player.get("actionPoint") or 0) + 2
    ctx.save()
    return ctx.ok(friend=fr, actionPoint=ctx.player["actionPoint"])


@route("logic.friendHandler.receiveGiftAll")
def friend_receive_gift_all(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    fr = _friend_bucket(ctx.player)
    ctx.player["actionPoint"] = int(ctx.player.get("actionPoint") or 0) + 10
    ctx.save()
    return ctx.ok(friend=fr, actionPoint=ctx.player["actionPoint"])


# ---------- logic.mailHandler (5/5) ----------

@route("logic.mailHandler.read")
def mail_read(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    mid = req.get("mailId")
    mails = ctx.player.setdefault("extra", {}).setdefault("mails", [])
    for m in mails:
        if m.get("_id") == mid:
            m["status"] = 2
            break
    ctx.save()
    return ctx.ok(extra={"mails": mails})


@route("logic.mailHandler.receive")
def mail_receive(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    mid = req.get("mailId")
    mails = ctx.player.setdefault("extra", {}).setdefault("mails", [])
    counts = {}
    for m in mails:
        if m.get("_id") == mid and not m.get("isReceived"):
            m["isReceived"] = True
            m["status"] = 2
            counts = rewards.grant_items(ctx.player, m.get("dropList") or [])
            break
    ctx.save()
    return ctx.ok(
        bag=ctx.player["bag"],
        coin=ctx.player["coin"],
        gem=ctx.player["gem"],
        extra={"mails": mails},
        _temp={"entityCountMap": counts},
    )


@route("logic.mailHandler.receiveAll")
def mail_receive_all(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    mails = ctx.player.setdefault("extra", {}).setdefault("mails", [])
    all_drops = []
    for m in mails:
        if not m.get("isReceived"):
            m["isReceived"] = True
            m["status"] = 2
            all_drops.extend(m.get("dropList") or [])
    counts = rewards.grant_items(ctx.player, all_drops) if all_drops else {}
    ctx.save()
    return ctx.ok(
        bag=ctx.player["bag"],
        coin=ctx.player["coin"],
        gem=ctx.player["gem"],
        extra={"mails": mails},
        _temp={"entityCountMap": counts},
    )


@route("logic.mailHandler.removeAllRead")
def mail_remove_all_read(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    extra = ctx.player.setdefault("extra", {})
    mails = [m for m in extra.get("mails", []) if m.get("status") != 2 and not m.get("isReceived")]
    extra["mails"] = mails
    ctx.save()
    return ctx.ok(extra={"mails": mails})


@route("logic.mailHandler.send")
def mail_send(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tid = req.get("targetId")
    content = str(req.get("content") or "")
    mail = {
        "_id": next_mail_id(ctx.db),
        "isSys": False,
        "status": 1,
        "type": 2,
        "senderId": ctx.player["id"],
        "senderName": ctx.player.get("name", "Ninja"),
        "title": f"来自 {ctx.player.get('name', 'Ninja')} 的邮件",
        "body": content,
        "ctime": common.now_ms(),
        "expireTime": common.now_ms() + 604800000,
        "dropList": [],
        "isReceived": False,
    }
    if push_mail(ctx.db, tid, mail):
        ctx.save()
        push.new_mail(tid, mail)
    return ctx.ok()


# ---------- chat.chatHandler (1/1) ----------

@route("chat.chatHandler.getGuildLast")
def chat_guild_last(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    gid = str(ctx.player.get("guildId") or "0")
    msgs = ctx.db.get("guild_chats", {}).get(gid, [])
    return ctx.ok(list=msgs)
