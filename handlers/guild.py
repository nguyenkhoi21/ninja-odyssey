from core.router import route
from core import rewards, schema, tasks
from handlers import common


def _ensure_guild(db: dict, p: dict):
    guilds = db.setdefault("guilds", {})
    gid = p.get("guildId", 0)
    if gid and str(gid) in guilds:
        return guilds[str(gid)]
    default_gid = 11187
    if str(default_gid) not in guilds:
        guilds[str(default_gid)] = {
            "id": default_gid,
            "serverId": p.get("serverId", 1),
            "name": p.get("guildName") or "oke",
            "badgeId": 1,
            "chairmanId": p["id"],
            "chairmanName": p["name"],
            "chairmanAtime": common.now_ms(),
            "viceChairmanIds": [],
            "memberIds": [p["id"]],
            "applyIds": [],
            "notice": "Welcome!",
            "activePoint": 7640,
            "joinLevelLimit": 1,
            "joinRequireType": 1,
            "level": 1,
            "maxMemberCount": 25,
            "drumTimes": 0,
            "openBoxTimes": 0,
        }
    return guilds[str(default_gid)]


# ---------- logic.guildHandler (18/18) ----------

@route("logic.guildHandler.create")
def guild_create(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    gid = int(ctx.db.get("next_guild_id", 11188))
    ctx.db["next_guild_id"] = gid + 1
    gname = req.get("name") or f"Konoha_{gid}"
    g = {
        "id": gid,
        "serverId": p.get("serverId", 1),
        "name": gname,
        "badgeId": req.get("badgeId", 1),
        "chairmanId": p["id"],
        "chairmanName": p["name"],
        "chairmanAtime": common.now_ms(),
        "viceChairmanIds": [],
        "memberIds": [p["id"]],
        "applyIds": [],
        "notice": "",
        "activePoint": 0,
        "joinLevelLimit": 1,
        "joinRequireType": 1,
        "level": 1,
        "maxMemberCount": 25,
        "drumTimes": 0,
        "openBoxTimes": 0,
    }
    ctx.db.setdefault("guilds", {})[str(gid)] = g
    p["guildId"] = gid
    p["guildName"] = gname
    ctx.save()
    return ctx.ok(guildId=gid, guildName=gname, guild=g)


@route("logic.guildHandler.info")
def guild_info(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    g = _ensure_guild(ctx.db, p)
    p["guildId"] = g["id"]
    p["guildName"] = g["name"]
    if p["id"] not in g.setdefault("memberIds", []):
        g["memberIds"].append(p["id"])
    ctx.save()
    return ctx.ok(guild=g)


@route("logic.guildHandler.list")
def guild_list(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    _ensure_guild(ctx.db, ctx.player)
    glist = []
    for g in ctx.db.get("guilds", {}).values():
        glist.append({
            "id": g["id"],
            "name": g["name"],
            "badgeId": g.get("badgeId", 1),
            "chairmanName": g.get("chairmanName", ""),
            "activePoint": g.get("activePoint", 0),
            "joinLevelLimit": g.get("joinLevelLimit", 1),
            "joinRequireType": g.get("joinRequireType", 1),
            "menberCount": len(g.get("memberIds", [])),
            "level": g.get("level", 1),
            "maxMemberCount": g.get("maxMemberCount", 25),
        })
    return ctx.ok(_temp={"_decodeKeys": ["list"], "list": glist})


@route("logic.guildHandler.applyJoin")
def guild_apply_join(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    gid = str(req.get("guildId") or "11187")
    g = ctx.db.get("guilds", {}).get(gid) or _ensure_guild(ctx.db, ctx.player)
    if ctx.player["id"] not in g.setdefault("memberIds", []):
        g["memberIds"].append(ctx.player["id"])
    ctx.player["guildId"] = g["id"]
    ctx.player["guildName"] = g["name"]
    ctx.save()
    return ctx.ok(guildId=g["id"], guildName=g["name"], guild=g)


@route("logic.guildHandler.handleApply")
def guild_handle_apply(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    g = _ensure_guild(ctx.db, ctx.player)
    tid = req.get("targetId")
    if tid in g.get("applyIds", []):
        g["applyIds"].remove(tid)
    if req.get("isAgree") and tid and tid not in g.get("memberIds", []):
        g.setdefault("memberIds", []).append(tid)
    ctx.save()
    return ctx.ok(guild=g)


@route("logic.guildHandler.addViceChairman")
def guild_add_vice(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    g = _ensure_guild(ctx.db, ctx.player)
    tid = req.get("targetId")
    v = g.setdefault("viceChairmanIds", [])
    if tid and tid not in v:
        v.append(tid)
    ctx.save()
    return ctx.ok(guild=g)


@route("logic.guildHandler.removeViceChairman")
def guild_remove_vice(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    g = _ensure_guild(ctx.db, ctx.player)
    tid = req.get("targetId")
    v = g.setdefault("viceChairmanIds", [])
    if tid in v:
        v.remove(tid)
    ctx.save()
    return ctx.ok(guild=g)


@route("logic.guildHandler.changeChairman")
def guild_change_chairman(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    g = _ensure_guild(ctx.db, ctx.player)
    g["chairmanId"] = req.get("targetId", ctx.player["id"])
    g["chairmanName"] = req.get("targetName", ctx.player["name"])
    ctx.save()
    return ctx.ok(guild=g)


@route("logic.guildHandler.inherit")
def guild_inherit(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    g = _ensure_guild(ctx.db, ctx.player)
    g["chairmanId"] = ctx.player["id"]
    g["chairmanName"] = ctx.player["name"]
    ctx.save()
    return ctx.ok(guild=g)


@route("logic.guildHandler.modifyNotice")
def guild_modify_notice(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    g = _ensure_guild(ctx.db, ctx.player)
    g["notice"] = str(req.get("notice") or "")
    ctx.save()
    return ctx.ok(guild={"notice": g["notice"]})


@route("logic.guildHandler.modifySetting")
def guild_modify_setting(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    g = _ensure_guild(ctx.db, ctx.player)
    for k_req, k_g in (("badgeId", "badgeId"), ("guildName", "name"), ("joinRequireType", "joinRequireType"), ("joinLevelLimit", "joinLevelLimit")):
        if req.get(k_req) is not None:
            g[k_g] = req[k_req]
    ctx.player["guildName"] = g["name"]
    ctx.save()
    return ctx.ok(guild=g, guildName=g["name"])


@route("logic.guildHandler.drum")
def guild_drum(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    g = _ensure_guild(ctx.db, p)
    g["activePoint"] = int(g.get("activePoint") or 0) + 50
    g["drumTimes"] = int(g.get("drumTimes") or 0) + 1
    counts = rewards.grant_items(p, [{"entityId": 107, "count": 300}])
    ctx.save()
    return ctx.ok(
        guild={"activePoint": g["activePoint"], "drumTimes": g["drumTimes"], "level": g.get("level", 1), "maxMemberCount": g.get("maxMemberCount", 25)},
        bag=p["bag"],
        gem=p["gem"],
        costGem=p.get("costGem", 0),
        _temp={"entityCountMap": counts},
    )


@route("logic.guildHandler.openBox")
def guild_open_box(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    g = _ensure_guild(ctx.db, p)
    g["openBoxTimes"] = int(g.get("openBoxTimes") or 0) + 1
    g["activePoint"] = int(g.get("activePoint") or 0) + 5
    counts = rewards.grant_items(p, [{"entityId": 101, "count": 30000}])
    ctx.save()
    return ctx.ok(guild={"openBoxTimes": g["openBoxTimes"], "activePoint": g["activePoint"]}, coin=p["coin"], _temp={"entityCountMap": counts})


@route("logic.guildHandler.upgradeSkill")
def guild_upgrade_skill(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    stype = str(req.get("type") or "ATK").upper()
    gs = p.setdefault("guildSkill", {"levelMap": {"HP": 0, "ATK": 0, "DEF": 0, "MDEF": 0}, "attr": {"hp": 0, "atk": 0, "def": 0, "mdef": 0}})
    gs["levelMap"][stype] = int(gs["levelMap"].get(stype) or 0) + 1
    ak = stype.lower()
    gs["attr"][ak] = int(gs["attr"].get(ak) or 0) + (100 if ak == "hp" else 10)
    tasks.complete_daily(p, 2016)
    schema.recalc_power(p)
    ctx.save()
    return ctx.ok(bag=p["bag"], guildSkill=gs, power=p["power"], task=p["task"])


@route("logic.guildHandler.worship")
def guild_worship(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    counts = rewards.grant_items(ctx.player, [{"entityId": 101, "count": 10000}, {"entityId": 99, "count": 20}])
    ctx.save()
    return ctx.ok(actionPoint=ctx.player["actionPoint"], coin=ctx.player["coin"], _temp={"entityCountMap": counts})


@route("logic.guildHandler.receiveWorshipAward")
def guild_receive_worship_award(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    counts = rewards.grant_items(ctx.player, [{"entityId": 101, "count": 20000}, {"entityId": 102, "count": 100}])
    ctx.save()
    return ctx.ok(coin=ctx.player["coin"], gem=ctx.player["gem"], _temp={"entityCountMap": counts})


@route("logic.guildHandler.exit")
@route("logic.guildHandler.dismiss")
def guild_exit(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    gid = str(p.get("guildId") or "")
    if gid in ctx.db.get("guilds", {}):
        g = ctx.db["guilds"][gid]
        if p["id"] in g.get("memberIds", []):
            g["memberIds"].remove(p["id"])
    p["guildId"] = 0
    p["guildName"] = None
    ctx.save()
    return ctx.ok(guildId=0, guildName=None)


# ---------- logic.guildBossHandler (4/4) ----------

@route("logic.guildBossHandler.openInfo")
def gboss_open_info(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    return ctx.ok(_temp={"bossId": 1, "bossHp": 1000000, "maxHp": 1000000, "challengeTimes": 3})


@route("logic.guildBossHandler.choose")
def gboss_choose(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok(_temp={"bossHp": 1000000})


@route("logic.guildBossHandler.challenge")
def gboss_challenge(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    counts = rewards.grant_items(ctx.player, [{"entityId": 101, "count": 20000}, {"entityId": 107, "count": 200}])
    ctx.save()
    return ctx.ok(bag=ctx.player["bag"], coin=ctx.player["coin"], _temp={"entityCountMap": counts, "dmg": 50000})


@route("logic.guildBossHandler.dmgRank")
def gboss_dmg_rank(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    return ctx.ok(_temp={"list": [{"playerId": p["id"], "playerName": p["name"], "dmg": 50000, "rank": 1}]})


# ---------- logic.guildBattleHandler (10/10) ----------

@route("logic.guildBattleHandler.openInfo")
def gb_open_info(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    return ctx.ok(_temp={"openInfo": {"openTime": common.now_ms() + 3600000, "isOpen": False}})


@route("logic.guildBattleHandler.enter")
@route("logic.guildBattleHandler.exit")
@route("logic.guildBattleHandler.move")
@route("logic.guildBattleHandler.beginBattle")
@route("logic.guildBattleHandler.recover")
def gb_basic(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok()


@route("logic.guildBattleHandler.getTeam")
def gb_get_team(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok(_temp={"team": ctx.player["team"]})


@route("logic.guildBattleHandler.endBattle")
def gb_end_battle(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    counts = rewards.grant_items(ctx.player, [{"entityId": 101, "count": 10000}])
    ctx.save()
    return ctx.ok(coin=ctx.player["coin"], _temp={"isWin": bool(req.get("isWin", True)), "entityCountMap": counts})


@route("logic.guildBattleHandler.getReport")
def gb_get_report(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok(_temp={"report": {}})


@route("logic.guildBattleHandler.receiveAward")
def gb_receive_award(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    counts = rewards.grant_items(ctx.player, [{"entityId": 102, "count": 100}])
    ctx.save()
    return ctx.ok(gem=ctx.player["gem"], _temp={"entityCountMap": counts})


# ---------- logic.newGuildBattleHandler (8/8) & logic.activityGuildBattleHandler (8/8) ----------

def _register_guild_battle_variants(prefix: str):
    @route(f"{prefix}.openInfo")
    def _open_info(req: dict, session: dict):
        ctx = common.get(session)
        return ctx.error if ctx.error else ctx.ok(_temp={"openInfo": {"openTime": common.now_ms() + 3600000, "isOpen": False, "isReady": False}})

    @route(f"{prefix}.enter")
    @route(f"{prefix}.exit")
    @route(f"{prefix}.setDefenseTeamInfo")
    @route(f"{prefix}.choose")
    def _simple(req: dict, session: dict):
        ctx = common.get(session)
        return ctx.error if ctx.error else ctx.ok()

    @route(f"{prefix}.challenge")
    def _challenge(req: dict, session: dict):
        ctx = common.get(session)
        if ctx.error:
            return ctx.error
        counts = rewards.grant_items(ctx.player, [{"entityId": 101, "count": 15000}])
        ctx.save()
        return ctx.ok(coin=ctx.player["coin"], _temp={"isWin": True, "entityCountMap": counts})

    @route(f"{prefix}.result")
    @route(f"{prefix}.wintTimesRank")
    def _result(req: dict, session: dict):
        ctx = common.get(session)
        return ctx.error if ctx.error else ctx.ok(_temp={"list": []})


_register_guild_battle_variants("logic.newGuildBattleHandler")
_register_guild_battle_variants("logic.activityGuildBattleHandler")
