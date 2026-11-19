from core.router import route
from core.db import add_item_to_bag, remove_item_from_bag, add_role_to_team
from core import gamedata as gd, schema
from handlers import common


def _find_by_fragment(table_name: str, frag_id: int, default_kid: int):
    for r in gd.table(table_name):
        if isinstance(r, dict) and r.get("fragmentId") == frag_id:
            return int(r["kindId"])
    return default_kid


@route("logic.bagHandler.sell")
def bag_sell(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    items = ctx.player.setdefault("bag", {"items": {}, "lastIdx": 0}).setdefault("items", {})
    idxs = req.get("bagIndexs") or []
    counts = req.get("itemCounts") or []
    gained = 0
    for idx, cnt in zip(idxs, counts):
        key = str(idx)
        it = items.get(key)
        if not it:
            continue
        c = max(1, int(cnt))
        row = gd.entity(it.get("kindId")) or {}
        price = int(row.get("price") or 100)
        if remove_item_from_bag(ctx.player, key, c):
            gained += price * c
    ctx.player["coin"] = int(ctx.player.get("coin") or 0) + gained
    ctx.save()
    return ctx.ok(bag=ctx.player["bag"], coin=ctx.player["coin"])


@route("logic.bagHandler.composeRole")
def compose_role(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    class_id = int(req.get("classId") or 1)
    matches = sorted(
        (r for r in gd.table("roleData") if isinstance(r, dict) and r.get("classId") == class_id),
        key=lambda r: r.get("kindId") or 0,
    )
    kind_id = int(matches[0]["kindId"]) if matches else (100001 + class_id * 100)
    idx, role = add_role_to_team(ctx.player, kind_id)
    ctx.save()
    return ctx.ok(
        team=ctx.player["team"],
        bag=ctx.player["bag"],
        _temp={"entityCountMap": {str(kind_id): 1}, "newRoles": {idx: role}},
    )


@route("logic.bagHandler.composeArtifact")
def compose_artifact(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    frag_id = int(req.get("fragmentId") or 80101)
    kid = _find_by_fragment("artifactData", frag_id, frag_id - 10000 if frag_id > 80000 else 70101)
    add_item_to_bag(ctx.player, kid, 1)
    ctx.save()
    return ctx.ok(bag=ctx.player["bag"], _temp={"entityCountMap": {str(kid): 1}})


@route("logic.bagHandler.composeFruit")
def compose_fruit(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    frag_id = int(req.get("fragmentId") or 10010)
    kid = _find_by_fragment("fruitData", frag_id, frag_id // 10 if frag_id >= 10000 else 1001)
    add_item_to_bag(ctx.player, kid, 1)
    ctx.save()
    return ctx.ok(bag=ctx.player["bag"], _temp={"entityCountMap": {str(kid): 1}})


@route("logic.bagHandler.composeShip")
def compose_ship(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    frag_id = int(req.get("fragmentId") or 9020)
    kid = _find_by_fragment("shipData", frag_id, 902)
    add_item_to_bag(ctx.player, kid, 1)
    ctx.save()
    return ctx.ok(bag=ctx.player["bag"], _temp={"entityCountMap": {str(kid): 1}})


@route("logic.bagHandler.composeCapsule")
def compose_capsule(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    for bidx in req.get("bagIndexs") or []:
        remove_item_from_bag(ctx.player, bidx, 1)
    kid = int(req.get("capsuleId") or 24001)
    add_item_to_bag(ctx.player, kid, 1)
    ctx.save()
    return ctx.ok(bag=ctx.player["bag"], _temp={"entityCountMap": {str(kid): 1}})


@route("logic.bagHandler.composeItem")
def compose_item(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    kid = int(req.get("kindId") or 20001)
    cnt = 5 if req.get("isAll") else 1
    add_item_to_bag(ctx.player, kid, cnt)
    ctx.save()
    return ctx.ok(bag=ctx.player["bag"], _temp={"entityCountMap": {str(kid): cnt}})


def _upgrade_bag_item_star(ctx, req):
    bidx = str(req.get("bagIndex") or "")
    items = ctx.player.setdefault("bag", {"items": {}, "lastIdx": 0}).setdefault("items", {})
    it = items.get(bidx)
    if it:
        it["star"] = int(it.get("star") or 1) + 1
        it["rateIncreaseTimes"] = 0
    ctx.save()
    return ctx.ok(bag=ctx.player["bag"], coin=ctx.player.get("coin", 0))


def _inc_bag_item_rate(ctx, req):
    bidx = str(req.get("bagIndex") or "")
    items = ctx.player.setdefault("bag", {"items": {}, "lastIdx": 0}).setdefault("items", {})
    it = items.get(bidx)
    if it:
        it["rateIncreaseTimes"] = int(it.get("rateIncreaseTimes") or 0) + 1
    ctx.save()
    return ctx.ok(bag=ctx.player["bag"], gem=ctx.player.get("gem", 0))


@route("logic.bagHandler.upgradeStarArtifact")
@route("logic.bagHandler.upgradeStarFruit")
@route("logic.bagHandler.upgradeStarSign")
def upgrade_star_bag(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    return _upgrade_bag_item_star(ctx, req)


@route("logic.bagHandler.increaseArtifactUpgradeStarSuccessRate")
@route("logic.bagHandler.increaseFruitUpgradeStarSuccessRate")
def inc_star_rate_bag(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    return _inc_bag_item_rate(ctx, req)


@route("logic.bagHandler.decomposeStarSign")
def decompose_star_sign(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    for bidx in req.get("bagIndexs") or []:
        remove_item_from_bag(ctx.player, bidx, 1)
    add_item_to_bag(ctx.player, 101, 0)
    ctx.player["coin"] = int(ctx.player.get("coin") or 0) + 5000
    ctx.save()
    return ctx.ok(bag=ctx.player["bag"], coin=ctx.player["coin"], _temp={"entityCountMap": {"101": 5000}})


@route("logic.bagHandler.resetCapsule")
def reset_capsule(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    bidx = str(req.get("bagIndex") or "")
    it = (ctx.player.get("bag", {}).get("items") or {}).get(bidx)
    if it:
        it["pendingReset"] = {"level": it.get("level", 1), "star": it.get("star", 1)}
    ctx.save()
    return ctx.ok(bag=ctx.player["bag"])


@route("logic.bagHandler.saveResetCapsule")
def save_reset_capsule(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    bidx = str(req.get("bagIndex") or "")
    it = (ctx.player.get("bag", {}).get("items") or {}).get(bidx)
    if it:
        it.pop("pendingReset", None)
    ctx.save()
    return ctx.ok(bag=ctx.player["bag"])


@route("logic.bagHandler.addShipExperience")
def add_ship_exp(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    bidx = str(req.get("bagIndex") or "")
    it = (ctx.player.get("bag", {}).get("items") or {}).get(bidx)
    if it:
        it["experience"] = int(it.get("experience") or 0) + int(req.get("experience") or 100)
        it["level"] = int(it.get("level") or 1) + 1
    ctx.save()
    return ctx.ok(bag=ctx.player["bag"])


@route("logic.bagHandler.upgradeShip")
@route("logic.bagHandler.upgradeShipSkill")
@route("logic.bagHandler.upgradeShipStar")
def upgrade_ship(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    bidx = str(req.get("bagIndex") or "")
    it = (ctx.player.get("bag", {}).get("items") or {}).get(bidx)
    if it:
        it["level"] = int(it.get("level") or 1) + 1
        it["star"] = int(it.get("star") or 1) + 1
    ctx.save()
    return ctx.ok(bag=ctx.player["bag"], coin=ctx.player.get("coin", 0))
