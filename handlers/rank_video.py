from core.router import route
from handlers import common


@route("logic.rankHandler.top50")
def rank_top50(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    rtype = req.get("type") or "totalPower"
    players = list(ctx.db.get("players", {}).values())
    if rtype == "level":
        players.sort(key=lambda x: int(x.get("level") or 0), reverse=True)
    else:
        players.sort(key=lambda x: int(x.get("topPower") or x.get("power") or 0), reverse=True)

    rows = []
    my_rank = 1
    my_val = p.get("topPower", p.get("power", 1014))
    for i, pl in enumerate(players[:50], 1):
        val = int(pl.get("level") or 1) if rtype == "level" else int(pl.get("topPower") or pl.get("power") or 0)
        if pl.get("id") == p["id"]:
            my_rank = i
            my_val = val
        rows.append({
            "playerId": pl["id"],
            "playerName": pl.get("name", "Ninja"),
            "playerLevel": pl.get("level", 1),
            "playerPhotoInfo": pl.get("photoInfo", {"photoImgId": 1003, "shipImgId": 900}),
            "rank": i,
            "value": val,
        })
    return ctx.ok(_temp={"_decodeKeys": ["list"], "myRank": my_rank, "myValue": my_val, "list": rows})


@route("logic.rankHandler.arenaTop50")
def rank_arena_top50(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    players = sorted(ctx.db.get("players", {}).values(), key=lambda x: int((x.get("arena") or {}).get("rank") or 10001))
    rows = []
    for i, pl in enumerate(players[:50], 1):
        r = int((pl.get("arena") or {}).get("rank") or i)
        rows.append({
            "playerId": pl["id"],
            "playerName": pl.get("name", "Ninja"),
            "playerLevel": pl.get("level", 1),
            "playerPhotoInfo": pl.get("photoInfo", {"photoImgId": 1003, "shipImgId": 900}),
            "rank": i,
            "value": r,
        })
    return ctx.ok(_temp={"_decodeKeys": ["list"], "myRank": 1, "myValue": (p.get("arena") or {}).get("rank", 10001), "list": rows})


# ---------- logic.videoHandler (7/7) ----------

@route("logic.videoHandler.getVideoList")
def video_list(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    vids = list(ctx.db.get("videos", {}).values())
    return ctx.ok(_temp={"list": vids})


@route("logic.videoHandler.getMyVideoList")
def video_my_list(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    vids = [v for v in ctx.db.get("videos", {}).values() if v.get("playerId") == ctx.player["id"]]
    return ctx.ok(_temp={"list": vids})


@route("logic.videoHandler.shareVideo")
def video_share(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    vid = int(ctx.db.get("next_video_id", 1))
    ctx.db["next_video_id"] = vid + 1
    entry = {
        "videoId": vid,
        "reportId": req.get("reportId", vid),
        "desc": req.get("desc", ""),
        "playerId": ctx.player["id"],
        "playerName": ctx.player.get("name", "Ninja"),
        "supportCount": 0,
        "ctime": common.now_ms(),
    }
    ctx.db.setdefault("videos", {})[str(vid)] = entry
    ctx.save()
    return ctx.ok(_temp={"video": entry})


@route("logic.videoHandler.removeVideo")
def video_remove(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    vid = str(req.get("videoId") or "")
    ctx.db.get("videos", {}).pop(vid, None)
    ctx.save()
    return ctx.ok()


@route("logic.videoHandler.serachVideo")
def video_search(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    vid = str(req.get("videoId") or "")
    v = ctx.db.get("videos", {}).get(vid)
    return ctx.ok(_temp={"list": [v] if v else []})


@route("logic.videoHandler.supportVideo")
def video_support(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    vid = str(req.get("videoId") or "")
    v = ctx.db.get("videos", {}).get(vid)
    if v:
        v["supportCount"] = int(v.get("supportCount") or 0) + 1
        ctx.save()
    return ctx.ok()


@route("logic.videoHandler.viewVideo")
def video_view(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    return ctx.ok(_temp={"report": {"id": req.get("reportId", 1), "records": []}})
