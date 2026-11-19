from core.router import route
from core import gamedata as gd, rewards, schema, tasks
from handlers import common

DEFAULT_BOTS = [
    {"playerId": 5600, "playerName": "佳乃·山室", "playerLevel": 10, "photoImgId": 1022, "totalPower": 3285, "rank": 5600},
    {"playerId": 6714, "playerName": "将门·相马", "playerLevel": 10, "photoImgId": 1008, "totalPower": 3510, "rank": 6714},
    {"playerId": 7539, "playerName": "万次郎·水月", "playerLevel": 10, "photoImgId": 1017, "totalPower": 3285, "rank": 7539},
    {"playerId": 9948, "playerName": "明·生野", "playerLevel": 10, "photoImgId": 1030, "totalPower": 3285, "rank": 9948},
]


def _bot_roles(level: int = 10):
    roles = []
    for kid in (100801, 100601, 100501):
        r = schema.make_role(kid, level=level, star=1)
        roles.append(r)
    return roles


def _player_battle_team(player: dict, team_idxs=None, rank: int = 10001):
    roles_dict = (player.get("team") or {}).get("roles") or {}
    idxs = team_idxs or (player.get("arena") or {}).get("defenseTeamIndexs") or (player.get("team") or {}).get("indexs") or ["1"]
    team_roles = []
    for i in idxs:
        if str(i) == "0":
            continue
        r = roles_dict.get(str(i))
        if isinstance(r, dict):
            schema.ensure_role_fields(r)
            team_roles.append(r)
    if not team_roles and roles_dict:
        team_roles = [next(iter(roles_dict.values()))]
    return {
        "userId": player.get("userId", 0),
        "sid": player.get("sid", "connector-server-1"),
        "serverId": player.get("serverId", 1),
        "playerId": player["id"],
        "playerPhotoInfo": player.get("photoInfo", {"photoImgId": 1003, "shipImgId": 900}),
        "rank": rank,
        "playerName": player.get("name", "Ninja"),
        "playerLevel": player.get("level", 1),
        "guildName": player.get("guildName"),
        "guildId": player.get("guildId", 0),
        "ships": [],
        "roles": team_roles,
    }


def _defense_team_for(db: dict, target_id, rank: int = 6714):
    real = db.get("players", {}).get(str(target_id))
    if real:
        return _player_battle_team(real, rank=real.get("arena", {}).get("rank", rank))
    bot = next((b for b in DEFAULT_BOTS if str(b["playerId"]) == str(target_id)), DEFAULT_BOTS[1])
    return {
        "playerId": int(target_id) if str(target_id).isdigit() else bot["playerId"],
        "serverId": 1,
        "playerPhotoInfo": {"photoImgId": bot["photoImgId"], "shipImgId": 900},
        "rank": bot["rank"],
        "playerName": bot["playerName"],
        "playerLevel": bot["playerLevel"],
        "ships": [],
        "roles": _bot_roles(bot["playerLevel"]),
    }


def _match_entry(bot: dict):
    return {
        "playerId": bot["playerId"],
        "playerName": bot["playerName"],
        "playerLevel": bot["playerLevel"],
        "playerPhotoInfo": {"photoImgId": bot["photoImgId"], "shipImgId": 900},
        "totalPower": bot["totalPower"],
        "rank": bot["rank"],
    }


# ---------- logic.arenaHandler (10/10) ----------

