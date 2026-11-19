from core.router import route
from core.db import add_role_to_team
from core import rewards, schema
from handlers import common


@route("logic.gmHandler.addItem")
def gm_add_item(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    kind_id = int(req.get("kindId") or 201)
    count = max(1, int(req.get("itemCount") or 1))
    counts = rewards.grant_items(ctx.player, [{"entityId": kind_id, "count": count, "extra": req.get("extra")}])
    schema.recalc_power(ctx.player)
    ctx.save()
    return ctx.ok(
        bag=ctx.player["bag"],
        coin=ctx.player.get("coin", 0),
        gem=ctx.player.get("gem", 0),
        _temp={"entityCountMap": counts},
    )


@route("logic.gmHandler.addRole")
def gm_add_role(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    kind_id = int(req.get("kindId") or 100301)
    idx, role = add_role_to_team(ctx.player, kind_id)
    ctx.save()
    return ctx.ok(team=ctx.player["team"], _temp={"newRoles": {idx: role}})


@route("logic.gmHandler.removeRole")
def gm_remove_role(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx = str(req.get("teamIndex") or "")
    team = ctx.player.setdefault("team", {})
    roles = team.setdefault("roles", {})
    roles.pop(tidx, None)
    team["indexs"] = ["0" if str(x) == tidx else x for x in (team.get("indexs") or ["0"] * 5)]
    schema.recalc_power(ctx.player)
    ctx.save()
    return ctx.ok(team=team)
