from core.router import route
from core import gamedata as gd, rewards, schema, tasks
from handlers import common


def _smap_rewards(srow: dict, times: int = 1):
    items = []
    if srow:
        desc = srow.get("dropListDesc") or srow.get("firstDropListDesc")
        if desc:
            items.extend(rewards.parse_drop_desc(desc))
        for eid in srow.get("specifyDropEntityIds") or []:
            if eid:
                items.append({"entityId": int(eid), "count": 2})
    if not items:
        items = [{"entityId": 42102, "count": 2}, {"entityId": 42202, "count": 2}]
    if times > 1:
        for it in items:
            it["count"] = int(it.get("count") or 1) * times
    return items


@route("logic.smapHandler.beginSmap")
def begin_smap(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    smap_id = int(req.get("smapId") or ctx.player.get("smap", {}).get("nowId") or 10101)
    session["active_smap_id"] = smap_id
    return ctx.ok(_temp={"showEntityIdsMap": {}})


@route("logic.smapHandler.endSmap")
def end_smap(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    smap_id = int(req.get("smapId") or session.get("active_smap_id") or p.get("smap", {}).get("nowId") or 10101)
    star = max(1, min(3, int(req.get("star") or 3)))
    srow = gd.smap(smap_id) or {}

    coin_add = int(srow.get("coin") or 1200)
    role_exp = int(srow.get("roleExp") or 20)
    ap_cost = int(srow.get("actionPoint") or 6)
    p["actionPoint"] = max(0, int(p.get("actionPoint") or 0) - ap_cost)
    p["coin"] = int(p.get("coin") or 0) + coin_add
    common.add_player_exp(ctx, role_exp)

    team_idxs = req.get("teamIndexs") or p.get("team", {}).get("indexs") or ["1"]
    updated_roles = {}
    for tidx in team_idxs:
        if str(tidx) == "0":
            continue
        r = common.role_of(p, str(tidx))
        if r:
            common.add_role_exp(r, role_exp, max_level=max(100, int(p.get("level") or 1)))
            schema.refresh_role(r)
            updated_roles[str(tidx)] = r

    star_map = p.setdefault("smapStarMap", {})
    prev_star = int(star_map.get(str(smap_id)) or 0)
    if star > prev_star:
        star_map[str(smap_id)] = star
        p["starCount"] = sum(int(v or 0) for v in star_map.values())

    times_map = p.setdefault("smapTimesMap", {})
    times_map[str(smap_id)] = int(times_map.get(str(smap_id)) or 0) + 1

    smap_obj = p.setdefault("smap", {"nowId": 10101, "maxId": 10101})
    if smap_id >= int(smap_obj.get("maxId") or 10101):
        smap_obj["nowId"] = smap_id + 1
        smap_obj["maxId"] = smap_id + 1

    items = _smap_rewards(srow, times=1)
    counts = rewards.grant_items(p, items)
    schema.recalc_power(p)
    tasks.complete_daily(p, 2001)
    ctx.save()
    return ctx.ok(
        team={**p["team"], "roles": updated_roles} if updated_roles else p["team"],
        bag=p["bag"],
        coin=p["coin"],
        experience=p["experience"],
        level=p["level"],
        actionPoint=p["actionPoint"],
        smap=smap_obj,
        smapStarMap={str(smap_id): star_map[str(smap_id)]},
        smapTimesMap={str(smap_id): times_map[str(smap_id)]},
        starCount=p.get("starCount", 0),
        _temp={"entityCountMap": counts, "isWin": True, "star": star},
    )


@route("logic.smapHandler.skip")
def skip_smap(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    smap_id = int(req.get("smapId") or 10101)
    times = max(1, int(req.get("times") or 1))
    srow = gd.smap(smap_id) or {}
    coin_add = int(srow.get("coin") or 1200) * times
    p["coin"] = int(p.get("coin") or 0) + coin_add
    common.add_player_exp(ctx, int(srow.get("roleExp") or 20) * times)
    times_map = p.setdefault("smapTimesMap", {})
    times_map[str(smap_id)] = int(times_map.get(str(smap_id)) or 0) + times
    items = _smap_rewards(srow, times=times)
    counts = rewards.grant_items(p, items)
    schema.recalc_power(p)
    ctx.save()
    return ctx.ok(
        bag=p["bag"],
        coin=p["coin"],
        experience=p["experience"],
        level=p["level"],
        smapTimesMap={str(smap_id): times_map[str(smap_id)]},
        _temp={"entityCountMap": counts},
    )


@route("logic.smapHandler.skipAll")
def skip_all_smap(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    bmap_id = int(req.get("bmapId") or 101)
    smaps = gd.smaps_of_bmap(bmap_id)
    first_id = int(smaps[0]["kindId"]) if smaps else 10101
    return skip_smap({"smapId": first_id, "times": 5}, session)


@route("logic.smapHandler.receiveBmapAward")
def receive_bmap_award(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    bmap_id = int(req.get("bmapId") or 101)
    star = str(req.get("star") or "6")
    brow = gd.bmap(bmap_id) or {}
    box_desc = brow.get("box3") or brow.get("box2") or brow.get("box1") or "102x200,101x20000"
    items = rewards.parse_drop_desc(box_desc)
    counts = rewards.grant_items(p, items)
    p.setdefault("bmapBoxReceivedMap", {}).setdefault(str(bmap_id), {})[star] = True
    ctx.save()
    return ctx.ok(
        bag=p["bag"],
        coin=p["coin"],
        gem=p["gem"],
        bmapBoxReceivedMap=p["bmapBoxReceivedMap"],
        _temp={"entityCountMap": counts},
    )


@route("logic.smapHandler.buyMapType5Times")
def buy_map_type5_times(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    vip = ctx.player.setdefault("vip", {})
    vip["buyMapType5Times"] = int(vip.get("buyMapType5Times") or 0) + 1
    ctx.save()
    return ctx.ok(vip={"buyMapType5Times": vip["buyMapType5Times"]})


@route("logic.smapHandler.resetSmapTimes")
def reset_smap_times(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    sid = str(req.get("smapId") or "10101")
    tmap = ctx.player.setdefault("smapTimesMap", {})
    tmap[sid] = 0
    vip = ctx.player.setdefault("vip", {})
    rmap = vip.setdefault("resetSmapTimesTimesMap", {})
    rmap[sid] = int(rmap.get(sid) or 0) + 1
    ctx.save()
    return ctx.ok(smapTimesMap={sid: 0}, vip={"resetSmapTimesTimesMap": rmap})


@route("logic.smapHandler.resetAllSmapTimes")
def reset_all_smap_times(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    bmap_id = int(req.get("bmapId") or 101)
    tmap = ctx.player.setdefault("smapTimesMap", {})
    for r in gd.smaps_of_bmap(bmap_id):
        sid = str(r.get("kindId"))
        if sid in tmap:
            tmap[sid] = 0
    ctx.save()
    return ctx.ok(smapTimesMap=tmap)
