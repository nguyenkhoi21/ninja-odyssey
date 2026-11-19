import time

from core.router import route, prefix_handler
from core.db import (
    load_db,
    save_db,
    get_player,
    add_item_to_bag,
    remove_item_from_bag,
    add_role_to_team,
    push_mail,
    next_mail_id,
)
from core import schema, gamedata as gd, rewards, activity, tasks, push
from core.templates import get_ws_template
from handlers import common

DAY = 86400000


def _now():
    return common.now_ms()


def _daily_reset(player):
    """Reset per-day counters when the day changed."""
    now = _now()
    last = int(player.get("resetTime") or 0)
    if last and now - last < DAY:
        return False
    player["resetTime"] = now
    player["dailyBuyGoodsTimesMap"] = {}
    player["dailyTopUpMoney"] = 0
    task = player.setdefault("task", {})
    task["daily"] = {}
    task["receivedPointMap"] = {}
    player.setdefault("activity", {})["received"] = {}
    arena = player.setdefault("arena", {})
    arena["challengeTimes"] = 0
    arena["remainingChallengeTimes"] = int(arena.get("maxChallengeTimes") or 5)
    player.setdefault("point", {})["dailyCoinTimes"] = 0
    player["point"]["dailyUseGemTimes"] = 0
    extra = player.setdefault("extra", {})
    extra["openDays"] = int(extra.get("openDays") or 0) + 1
    tasks.ensure_daily_tasks(player)
    activity.refresh_activity(player)
    return True


def _prepare(player):
    schema.ensure_player_fields(player)
    _daily_reset(player)
    tasks.ensure_main_task(player)
    tasks.ensure_daily_tasks(player)
    activity.refresh_activity(player)
    return player


# ---------------- basic player ops ----------------

