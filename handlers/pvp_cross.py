from core.router import route
from core import rewards, schema
from handlers import common


def _my_team_snapshot(player: dict, rank: int = 1):
    roles = list((player.get("team") or {}).get("roles", {}).values())[:5]
    return {
        "playerId": player["id"],
        "serverId": player.get("serverId", 1),
        "playerName": player.get("name", "Ninja"),
        "playerLevel": player.get("level", 1),
        "playerPhotoInfo": player.get("photoInfo", {"photoImgId": 1003, "shipImgId": 900}),
        "rank": rank,
        "ships": [],
        "roles": roles,
    }


# ---------- logic.islandHandler (15/15) ----------

@route("logic.islandHandler.myIslandList")
def island_my_list(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok(island=ctx.player.get("island", {}), _temp={"list": []})


@route("logic.islandHandler.match")
def island_match(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok(_temp={"list": []})


@route("logic.islandHandler.enemyList")
def island_enemy_list(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok(_temp={"list": []})


@route("logic.islandHandler.defenseTeam")
def island_defense_team(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    return ctx.ok(_temp={"_decodeKeys": ["defenseTeam"], "defenseTeam": _my_team_snapshot(ctx.player)})


@route("logic.islandHandler.choose")
def island_choose(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    snap = _my_team_snapshot(ctx.player)
    return ctx.ok(_temp={"_decodeKeys": ["attackTeam", "defenseTeam"], "attackTeam": snap, "defenseTeam": snap})


@route("logic.islandHandler.challenge")
def island_challenge(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    counts = rewards.grant_items(ctx.player, [{"entityId": 101, "count": 15000}])
    ctx.save()
    return ctx.ok(coin=ctx.player["coin"], _temp={"isWin": bool(req.get("isWin", True)), "entityCountMap": counts})


@route("logic.islandHandler.practice")
@route("logic.islandHandler.help")
@route("logic.islandHandler.setNeedHelp")
@route("logic.islandHandler.reviveRole")
def island_ops(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok(island=ctx.player.get("island", {}))


@route("logic.islandHandler.earlySettlement")
@route("logic.islandHandler.settlement")
def island_settlement(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    counts = rewards.grant_items(ctx.player, [{"entityId": 101, "count": 20000}, {"entityId": 102, "count": 50}])
    ctx.save()
    return ctx.ok(coin=ctx.player["coin"], gem=ctx.player["gem"], _temp={"entityCountMap": counts})


@route("logic.islandHandler.buyChallengeTimes")
def island_buy_times(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok()


@route("logic.islandHandler.reportList")
def island_report_list(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok(_temp={"list": []})


@route("logic.islandHandler.report")
def island_report(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok(_temp={"report": {}})


# ---------- logic.allServerBattleHandler (16/16) ----------

@route("logic.allServerBattleHandler.openInfo")
def asb_open_info(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok(_temp={"openInfo": {"openTime": common.now_ms() + 3600000, "isOpen": False}})


@route("logic.allServerBattleHandler.apply")
@route("logic.allServerBattleHandler.enter")
@route("logic.allServerBattleHandler.exit")
@route("logic.allServerBattleHandler.move")
@route("logic.allServerBattleHandler.beginBattle")
@route("logic.allServerBattleHandler.recover")
def asb_basic(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok()


@route("logic.allServerBattleHandler.getTeam")
def asb_get_team(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok(_temp={"team": ctx.player["team"]})


@route("logic.allServerBattleHandler.endBattle")
def asb_end_battle(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    counts = rewards.grant_items(ctx.player, [{"entityId": 101, "count": 20000}])
    ctx.save()
    return ctx.ok(coin=ctx.player["coin"], _temp={"isWin": bool(req.get("isWin", True)), "entityCountMap": counts})


@route("logic.allServerBattleHandler.receiveAward")
@route("logic.allServerBattleHandler.worshipStatue")
def asb_award(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    counts = rewards.grant_items(ctx.player, [{"entityId": 102, "count": 100}])
    ctx.save()
    return ctx.ok(gem=ctx.player["gem"], _temp={"entityCountMap": counts})


@route("logic.allServerBattleHandler.applyRank")
@route("logic.allServerBattleHandler.winTimesRank")
@route("logic.allServerBattleHandler.endTopRankInfo")
@route("logic.allServerBattleHandler.worshipRank")
def asb_ranks(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok(_temp={"list": []})


@route("logic.allServerBattleHandler.getReport")
def asb_report(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok(_temp={"report": {}})


# ---------- logic.teamBattleHandler (13/13) & logic.prestigeBattleHandler (12/12) ----------

def _register_team_battle(prefix: str, has_refresh: bool = False):
    @route(f"{prefix}.getInfo")
    def _info(req: dict, session: dict):
        ctx = common.get(session)
        return ctx.error if ctx.error else ctx.ok(_temp={"info": {"team": None, "challengeTimes": 5}})

    @route(f"{prefix}.getReadyTeamInfos")
    @route(f"{prefix}.match")
    @route(f"{prefix}.rank")
    def _lists(req: dict, session: dict):
        ctx = common.get(session)
        return ctx.error if ctx.error else ctx.ok(_temp={"list": []})

    @route(f"{prefix}.createTeam")
    def _create(req: dict, session: dict):
        ctx = common.get(session)
        if ctx.error:
            return ctx.error
        return ctx.ok(_temp={"teamId": ctx.player["id"]})

    @route(f"{prefix}.joinTeam")
    @route(f"{prefix}.dissolveTeam")
    @route(f"{prefix}.removeTeamMember")
    @route(f"{prefix}.practice")
    @route(f"{prefix}.setAutoPractice")
    @route(f"{prefix}.choose")
    def _ops(req: dict, session: dict):
        ctx = common.get(session)
        return ctx.error if ctx.error else ctx.ok()

    @route(f"{prefix}.challenge")
    def _challenge(req: dict, session: dict):
        ctx = common.get(session)
        if ctx.error:
            return ctx.error
        counts = rewards.grant_items(ctx.player, [{"entityId": 101, "count": 20000}])
        ctx.save()
        return ctx.ok(coin=ctx.player["coin"], _temp={"isWin": bool(req.get("isWin", True)), "entityCountMap": counts})

    if has_refresh:
        @route(f"{prefix}.refresh")
        def _refresh(req: dict, session: dict):
            ctx = common.get(session)
            return ctx.error if ctx.error else ctx.ok(_temp={"list": []})


_register_team_battle("logic.teamBattleHandler", has_refresh=True)
_register_team_battle("logic.prestigeBattleHandler", has_refresh=False)


# ---------- logic.doubleBattleHandler (9/9) & logic.worshipBattleHandler (9/9) ----------

def _register_bet_battle(prefix: str):
    @route(f"{prefix}.openInfo")
    def _open(req: dict, session: dict):
        ctx = common.get(session)
        return ctx.error if ctx.error else ctx.ok(_temp={"openInfo": {"isOpen": False, "openTime": common.now_ms() + 3600000}})

    @route(f"{prefix}.apply")
    @route(f"{prefix}.bet")
    def _act(req: dict, session: dict):
        ctx = common.get(session)
        return ctx.error if ctx.error else ctx.ok()

    @route(f"{prefix}.battleInfo")
    @route(f"{prefix}.getTeam")
    @route(f"{prefix}.getMyTeam")
    @route(f"{prefix}.getChampionTeam")
    def _info(req: dict, session: dict):
        ctx = common.get(session)
        return ctx.error if ctx.error else ctx.ok(_temp={"team": _my_team_snapshot(ctx.player) if ctx.player else {}, "list": []})

    @route(f"{prefix}.worshipRank")
    def _wrank(req: dict, session: dict):
        ctx = common.get(session)
        return ctx.error if ctx.error else ctx.ok(_temp={"list": []})

    @route(f"{prefix}.worshipStatue")
    def _wstatue(req: dict, session: dict):
        ctx = common.get(session)
        if ctx.error:
            return ctx.error
        counts = rewards.grant_items(ctx.player, [{"entityId": 102, "count": 50}])
        ctx.save()
        return ctx.ok(gem=ctx.player["gem"], _temp={"entityCountMap": counts})


_register_bet_battle("logic.doubleBattleHandler")
_register_bet_battle("logic.worshipBattleHandler")


# ---------- logic.eyeHandler (7/7) ----------

@route("logic.eyeHandler.info")
def eye_info(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok(eye=ctx.player.get("eye", {}))


@route("logic.eyeHandler.defenseTeam")
def eye_defense_team(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok(_temp={"_decodeKeys": ["defenseTeam"], "defenseTeam": _my_team_snapshot(ctx.player)})


@route("logic.eyeHandler.choose")
def eye_choose(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    snap = _my_team_snapshot(ctx.player)
    return ctx.ok(_temp={"_decodeKeys": ["attackTeam", "defenseTeam"], "attackTeam": snap, "defenseTeam": snap})


@route("logic.eyeHandler.challenge")
def eye_challenge(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    counts = rewards.grant_items(ctx.player, [{"entityId": 102, "count": 100}, {"entityId": 101, "count": 10000}])
    ctx.save()
    return ctx.ok(gem=ctx.player["gem"], coin=ctx.player["coin"], _temp={"isWin": bool(req.get("isWin", True)), "entityCountMap": counts})


@route("logic.eyeHandler.buyChallengeTimes")
def eye_buy_times(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    eye = ctx.player.setdefault("eye", {})
    eye["challengeTimes"] = int(eye.get("challengeTimes") or 0) + 2
    vip = ctx.player.setdefault("vip", {})
    vip["buyEyeChallengeTimesTimes"] = int(vip.get("buyEyeChallengeTimesTimes") or 0) + 1
    ctx.save()
    return ctx.ok(eye=eye, vip={"buyEyeChallengeTimesTimes": vip["buyEyeChallengeTimesTimes"]})


@route("logic.eyeHandler.report")
def eye_report(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok(_temp={"report": {}})


@route("logic.eyeHandler.startPrivate")
def eye_start_private(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else ctx.ok(eye=ctx.player.get("eye", {}))


# ---------- logic.practiceHandler (5/5) & logic.sixPracticeHandler (5/5) ----------

def _register_practice(prefix: str):
    @route(f"{prefix}.match")
    def _match(req: dict, session: dict):
        ctx = common.get(session)
        return ctx.error if ctx.error else ctx.ok(_temp={"list": []})

    @route(f"{prefix}.defenseTeam")
    def _dt(req: dict, session: dict):
        ctx = common.get(session)
        return ctx.error if ctx.error else ctx.ok(_temp={"_decodeKeys": ["defenseTeam"], "defenseTeam": _my_team_snapshot(ctx.player)})

    @route(f"{prefix}.choose")
    def _choose(req: dict, session: dict):
        ctx = common.get(session)
        if ctx.error:
            return ctx.error
        snap = _my_team_snapshot(ctx.player)
        return ctx.ok(_temp={"_decodeKeys": ["attackTeam", "defenseTeam"], "attackTeam": snap, "defenseTeam": snap})

    @route(f"{prefix}.challenge")
    def _challenge(req: dict, session: dict):
        ctx = common.get(session)
        if ctx.error:
            return ctx.error
        counts = rewards.grant_items(ctx.player, [{"entityId": 101, "count": 10000}])
        ctx.save()
        return ctx.ok(coin=ctx.player["coin"], _temp={"isWin": bool(req.get("isWin", True)), "entityCountMap": counts})

    @route(f"{prefix}.setDefenseInfo")
    def _set_def(req: dict, session: dict):
        ctx = common.get(session)
        if ctx.error:
            return ctx.error
        pr = ctx.player.setdefault("practice", {})
        pr.setdefault("defenseInfoMap", {})[str(req.get("type") or "1")] = {
            "defenseTeamIndexs": req.get("defenseTeamIndexs") or ["1"],
            "defenseShipIndexs": req.get("defenseShipIndexs") or [],
        }
        ctx.save()
        return ctx.ok(practice=pr)


_register_practice("logic.practiceHandler")
_register_practice("logic.sixPracticeHandler")