@route("logic.arenaHandler.info")
def arena_info(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    arena = ctx.player.setdefault("arena", {})
    return ctx.ok(_temp={"rank": arena.get("rank", 10001)})


@route("logic.arenaHandler.match")
def arena_match(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    return ctx.ok(_temp={
        "smaller": _match_entry(DEFAULT_BOTS[0]),
        "middle": _match_entry(DEFAULT_BOTS[2]),
        "larger": _match_entry(DEFAULT_BOTS[3]),
    })


@route("logic.arenaHandler.defenseTeam")
def arena_defense_team(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tid = req.get("playerId") or ctx.player["id"]
    dt = _defense_team_for(ctx.db, tid)
    return ctx.ok(_temp={"_decodeKeys": ["defenseTeam"], "defenseTeam": dt})


@route("logic.arenaHandler.choose")
def arena_choose(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    def_id = req.get("defenderId") or 6714
    atk_team = _player_battle_team(ctx.player, req.get("attackTeamIndexs"), ctx.player.get("arena", {}).get("rank", 10001))
    def_team = _defense_team_for(ctx.db, def_id)
    return ctx.ok(_temp={
        "_decodeKeys": ["attackTeam", "defenseTeam"],
        "attackTeam": atk_team,
        "defenseTeam": def_team,
    })


@route("logic.arenaHandler.challenge")
def arena_challenge(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    arena = p.setdefault("arena", {})
    is_win = bool(req.get("isWin", True))
    arena["challengeTimes"] = int(arena.get("challengeTimes") or 0) + 1
    arena["remainingChallengeTimes"] = max(0, int(arena.get("remainingChallengeTimes") or 5) - 1)
    arena["nextChallengeTime"] = common.now_ms() + 300000
    if is_win:
        arena["winTimes"] = int(arena.get("winTimes") or 0) + 1
        cur_rank = int(arena.get("rank") or 10001)
        new_rank = max(1, min(cur_rank, 6714 if cur_rank > 6714 else cur_rank - 1))
        arena["rank"] = new_rank
        arena["topRank"] = min(int(arena.get("topRank") or cur_rank), new_rank)
        rewards.grant_items(p, [{"entityId": 102, "count": 50}, {"entityId": 101, "count": 5000}])
    tasks.complete_daily(p, 2004, complete=True, show="1/1")
    rep_id = int(ctx.db.get("next_report_id", 1082119))
    ctx.db["next_report_id"] = rep_id + 1
    reports = ctx.db.setdefault("arena_reports", {}).setdefault(str(p["id"]), [])
    reports.insert(0, {
        "id": rep_id,
        "isWin": is_win,
        "targetId": req.get("defenderId", 6714),
        "targetName": "将门·相马",
        "rank": arena.get("rank", 10001),
        "ctime": common.now_ms(),
    })
    del reports[20:]
    ctx.save()
    return ctx.ok(
        gem=p["gem"],
        coin=p["coin"],
        arena=arena,
        task=p.get("task", {}),
        _temp={"isWin": is_win, "rank": arena.get("rank", 10001), "reportId": rep_id},
    )


@route("logic.arenaHandler.reportList")
def arena_reports(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    reports = ctx.db.get("arena_reports", {}).get(str(ctx.player["id"]), [])
    return ctx.ok(_temp={"list": reports})


@route("logic.arenaHandler.report")
def arena_report_detail(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    return ctx.ok(_temp={"report": {"id": req.get("id", 1), "isWin": True, "records": []}})


@route("logic.arenaHandler.setDefenseTeamIndexs")
def arena_set_defense(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    arena = ctx.player.setdefault("arena", {})
    arena["defenseTeamIndexs"] = req.get("defenseTeamIndexs") or ["1"]
    arena["defenseShipIndexs"] = req.get("defenseShipIndexs") or []
    ctx.save()
    return ctx.ok(arena=arena)


@route("logic.arenaHandler.buyChallengeTimes")
def arena_buy_times(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    arena = ctx.player.setdefault("arena", {})
    arena["remainingChallengeTimes"] = int(arena.get("remainingChallengeTimes") or 0) + 5
    vip = ctx.player.setdefault("vip", {})
    vip["buyChallengeTimesTimes"] = int(vip.get("buyChallengeTimesTimes") or 0) + 1
    ctx.save()
    return ctx.ok(arena=arena, vip={"buyChallengeTimesTimes": vip["buyChallengeTimesTimes"]})


@route("logic.arenaHandler.cancelCD")
def arena_cancel_cd(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    arena = ctx.player.setdefault("arena", {})
    arena["nextChallengeTime"] = 0
    ctx.save()
    return ctx.ok(arena=arena)


# ---------- logic.arena3v3Handler (13/13) ----------

@route("logic.arena3v3Handler.info")
def arena3v3_info(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    a3 = ctx.player.setdefault("arena3v3", {})
    return ctx.ok(arena3v3=a3, _temp={"rank": a3.get("rank", 10001)})


@route("logic.arena3v3Handler.match")
def arena3v3_match(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    return ctx.ok(_temp={"list": [_match_entry(b) for b in DEFAULT_BOTS[:3]]})


@route("logic.arena3v3Handler.defenseTeam")
def arena3v3_defense_team(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    dt = _defense_team_for(ctx.db, req.get("playerId") or ctx.player["id"])
    return ctx.ok(_temp={"_decodeKeys": ["defenseTeam"], "defenseTeam": dt})


@route("logic.arena3v3Handler.choose")
def arena3v3_choose(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    atk = _player_battle_team(ctx.player)
    dfd = _defense_team_for(ctx.db, req.get("defenderId") or 6714)
    return ctx.ok(_temp={"_decodeKeys": ["attackTeam", "defenseTeam"], "attackTeam": atk, "defenseTeam": dfd})


@route("logic.arena3v3Handler.challenge")
def arena3v3_challenge(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    a3 = ctx.player.setdefault("arena3v3", {})
    a3["challengeTimes"] = max(0, int(a3.get("challengeTimes") or 5) - 1)
    a3["score"] = int(a3.get("score") or 0) + 100
    a3["rank"] = max(1, int(a3.get("rank") or 10001) - 10)
    rewards.grant_items(ctx.player, [{"entityId": 101, "count": 5000}])
    ctx.save()
    return ctx.ok(arena3v3=a3, coin=ctx.player["coin"], _temp={"isWin": bool(req.get("isWin", True)), "rank": a3["rank"]})


@route("logic.arena3v3Handler.reportList")
def arena3v3_report_list(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok(_temp={"list": []})


@route("logic.arena3v3Handler.setDefenseTeamIndexsMap")
def arena3v3_set_defense(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    a3 = ctx.player.setdefault("arena3v3", {})
    a3["defenseTeamIndexsMap"] = req.get("defenseTeamIndexsMap") or {}
    a3["defenseShipIndexsMap"] = req.get("defenseShipIndexsMap") or {}
    ctx.save()
    return ctx.ok(arena3v3=a3)


@route("logic.arena3v3Handler.buyChallengeTimes")
def arena3v3_buy_times(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    a3 = ctx.player.setdefault("arena3v3", {})
    a3["challengeTimes"] = int(a3.get("challengeTimes") or 0) + 5
    ctx.save()
    return ctx.ok(arena3v3=a3)


@route("logic.arena3v3Handler.cancelCD")
def arena3v3_cancel_cd(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok()


@route("logic.arena3v3Handler.receive")
def arena3v3_receive(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    counts = rewards.grant_items(ctx.player, [{"entityId": 101, "count": 10000}])
    ctx.save()
    return ctx.ok(coin=ctx.player["coin"], _temp={"entityCountMap": counts})


@route("logic.arena3v3Handler.top50")
def arena3v3_top50(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    rows = [{"playerId": p["id"], "playerName": p["name"], "playerLevel": p["level"], "playerPhotoInfo": p.get("photoInfo", {}), "rank": 1, "value": p.get("power", 1000)}]
    return ctx.ok(_temp={"_decodeKeys": ["list"], "list": rows, "myRank": 1})


@route("logic.arena3v3Handler.worshipRank")
def arena3v3_worship_rank(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok(_temp={"list": []})


@route("logic.arena3v3Handler.worshipStatue")
def arena3v3_worship_statue(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    vip = ctx.player.setdefault("vip", {})
    vip["worshipStatue3v3Times"] = int(vip.get("worshipStatue3v3Times") or 0) + 1
    counts = rewards.grant_items(ctx.player, [{"entityId": 102, "count": 50}])
    ctx.save()
    return ctx.ok(gem=ctx.player["gem"], vip={"worshipStatue3v3Times": vip["worshipStatue3v3Times"]}, _temp={"entityCountMap": counts})


# ---------- logic.topArena3v3Handler (11/11) ----------

@route("logic.topArena3v3Handler.info")
def top3v3_info(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    ta = ctx.player.setdefault("topArena3v3", {})
    return ctx.ok(topArena3v3=ta, _temp={"rank": ta.get("rank", 1), "topInfoMap": ta.get("topInfoMap", {})})


@route("logic.topArena3v3Handler.match")
def top3v3_match(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok(_temp={"list": [_match_entry(b) for b in DEFAULT_BOTS[:3]]})


@route("logic.topArena3v3Handler.defenseTeam")
def top3v3_defense_team(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    dt = _defense_team_for(ctx.db, req.get("playerId") or ctx.player["id"])
    return ctx.ok(_temp={"_decodeKeys": ["defenseTeam"], "defenseTeam": dt})


@route("logic.topArena3v3Handler.choose")
def top3v3_choose(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    return ctx.ok(_temp={
        "_decodeKeys": ["attackTeam", "defenseTeam"],
        "attackTeam": _player_battle_team(ctx.player),
        "defenseTeam": _defense_team_for(ctx.db, req.get("defenderId") or 6714),
    })


@route("logic.topArena3v3Handler.challenge")
@route("logic.topArena3v3Handler.challengeTop")
@route("logic.topArena3v3Handler.challengeTopNull")
def top3v3_challenge(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    ta = ctx.player.setdefault("topArena3v3", {})
    ta["score"] = int(ta.get("score") or 0) + 100
    ta["rank"] = int(req.get("no") or ta.get("rank") or 1) or 1
    counts = rewards.grant_items(ctx.player, [{"entityId": 102, "count": 50}])
    ctx.save()
    return ctx.ok(topArena3v3=ta, gem=ctx.player["gem"], _temp={"isWin": bool(req.get("isWin", True)), "entityCountMap": counts})


@route("logic.topArena3v3Handler.reportList")
def top3v3_report_list(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok(_temp={"list": []})


@route("logic.topArena3v3Handler.setDefenseTeamIndexsMap")
def top3v3_set_defense(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    ta = ctx.player.setdefault("topArena3v3", {})
    ta["defenseTeamIndexsMap"] = req.get("defenseTeamIndexsMap") or {}
    ta["defenseShipIndexsMap"] = req.get("defenseShipIndexsMap") or {}
    ctx.save()
    return ctx.ok(topArena3v3=ta)


@route("logic.topArena3v3Handler.buyMatchTimes")
def top3v3_buy_times(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok()


@route("logic.topArena3v3Handler.receiveFirstReachReward")
def top3v3_first_reward(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    counts = rewards.grant_items(ctx.player, [{"entityId": 102, "count": 300}])
    ctx.save()
    return ctx.ok(gem=ctx.player["gem"], _temp={"entityCountMap": counts})