@route("logic.playerHandler.incOnlineTime")
def inc_online_time(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    sec = int(req.get("seconds") or 10)
    p["onlineTime"] = int(p.get("onlineTime") or 0) + sec
    player_sec = int(p.get("activityReach", {}).get("onlineSeconds") or 0) + sec
    p.setdefault("activityReach", {})["onlineSeconds"] = player_sec
    activity.refresh_activity(p)
    ctx.save()
    return ctx.ok(onlineTime=p["onlineTime"])


@route("logic.playerHandler.rename")
def rename(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    name = (req.get("name") or "").strip()
    if not name:
        return ctx.err("名字不能为空")
    from core import session as sess
    if sess.name_taken(ctx.db, name, exclude_pid=ctx.player["id"]):
        return ctx.err("名字已被使用")
    cost = 500
    if int(ctx.player.get("gem") or 0) < cost:
        return ctx.err("钻石不足")
    ctx.player["gem"] = int(ctx.player["gem"]) - cost
    ctx.player["costGem"] = int(ctx.player.get("costGem") or 0) + cost
    ctx.player["name"] = name
    ctx.save()
    return ctx.ok(name=name, gem=ctx.player["gem"], costGem=ctx.player["costGem"])


@route("logic.playerHandler.signIn")
def sign_in(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    now = _now()
    last = int(p.get("signInTime") or 0)
    if last and now - last < DAY:
        return ctx.err("今日已签到")

    days = int(p.get("signInDays") or 0) + 1
    p["signInTime"] = now
    p["signInDays"] = days

    row = None
    for r in gd.table("signInData"):
        if isinstance(r, dict) and r.get("signInDays") == ((days - 1) % 30) + 1:
            row = r
            break
    items = rewards.parse_drop_desc((row or {}).get("dropListDesc") or "202x2")
    counts = rewards.grant_items(p, items)
    is_double = bool(row and row.get("doubleVip") == 0 and int(p.get("vip", {}).get("level") or 0) > 0)
    if is_double:
        for it in items:
            extra = rewards.grant_items(p, [it])
            for k, v in extra.items():
                counts[k] = counts.get(k, 0) + v

    tasks.complete_daily(p, 2001, True, "1/1")
    schema.recalc_power(p)
    ctx.save()
    return ctx.ok(
        bag=p["bag"], signInTime=now, signInDays=days,
        _temp=ctx.temp(entityCountMap=counts, isDouble=is_double),
    )


@route("logic.playerHandler.useItem")
def use_item(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    bag = p.setdefault("bag", {"items": {}, "lastIdx": 0})
    idx = str(req.get("bagIndex"))
    cnt = max(1, int(req.get("itemCount") or 1))
    item = bag.get("items", {}).get(idx)
    if not item:
        return ctx.err("道具不存在")
    kind_id = int(item.get("kindId") or 0)
    have = int(item.get("count") or 0)
    if have < cnt:
        return ctx.err("道具数量不足")

    row = gd.entity(kind_id) or gd.find("consumablesData", "kindId", kind_id) or {}
    etype = row.get("type")
    counts = {}

    if etype == "box" or row.get("selectCount"):
        return ctx.err("请选择宝箱奖励")

    role_exp = int(row.get("roleExp") or 0)
    action_point = int(row.get("actionPoint") or 0)
    if role_exp:
        gained = role_exp * cnt
        p["experience"] = int(p.get("experience") or 0) + gained
        counts[str(kind_id)] = cnt
    elif action_point:
        p["actionPoint"] = int(p.get("actionPoint") or 0) + action_point * cnt
        counts[str(kind_id)] = cnt
    elif etype == "title":
        p.setdefault("titleInfoMap", {})[str(kind_id)] = {"imgId": kind_id, "expireTime": -1}
        p["honourPoint"] = int(p.get("honourPoint") or 0) + 20
        counts[str(kind_id)] = cnt
    else:
        counts[str(kind_id)] = cnt

    remove_item_from_bag(p, idx, cnt)
    tasks.complete_daily(p, 2006, True, "1/1")
    schema.recalc_power(p)
    ctx.save()
    res = ctx.ok(bag=p["bag"], _temp=ctx.temp(entityCountMap=counts))
    if role_exp:
        res["experience"] = p["experience"]
    if action_point:
        res["actionPoint"] = p["actionPoint"]
    if etype == "title":
        res["honourPoint"] = p["honourPoint"]
        res["titleInfoMap"] = p["titleInfoMap"]
    return res


def _box_rewards(kind_id):
    row = gd.find("entityExtData", "kindId", kind_id) or gd.entity(kind_id) or {}
    extra = row.get("extra") or {}
    desc = extra.get("dropListDesc") or ""
    return rewards.parse_drop_desc(desc), int(extra.get("selectCount") or 1)


@route("logic.playerHandler.selectBoxReward")
def select_box_reward(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    bag = p.setdefault("bag", {"items": {}, "lastIdx": 0})
    idx = str(req.get("bagIndex"))
    cnt = max(1, int(req.get("itemCount") or 1))
    item = bag.get("items", {}).get(idx)
    if not item:
        return ctx.err("道具不存在")
    kind_id = int(item.get("kindId") or 0)
    if int(item.get("count") or 0) < cnt:
        return ctx.err("道具数量不足")

    options, select_count = _box_rewards(kind_id)
    if not options:
        return ctx.err("宝箱配置错误")
    reward_idxs = req.get("rewardIdxs") or []
    picks = []
    for i in reward_idxs[:select_count]:
        try:
            pos = int(i)
        except (TypeError, ValueError):
            continue
        if 0 <= pos < len(options):
            picks.append(options[pos])
    if not picks:
        picks = options[:select_count]

    items = []
    for it in picks:
        items.append({"entityId": it["entityId"], "count": it["count"] * cnt, "extra": it.get("extra")})
    counts = rewards.grant_items(p, items)
    remove_item_from_bag(p, idx, cnt)
    schema.recalc_power(p)
    ctx.save()
    return ctx.ok(bag=p["bag"], _temp=ctx.temp(entityCountMap=counts))


@route("logic.playerHandler.selectBoxReward2")
def select_box_reward2(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    bag = p.setdefault("bag", {"items": {}, "lastIdx": 0})
    idx = str(req.get("bagIndex"))
    cnt = max(1, int(req.get("itemCount") or 1))
    item = bag.get("items", {}).get(idx)
    if not item:
        return ctx.err("道具不存在")
    kind_id = int(item.get("kindId") or 0)
    if int(item.get("count") or 0) < cnt:
        return ctx.err("道具数量不足")

    options, _ = _box_rewards(kind_id)
    if not options:
        return ctx.err("宝箱配置错误")
    count_map = req.get("rewardIdxCountMap") or {}
    items = []
    for pos_s, n in count_map.items():
        try:
            pos = int(pos_s)
            n = int(n)
        except (TypeError, ValueError):
            continue
        if 0 <= pos < len(options) and n > 0:
            opt = options[pos]
            items.append({"entityId": opt["entityId"], "count": opt["count"] * n * cnt,
                          "extra": opt.get("extra")})
    if not items:
        return ctx.err("请选择奖励")
    counts = rewards.grant_items(p, items)
    remove_item_from_bag(p, idx, cnt)
    schema.recalc_power(p)
    ctx.save()
    return ctx.ok(bag=p["bag"], _temp=ctx.temp(entityCountMap=counts))


@route("logic.playerHandler.receiveTaskAward")
def receive_task_award(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = _prepare(ctx.player)
    tid = req.get("taskId")
    try:
        tid = int(tid)
    except (TypeError, ValueError):
        return ctx.err("参数错误")

    desc, err = tasks.claim_task_award(p, tid)
    if err:
        return ctx.err(err)

    items = rewards.parse_drop_desc(desc or "")
    counts = rewards.grant_items(p, items)
    row = gd.find("taskData", "kindId", tid) or {}
    ap = int(row.get("activePoint") or 0)
    if ap:
        activity.add_task_active_point(p, ap)
        counts["99"] = counts.get("99", 0)

    activity.refresh_activity(p)
    schema.recalc_power(p)
    ctx.save()
    return ctx.ok(
        bag=p["bag"], task=p["task"], activity={"map": p["activity"]["map"]},
        _temp=ctx.temp(entityCountMap=counts),
    )


@route("logic.playerHandler.receiveTaskActiveAward")
def receive_task_active_award(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = _prepare(ctx.player)
    kind = str(req.get("type") or "daily")
    point = int(req.get("point") or 0)
    bucket = tasks.active_point_rewards(p, kind)
    if str(point) in bucket:
        return ctx.err("已领取")

    milestone = {
        50: "21001x10,49907x5,49912x5",
        100: "21001x10,49907x5,49912x5,9030x2",
        150: "21001x20,49907x10,49912x10,9030x2",
    }
    desc = milestone.get(point)
    if not desc:
        return ctx.err("奖励不存在")

    cur = int(p.get("task", {}).get("activePoint") or 0)
    if cur < point:
        return ctx.err("活跃度不足")

    items = rewards.parse_drop_desc(desc)
    counts = rewards.grant_items(p, items)
    bucket[str(point)] = True
    p["vip"]["topUpGem"] = int(p["vip"].get("topUpGem") or 0) + 50
    p["vip"]["giftGem"] = int(p["vip"].get("giftGem") or 0) + 50
    schema.recalc_power(p)
    ctx.save()
    return ctx.ok(
        bag=p["bag"], task={"receivedPointMap": p["task"]["receivedPointMap"]},
        vip={"topUpGem": p["vip"]["topUpGem"], "giftGem": p["vip"]["giftGem"]},
        _temp=ctx.temp(entityCountMap=counts),
    )


@route("logic.playerHandler.receiveActivityAward")
def receive_activity_award(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = _prepare(ctx.player)
    name = req.get("activityName")
    idx = req.get("rewardIdx")
    if not name:
        return ctx.err("参数错误")
    desc, err = activity.claim_activity(p, name, idx)
    if err:
        return ctx.err(err)
    items = rewards.parse_drop_desc(desc or "")
    counts = rewards.grant_items(p, items)
    schema.recalc_power(p)
    ctx.save()
    return ctx.ok(
        bag=p["bag"], activity={"map": p["activity"]["map"]},
        _temp=ctx.temp(entityCountMap=counts),
    )


@route("logic.playerHandler.receiveActivityAward2")
def receive_activity_award2(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = _prepare(ctx.player)
    names = req.get("activityNames") or []
    idxs = req.get("rewardIdxs") or []
    if not isinstance(names, list) or not isinstance(idxs, list):
        return ctx.err("参数错误")
    items = []
    claimed = 0
    for name, idx in zip(names, idxs):
        desc, err = activity.claim_activity(p, name, idx)
        if err:
            continue
        items.extend(rewards.parse_drop_desc(desc or ""))
        claimed += 1
    if not claimed:
        return ctx.err("没有可领取的奖励")
    counts = rewards.grant_items(p, items)
    schema.recalc_power(p)
    ctx.save()
    return ctx.ok(
        bag=p["bag"], coin=p.get("coin", 0), activity={"map": p["activity"]["map"]},
        _temp=ctx.temp(entityCountMap=counts),
    )


@route("logic.playerHandler.useGiftCode")
def use_gift_code(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    code = str(req.get("giftCode") or "").strip().upper()
    if not code:
        return ctx.err("请输入礼包码")
    used = p.setdefault("usedGiftCodes", [])
    if code in used:
        return ctx.err("礼包码已使用")
    codes = ctx.db.setdefault("gift_codes", {})
    desc = codes.get(code) or "101x50000,102x500,116x1000,60002x2"
    used.append(code)
    items = rewards.parse_drop_desc(desc)
    counts = rewards.grant_items(p, items)
    schema.recalc_power(p)
    ctx.save()
    return ctx.ok(bag=p["bag"], _temp=ctx.temp(entityCountMap=counts))


def _gem_cost(kind, times):
    return max(0, 50 * times)


@route("logic.playerHandler.buyCoin")
def buy_coin(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    vip = p.setdefault("vip", {})
    times = int(vip.get("buyCoinTimes") or 0)
    cost = 50 + 50 * min(times, 19)
    if int(p.get("gem") or 0) < cost:
        return ctx.err("钻石不足")
    get_coin = int((30000 + 100 * int(p.get("level") or 1)) * 1.0)
    p["gem"] = int(p["gem"]) - cost
    p["costGem"] = int(p.get("costGem") or 0) + cost
    p["coin"] = int(p.get("coin") or 0) + get_coin
    vip["buyCoinTimes"] = times + 1
    tasks.complete_daily(p, 2008, True, "1/1")
    activity.refresh_activity(p)
    ctx.save()
    return ctx.ok(
        coin=p["coin"], gem=p["gem"], costGem=p["costGem"],
        task={"daily": {"2008": p["task"]["daily"].get("2008")}},
        vip={"buyCoinTimes": vip["buyCoinTimes"]},
        _temp=ctx.temp(costGem=cost, getCoin=get_coin, ratio=1),
    )


@route("logic.playerHandler.buyActionPoint")
def buy_action_point(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    vip = p.setdefault("vip", {})
    times = int(vip.get("buyActionPointTimes") or 0)
    costs = [0, 250, 250, 250, 500, 500, 500, 1000, 1000, 1000, 2000]
    cost = costs[min(times, len(costs) - 1)]
    if int(p.get("gem") or 0) < cost:
        return ctx.err("钻石不足")
    p["gem"] = int(p["gem"]) - cost
    p["costGem"] = int(p.get("costGem") or 0) + cost
    p["actionPoint"] = int(p.get("actionPoint") or 0) + 120
    vip["buyActionPointTimes"] = times + 1
    tasks.complete_daily(p, 2009, True, "1/1")
    activity.refresh_activity(p)
    ctx.save()
    return ctx.ok(
        gem=p["gem"], costGem=p["costGem"], actionPoint=p["actionPoint"],
        task={"daily": {"2009": p["task"]["daily"].get("2009")}},
        vip={"buyActionPointTimes": vip["buyActionPointTimes"]},
        _temp=ctx.temp(costGem=cost, getActionPoint=120),
    )


@route("logic.playerHandler.buySkillPoint")
def buy_skill_point(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    vip = p.setdefault("vip", {})
    times = int(vip.get("buySkillPointTimes") or 0)
    costs = [0, 50, 100, 100, 100, 200, 200, 200, 200, 200, 500]
    cost = costs[min(times, len(costs) - 1)]
    if int(p.get("gem") or 0) < cost:
        return ctx.err("钻石不足")
    p["gem"] = int(p["gem"]) - cost
    p["costGem"] = int(p.get("costGem") or 0) + cost
    p["skillPoint"] = int(p.get("skillPoint") or 0) + 10
    vip["buySkillPointTimes"] = times + 1
    ctx.save()
    return ctx.ok(
        gem=p["gem"], costGem=p["costGem"], skillPoint=p["skillPoint"],
        vip={"buySkillPointTimes": vip["buySkillPointTimes"]},
        _temp=ctx.temp(costGem=cost, getPoint=10),
    )


@route("logic.playerHandler.dreamRoll")
def dream_roll(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = _prepare(ctx.player)
    dream = p.setdefault("activity", {}).setdefault("dream", {"curPos": 0, "logs": []})
    diy_point = int(req.get("diyPoint") or 0)
    if diy_point > 0:
        if int(p.get("gem") or 0) < diy_point:
            return ctx.err("钻石不足")
        p["gem"] = int(p["gem"]) - diy_point
        p["costGem"] = int(p.get("costGem") or 0) + diy_point

    drop = rewards.roll_drop_class(901, 1) or [{"entityId": 20003, "count": 10}]
    counts = rewards.grant_items(p, drop)
    gain = 6
    dream["curPos"] = int(dream.get("curPos") or 0) + gain
    logs = dream.setdefault("logs", [])
    logs.insert(0, {
        "time": _now(), "point": gain,
        "dropDesc": ",".join(f"{d['entityId']}x{d['count']}" for d in drop),
    })
    del logs[50:]
    activity.refresh_activity(p)
    ctx.save()
    return ctx.ok(
        bag=p["bag"], activity={"dream": dream}, gem=p.get("gem", 0),
        _temp=ctx.temp(dropList=rewards.to_drop_list(drop), event=0, point=gain),
    )


@route("logic.playerHandler.rollDial")
def roll_dial(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = _prepare(ctx.player)
    dtype = str(req.get("type") or "coin")
    times = max(1, int(req.get("times") or 1))
    cost_ids = {"luck": 113, "vip": 114, "svip": 117, "shen": 119, "pay": 131, "coin": 104, "gem": 102}
    cost_id = cost_ids.get(dtype, 102)
    cost = times * (100 if cost_id == 102 else 1)

    if cost_id == 102:
        if int(p.get("gem") or 0) < cost:
            return ctx.err("钻石不足")
        p["gem"] = int(p["gem"]) - cost
        p["costGem"] = int(p.get("costGem") or 0) + cost
    else:
        have = 0
        for it in p.get("bag", {}).get("items", {}).values():
            if it and int(it.get("kindId") or 0) == cost_id:
                have += int(it.get("count") or 0)
        if have < cost:
            return ctx.err("道具不足")
        left = cost
        for idx, it in list(p.get("bag", {}).get("items", {}).items()):
            if left <= 0:
                break
            if it and int(it.get("kindId") or 0) == cost_id:
                take = min(left, int(it.get("count") or 0))
                remove_item_from_bag(p, idx, take)
                left -= take

    drops = []
    for _ in range(times):
        drops.extend(rewards.roll_drop_class(902, 1))
    if not drops:
        drops = [{"entityId": 102, "count": 500}]
    counts = rewards.grant_items(p, drops)
    schema.recalc_power(p)
    ctx.save()
    return ctx.ok(
        bag=p["bag"], gem=p.get("gem", 0), coin=p.get("coin", 0),
        _temp=ctx.temp(dropList=rewards.to_drop_list(drops)),
    )


@route("logic.playerHandler.receiveHonourReward")
def receive_honour_reward(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    lvl = str(req.get("level") or 1)
    received = p.setdefault("honourReceivedMap", {})
    if received.get(lvl):
        return ctx.err("已领取")
    received[lvl] = True
    items = [{"entityId": 481, "count": 1}, {"entityId": 523, "count": 1}]
    counts = rewards.grant_items(p, items)
    schema.recalc_power(p)
    ctx.save()
    return ctx.ok(bag=p["bag"], honourReceivedMap=received, _temp=ctx.temp(entityCountMap=counts))


@route("logic.playerHandler.setPhotoImg")
def set_photo_img(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    ctx.player.setdefault("photoInfo", {})["photoImgId"] = int(req.get("imgId") or 1003)
    ctx.save()
    return ctx.ok(photoInfo=ctx.player["photoInfo"])


@route("logic.playerHandler.setShipImg")
def set_ship_img(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    ctx.player.setdefault("photoInfo", {})["shipImgId"] = int(req.get("imgId") or 900)
    ctx.save()
    return ctx.ok(photoInfo=ctx.player["photoInfo"])


@route("logic.playerHandler.setTitleImg")
def set_title_img(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    img_id = int(req.get("imgId") or 0)
    info = ctx.player.setdefault("photoInfo", {})
    if img_id:
        info["titleImgId"] = img_id
    else:
        info.pop("titleImgId", None)
    ctx.save()
    return ctx.ok(photoInfo=info)


@route("logic.playerHandler.setChatSkin")
def set_chat_skin(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    img_id = int(req.get("imgId") or 0)
    skins = ctx.player.setdefault("chatSkinIds", [0])
    if img_id not in skins:
        skins.append(img_id)
    ctx.player.setdefault("photoInfo", {})["chatImgId"] = img_id
    ctx.save()
    return ctx.ok(chatSkinIds=skins, photoInfo=ctx.player["photoInfo"])


@route("logic.playerHandler.sendChat")
def send_chat(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    ctype = int(req.get("type") or 1)
    words = str(req.get("words") or "").strip()
    if not words:
        return ctx.err("消息不能为空")

    msg = {
        "playerId": p["id"],
        "playerName": p["name"],
        "playerLevel": p.get("level", 1),
        "playerPhotoInfo": p.get("photoInfo", {}),
        "guildId": p.get("guildId", 0),
        "guildName": p.get("guildName"),
        "type": ctype,
        "words": words,
        "ctime": _now(),
        "serverId": p.get("serverId", 1),
    }
    chat = ctx.db.setdefault("chat", {"world": [], "guild": {}, "allServer": []})
    if ctype == 2 and p.get("guildId"):
        bucket = chat.setdefault("guild", {}).setdefault(str(p["guildId"]), [])
    elif ctype == 3:
        bucket = chat.setdefault("allServer", [])
    else:
        bucket = chat.setdefault("world", [])
    bucket.insert(0, msg)
    del bucket[100:]

    if ctype == 2 and p.get("guildId"):
        g = ctx.db.get("guilds", {}).get(str(p["guildId"])) or {}
        targets = g.get("memberIds") or []
    else:
        targets = push.online_players()
    for pid in targets:
        if pid != p["id"]:
            push.chat(pid, msg)
    ctx.save()
    return ctx.ok(_temp=ctx.temp())


@route("logic.playerHandler.costTopUpPoint")
def cost_top_up_point(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    goods_id = str(req.get("goodsId") or "")
    goods = (p.get("extra", {}).get("goodsList") or {}).get(goods_id) or {}
    gem = int(goods.get("getTicket") or 0) or 6480
    money = int(goods.get("price") or 0) or 648

    p["topUpPoint"] = int(p.get("topUpPoint") or 0) + money
    p["dailyTopUpMoney"] = int(p.get("dailyTopUpMoney") or 0) + money
    vip = p.setdefault("vip", {})
    vip["topUpMoney"] = int(vip.get("topUpMoney") or 0) + money
    vip["topUpGem"] = int(vip.get("topUpGem") or 0) + gem
    _, bag = add_item_to_bag(p, 2, gem)
    _refresh_vip(p)
    ctx.save()
    return ctx.ok(
        bag=bag, dailyTopUpMoney=p["dailyTopUpMoney"],
        vip={"topUpMoney": vip["topUpMoney"], "level": vip["level"]},
        _temp=ctx.temp(),
    )


def _refresh_vip(p):
    vip = p.setdefault("vip", {})
    top = int(vip.get("topUpGem") or 0)
    level = 0
    for row in gd.table("vipData"):
        if not isinstance(row, dict):
            continue
        if top >= int(row.get("nextLevelTopUpGem") or 0):
            level = max(level, int(row.get("level") or 0))
    if level != int(vip.get("level") or 0):
        vip["level"] = level
    return vip


@route("logic.playerHandler.topUpGoodsList")
def top_up_goods_list(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    extra = ctx.player.setdefault("extra", {})
    goods = extra.setdefault("goodsList", {})
    if not goods:
        for i, (price, ticket) in enumerate([(6, 60), (30, 300), (98, 980), (198, 1980), (328, 3280), (648, 6480)], 1):
            goods[str(1000 + i)] = {
                "id": 1000 + i, "name": f"{ticket}钻石", "imgId": i,
                "price": price, "show": f"{price}元", "getTicket": ticket,
                "firstGiftRate": 1 if i == 1 else 0, "isFirstDouble": 1 if i <= 2 else 0,
                "isRecommend": i == 3, "dailyBuyMaxTimes": 0, "weeklyBuyMaxTimes": 0,
                "showNeedTopUpMoney": 0, "isNoUsePoint": 0,
            }
        ctx.save()
    return ctx.ok(extra={"goodsList": goods})


@route("logic.playerHandler.buyGemGoods")
def buy_gem_goods(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    cost = int(req.get("costGem") or 0)
    if cost <= 0:
        return ctx.err("参数错误")
    if int(p.get("gem") or 0) < cost:
        return ctx.err("钻石不足")
    p["gem"] = int(p["gem"]) - cost
    p["costGem"] = int(p.get("costGem") or 0) + cost
    goods_id = str(req.get("id") or "")
    goods = (p.get("extra", {}).get("goodsList") or {}).get(goods_id) or {}
    items = rewards.parse_drop_desc(goods.get("dropListDesc") or "101x100000")
    counts = rewards.grant_items(p, items)
    activity.refresh_activity(p)
    ctx.save()
    return ctx.ok(bag=p["bag"], gem=p["gem"], costGem=p["costGem"],
                  _temp=ctx.temp(entityCountMap=counts))


@route("logic.playerHandler.exchange")
def player_exchange(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    exchange_id = str(req.get("exchangeId") or "")
    item_id = str(req.get("id") or "")
    cfg = (ctx.db.get("exchange_config") or {}).get(exchange_id) or {}
    cost = cfg.get("cost") or {"entityId": 102, "count": 100}
    gain = cfg.get("gain") or {"entityId": 101, "count": 50000}

    if cost["entityId"] == 102:
        if int(p.get("gem") or 0) < cost["count"]:
            return ctx.err("钻石不足")
        p["gem"] = int(p["gem"]) - cost["count"]
    else:
        ok = False
        for idx, it in list(p.get("bag", {}).get("items", {}).items()):
            if it and int(it.get("kindId") or 0) == cost["entityId"] and int(it.get("count") or 0) >= cost["count"]:
                remove_item_from_bag(p, idx, cost["count"])
                ok = True
                break
        if not ok:
            return ctx.err("道具不足")

    counts = rewards.grant_items(p, [gain])
    schema.recalc_power(p)
    ctx.save()
    return ctx.ok(bag=p["bag"], gem=p.get("gem", 0), coin=p.get("coin", 0),
                  _temp=ctx.temp(entityCountMap=counts))


for _alias in ("exchangeBuy", "exchange2Buy", "exchange3Buy", "exchange4Buy",
               "spWishExchangeBuy", "buyGetBack", "receiveDailyBuyout"):
    route("logic.playerHandler." + _alias)(player_exchange)


@route("logic.playerHandler.activitySaveGem")
def activity_save_gem(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    name = str(req.get("activityName") or "")
    save_map = p.setdefault("activitySaveGem", {})
    save_map[name] = int(p.get("gem") or 0)
    ctx.save()
    return ctx.ok(activity={"saveGem": save_map}, _temp=ctx.temp())


@route("logic.playerHandler.updateFreeActivity")
def update_free_activity(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = _prepare(ctx.player)
    ctx.save()
    return ctx.ok(activity={"map": p["activity"]["map"]}, _temp=ctx.temp())


@route("logic.playerHandler.fillTaskActive")
def fill_task_active(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = _prepare(ctx.player)
    activity.add_task_active_point(p, 20)
    activity.refresh_activity(p)
    ctx.save()
    return ctx.ok(task=p["task"], activity={"map": p["activity"]["map"]},
                  _temp=ctx.temp(entityCountMap={"99": 20}))


@route("logic.playerHandler.fillSpActive")
def fill_sp_active(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = _prepare(ctx.player)
    p.setdefault("activityReach", {})["spActive"] = 1
    ctx.save()
    return ctx.ok(_temp=ctx.temp())


@route("logic.playerHandler.fillLoginTopUp")
def fill_login_top_up(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = _prepare(ctx.player)
    activity.refresh_activity(p)
    ctx.save()
    return ctx.ok(activity={"map": p["activity"]["map"]}, _temp=ctx.temp())


@route("logic.playerHandler.scorePoint")
def score_point(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    times = max(1, int(req.get("times") or 1))
    cost = times * 100
    if int(p.get("gem") or 0) < cost:
        return ctx.err("钻石不足")
    p["gem"] = int(p["gem"]) - cost
    p["costGem"] = int(p.get("costGem") or 0) + cost
    score = p.setdefault("scorePoint", {})
    name = str(req.get("activityName") or "default")
    score[name] = int(score.get(name) or 0) + times * 10
    drops = [{"entityId": 102, "count": 50}]
    counts = rewards.grant_items(p, drops)
    ctx.save()
    return ctx.ok(gem=p["gem"], _temp=ctx.temp(dropList=rewards.to_drop_list(drops),
                                               entityCountMap=counts))


@route("logic.playerHandler.receiveScorePointBoxReward")
def receive_score_point_box_reward(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    name = str(req.get("activityName") or "default")
    score = int(req.get("score") or 0)
    received = p.setdefault("scorePointReceived", {}).setdefault(name, {})
    if str(score) in received:
        return ctx.err("已领取")
    cur = int((p.get("scorePoint") or {}).get(name) or 0)
    if cur < score:
        return ctx.err("积分不足")
    received[str(score)] = True
    items = rewards.parse_drop_desc("102x200,21002x5")
    counts = rewards.grant_items(p, items)
    ctx.save()
    return ctx.ok(bag=p["bag"], _temp=ctx.temp(entityCountMap=counts))


@route("logic.playerHandler.spWish")
def sp_wish(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    times = max(1, int(req.get("times") or 1))
    cost = times * 100
    if int(p.get("gem") or 0) < cost:
        return ctx.err("钻石不足")
    p["gem"] = int(p["gem"]) - cost
    p["costGem"] = int(p.get("costGem") or 0) + cost
    drops = rewards.roll_drop_class(901, times) or [{"entityId": 20002, "count": 1}]
    counts = rewards.grant_items(p, drops)
    ctx.save()
    return ctx.ok(bag=p["bag"], gem=p["gem"],
                  _temp=ctx.temp(dropList=rewards.to_drop_list(drops), entityCountMap=counts))


@route("logic.playerHandler.spWishBuyTicket")
def sp_wish_buy_ticket(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    times = max(1, int(req.get("times") or 1))
    cost = times * 50
    if int(p.get("gem") or 0) < cost:
        return ctx.err("钻石不足")
    p["gem"] = int(p["gem"]) - cost
    p["costGem"] = int(p.get("costGem") or 0) + cost
    _, bag = add_item_to_bag(p, 341, times)
    ctx.save()
    return ctx.ok(bag=bag, gem=p["gem"],
                  _temp=ctx.temp(entityCountMap={"341": times}, getTicket=times))


@route("logic.playerHandler.updateDiyActivity")
def update_diy_activity(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = _prepare(ctx.player)
    key = str(req.get("key") or "")
    val = req.get("value")
    if key:
        p.setdefault("diyActivity", {})[key] = val
    activity.refresh_activity(p)
    ctx.save()
    return ctx.ok(activity={"map": p["activity"]["map"]}, _temp=ctx.temp())


@prefix_handler("logic.playerHandler.")
def player_fallback(route_name: str, req: dict, session: dict):
    tpl = get_ws_template(route_name)
    if tpl is not None and isinstance(tpl, dict) and tpl.get("code") == 200:
        return tpl
    return {"code": 200, "_temp": {"route": route_name}}
