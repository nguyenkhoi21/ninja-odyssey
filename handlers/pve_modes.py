from core.router import route
from core import gamedata as gd, rewards, tasks
from handlers import common


# ---------- logic.endlessHandler (6/6) ----------

@route("logic.endlessHandler.begin")
def endless_begin(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok()


@route("logic.endlessHandler.pass")
def endless_pass(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    endless = p.setdefault("endless", {"maxFloor": 1, "nowFloor": 1, "topPassId": 0})
    top = int(endless.get("topPassId") or 0)
    if top >= 40000:
        top = 0
    smap_id = req.get("smapId")
    row = gd.smap(int(smap_id)) if smap_id else None
    floor_no = int(row.get("no") or 0) if row else (top + 1)
    if floor_no <= 0:
        floor_no = top + 1
    endless["nowFloor"] = max(int(endless.get("nowFloor") or 1), floor_no) + 1
    endless["maxFloor"] = max(int(endless.get("maxFloor") or 1), endless["nowFloor"])
    endless["topPassId"] = max(top, floor_no)
    counts = rewards.grant_items(p, [{"entityId": 60101, "count": 1}, {"entityId": 101, "count": 1000}])
    ctx.save()
    return ctx.ok(endless=endless, bag=p["bag"], coin=p["coin"], _temp={"isWin": True, "entityCountMap": counts})


@route("logic.endlessHandler.skip")
def endless_skip(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    endless = p.setdefault("endless", {"maxFloor": 1, "nowFloor": 1, "topPassId": 0})
    top = int(endless.get("topPassId") or 0)
    if top >= 40000:
        top = 0
    endless["nowFloor"] = int(endless.get("nowFloor") or 1) + 5
    endless["maxFloor"] = max(int(endless.get("maxFloor") or 1), endless["nowFloor"])
    endless["topPassId"] = max(top, endless["maxFloor"] - 1)
    vip = p.setdefault("vip", {})
    vip["endlessSkipTimes"] = int(vip.get("endlessSkipTimes") or 0) + 1
    counts = rewards.grant_items(p, [{"entityId": 60101, "count": 5}, {"entityId": 101, "count": 10000}])
    ctx.save()
    return ctx.ok(endless=endless, bag=p["bag"], coin=p["coin"], vip={"endlessSkipTimes": vip["endlessSkipTimes"]}, _temp={"entityCountMap": counts})


@route("logic.endlessHandler.buyFruitMapTimes")
def endless_buy_fruit_times(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok()


@route("logic.endlessHandler.setPursuitTeamIndexs")
def endless_set_pursuit(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    endless = ctx.player.setdefault("endless", {})
    bmap_id = str(req.get("bmapId") or "401")
    endless.setdefault("pursuitTeamIndexsMap", {})[bmap_id] = req.get("teamIndexs") or ["1"]
    endless.setdefault("pursuitShipIndexsMap", {})[bmap_id] = req.get("shipIndexs") or []
    ctx.save()
    return ctx.ok(endless=endless)


@route("logic.endlessHandler.resetSetPursuitTeamTimes")
def endless_reset_pursuit(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    endless = ctx.player.setdefault("endless", {})
    bmap_id = str(req.get("bmapId") or "401")
    endless.setdefault("resetTimesMap", {})[bmap_id] = int(endless.get("resetTimesMap", {}).get(bmap_id) or 0) + 1
    ctx.save()
    return ctx.ok(endless=endless)


# ---------- logic.expeditionHandler (4/4) ----------

@route("logic.expeditionHandler.challenge")
def exp_challenge(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    exp = ctx.player.setdefault("expedition", {})
    exp["status"] = 2
    tasks.complete_daily(ctx.player, 2005, complete=True, show="1/1")
    ctx.save()
    return ctx.ok(expedition=exp, task=ctx.player["task"])


@route("logic.expeditionHandler.receive")
def exp_receive(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    exp = ctx.player.setdefault("expedition", {})
    exp["prePassId"] = int(exp.get("passId") or 0)
    exp["passId"] = int(exp.get("passId") or 0) + 1
    exp["status"] = 1
    counts = rewards.grant_items(ctx.player, [{"entityId": 101, "count": 36608}, {"entityId": 49902, "count": 10}])
    ctx.save()
    return ctx.ok(bag=ctx.player["bag"], coin=ctx.player["coin"], expedition=exp, _temp={"entityCountMap": counts})


@route("logic.expeditionHandler.reset")
def exp_reset(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    exp = ctx.player.setdefault("expedition", {})
    exp["passId"] = 0
    exp["prePassId"] = 0
    exp["status"] = 1
    vip = ctx.player.setdefault("vip", {})
    vip["resetExpeditionTimes"] = int(vip.get("resetExpeditionTimes") or 0) + 1
    ctx.save()
    return ctx.ok(vip={"resetExpeditionTimes": vip["resetExpeditionTimes"]}, expedition=exp)


@route("logic.expeditionHandler.skip")
def exp_skip(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    exp = ctx.player.setdefault("expedition", {})
    exp["prePassId"] = int(exp.get("passId") or 0)
    exp["passId"] = int(exp.get("passId") or 0) + 5
    exp["status"] = 1
    counts = rewards.grant_items(ctx.player, [{"entityId": 101, "count": 150000}, {"entityId": 49902, "count": 50}])
    ctx.save()
    return ctx.ok(bag=ctx.player["bag"], coin=ctx.player["coin"], expedition=exp, _temp={"entityCountMap": counts})


# ---------- logic.sixExpeditionHandler (5/5) ----------

@route("logic.sixExpeditionHandler.info")
def six_exp_info(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    se = ctx.player.setdefault("sixExpedition", {"passId": 0, "prePassId": 0, "status": 1})
    return ctx.ok(sixExpedition=se)


@route("logic.sixExpeditionHandler.challenge")
def six_exp_challenge(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    se = ctx.player.setdefault("sixExpedition", {"passId": 0, "prePassId": 0, "status": 1})
    se["status"] = 2 if req.get("isWin", True) else 1
    ctx.save()
    return ctx.ok(sixExpedition=se)


@route("logic.sixExpeditionHandler.receive")
def six_exp_receive(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    se = ctx.player.setdefault("sixExpedition", {"passId": 0, "prePassId": 0, "status": 1})
    se["prePassId"] = int(se.get("passId") or 0)
    se["passId"] = int(se.get("passId") or 0) + 1
    se["status"] = 1
    counts = rewards.grant_items(ctx.player, [{"entityId": 101, "count": 50000}, {"entityId": 49902, "count": 20}])
    ctx.save()
    return ctx.ok(bag=ctx.player["bag"], coin=ctx.player["coin"], sixExpedition=se, _temp={"entityCountMap": counts})


@route("logic.sixExpeditionHandler.reset")
def six_exp_reset(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    se = ctx.player.setdefault("sixExpedition", {})
    se.update({"passId": 0, "prePassId": 0, "status": 1})
    vip = ctx.player.setdefault("vip", {})
    vip["resetSixExpeditionTimes"] = int(vip.get("resetSixExpeditionTimes") or 0) + 1
    ctx.save()
    return ctx.ok(sixExpedition=se, vip={"resetSixExpeditionTimes": vip["resetSixExpeditionTimes"]})


@route("logic.sixExpeditionHandler.skip")
def six_exp_skip(req: dict, session: dict):
    return six_exp_receive(req, session)


# ---------- logic.worldBossHandler (5/5) ----------

@route("logic.worldBossHandler.openInfo")
def wb_open_info(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok(_temp={"bossId": 1, "bossHp": 10000000, "maxHp": 10000000, "isOpen": True})


@route("logic.worldBossHandler.choose")
def wb_choose(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok(_temp={"bossHp": 10000000})


@route("logic.worldBossHandler.challenge")
def wb_challenge(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    counts = rewards.grant_items(ctx.player, [{"entityId": 101, "count": 20000}, {"entityId": 102, "count": 50}])
    ctx.save()
    return ctx.ok(coin=ctx.player["coin"], gem=ctx.player["gem"], _temp={"entityCountMap": counts, "dmg": 100000})


@route("logic.worldBossHandler.inspire")
def wb_inspire(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok(_temp={"inspireTimes": 1})


@route("logic.worldBossHandler.dmgRank")
def wb_dmg_rank(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    return ctx.ok(_temp={"list": [{"playerId": p["id"], "playerName": p["name"], "dmg": 100000, "rank": 1}]})


# ---------- logic.tailHandler (2/2) ----------

@route("logic.tailHandler.choose")
def tail_choose(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok(_temp={"bossHp": 5000000})


@route("logic.tailHandler.challenge")
def tail_challenge(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    vip = ctx.player.setdefault("vip", {})
    vip["tailChallengeTimesTimes"] = int(vip.get("tailChallengeTimesTimes") or 0) + 1
    counts = rewards.grant_items(ctx.player, [{"entityId": 101, "count": 25000}, {"entityId": 102, "count": 50}])
    ctx.save()
    return ctx.ok(coin=ctx.player["coin"], gem=ctx.player["gem"], vip={"tailChallengeTimesTimes": vip["tailChallengeTimesTimes"]}, _temp={"entityCountMap": counts})


# ---------- logic.timePeakHandler (13/13) ----------

@route("logic.timePeakHandler.openMap")
def tp_open_map(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tp = ctx.player.setdefault("timePeak", {})
    bmap_id = int(req.get("bmapId") or 1)
    open_ids = tp.setdefault("openBmapIds", [])
    if bmap_id not in open_ids:
        open_ids.append(bmap_id)
    ctx.save()
    return ctx.ok(timePeak=tp)


@route("logic.timePeakHandler.closeMap")
def tp_close_map(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok(timePeak=ctx.player.get("timePeak", {}))


@route("logic.timePeakHandler.setStatus")
def tp_set_status(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tp = ctx.player.setdefault("timePeak", {})
    sid = str(req.get("smapId") or "101")
    tp.setdefault("statusMap", {})[sid] = req.get("status", 1)
    ctx.save()
    return ctx.ok(timePeak=tp)


@route("logic.timePeakHandler.setExtInfo")
def tp_set_ext_info(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tp = ctx.player.setdefault("timePeak", {})
    tp.setdefault("extInfoMap", {})[str(req.get("key") or "k")] = req.get("value")
    ctx.save()
    return ctx.ok(timePeak=tp)


@route("logic.timePeakHandler.openBox")
def tp_open_box(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tp = ctx.player.setdefault("timePeak", {})
    sid = str(req.get("smapId") or "101")
    tp.setdefault("boxReceivedMap", {})[sid] = True
    counts = rewards.grant_items(ctx.player, [{"entityId": 102, "count": 100}, {"entityId": 101, "count": 20000}])
    ctx.save()
    return ctx.ok(timePeak=tp, coin=ctx.player["coin"], gem=ctx.player["gem"], _temp={"entityCountMap": counts})


@route("logic.timePeakHandler.getBlessing")
def tp_get_blessing(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    rows = [int(r["kindId"]) for r in gd.table("blessingData")[:3] if isinstance(r, dict) and r.get("kindId")]
    return ctx.ok(_temp={"blessingIds": rows or [1, 2, 3]})


@route("logic.timePeakHandler.selectBlessing")
def tp_select_blessing(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tp = ctx.player.setdefault("timePeak", {})
    sid = str(req.get("smapId") or "101")
    bid = req.get("blessingId")
    tp.setdefault("selectBlessingIdsMap", {}).setdefault(sid, []).append(bid)
    ctx.save()
    return ctx.ok(timePeak=tp)


@route("logic.timePeakHandler.altar")
def tp_altar(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tp = ctx.player.setdefault("timePeak", {})
    tp.setdefault("altarMap", {})[str(req.get("smapId") or "101")] = True
    ctx.save()
    return ctx.ok(timePeak=tp)


@route("logic.timePeakHandler.spa")
def tp_spa(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok(timePeak=ctx.player.get("timePeak", {}))


@route("logic.timePeakHandler.borrowRole")
def tp_borrow_role(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok(timePeak=ctx.player.get("timePeak", {}))


@route("logic.timePeakHandler.challenge")
def tp_challenge(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    counts = rewards.grant_items(ctx.player, [{"entityId": 101, "count": 10000}])
    ctx.save()
    return ctx.ok(coin=ctx.player["coin"], _temp={"isWin": bool(req.get("isWin", True)), "entityCountMap": counts})


@route("logic.timePeakHandler.updateBattleInfo")
def tp_update_battle(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tp = ctx.player.setdefault("timePeak", {})
    for sid in req.get("winSmapIds") or []:
        tp.setdefault("statusMap", {})[str(sid)] = 2
    ctx.save()
    return ctx.ok(timePeak=tp)


@route("logic.timePeakHandler.recordLog")
def tp_record_log(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok()
