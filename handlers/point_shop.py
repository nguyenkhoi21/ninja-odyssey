import random

from core.router import route
from core.db import add_item_to_bag, add_role_to_team
from core import gamedata as gd, rewards, schema, tasks
from handlers import common

_ROLE_POOL_CACHE = None
_SOUL_BY_CLASS_CACHE = None
_EQUIVALENT_SOULS = {1: 10, 2: 30, 3: 80, 4: 180, 5: 330}


def _role_pool():
    global _ROLE_POOL_CACHE
    if _ROLE_POOL_CACHE is None:
        pool = []
        for r in gd.table("roleData"):
            if isinstance(r, dict) and r.get("kindId"):
                kid = int(r["kindId"])
                if kid % 100 in (1, 4, 7):
                    pool.append(kid)
        _ROLE_POOL_CACHE = pool or [100101, 100301, 100401, 101101, 103701, 104001, 104101, 105404]
    return _ROLE_POOL_CACHE


def _soul_kind_for_class(cid: int) -> int:
    global _SOUL_BY_CLASS_CACHE
    if _SOUL_BY_CLASS_CACHE is None:
        _SOUL_BY_CLASS_CACHE = {
            int(r["classId"]): int(r["kindId"])
            for r in gd.table("soulData")
            if isinstance(r, dict) and r.get("classId") is not None and r.get("kindId") is not None
        }
    return _SOUL_BY_CLASS_CACHE.get(int(cid or 0), 20001)


def _owned_class_ids(player: dict) -> set:
    owned = set()
    for role in (player.get("team") or {}).get("roles", {}).values():
        if not isinstance(role, dict):
            continue
        cid = role.get("classId") or (gd.role(role.get("kindId")) or {}).get("classId")
        if cid is not None:
            owned.add(int(cid))
    return owned


def _pick_draw_role(pool: list, count: int, is_gem: bool, owned_class_ids: set) -> int:
    if not is_gem and count == 1 and 2 not in owned_class_ids:
        return 100201
    if is_gem and len(owned_class_ids) < 3:
        missing = [
            k for k in pool
            if int((gd.role(k) or {}).get("classId") or 0) not in owned_class_ids
        ]
        if missing:
            return random.choice(missing)
    return random.choice(pool)


def _do_gacha(ctx, count: int, is_gem: bool):
    p = ctx.player
    pool = _role_pool()
    point = p.setdefault("point", {})
    now_ms = common.now_ms()
    if is_gem:
        next_free = int(point.get("nextGemFreeTime") or 0)
        if count == 1 and (next_free == 0 or now_ms >= next_free):
            point["nextGemFreeTime"] = now_ms + 172800000
        else:
            point["isPayGemFirst"] = False
        point["gemTimes"] = int(point.get("gemTimes") or 0) + count
        point["dailyUseGemTimes"] = int(point.get("dailyUseGemTimes") or 0) + count
        if count >= 10:
            point["gemTenTimes"] = int(point.get("gemTenTimes") or 0) + 1
    else:
        next_free = int(point.get("nextCoinFreeTime") or 0)
        free_times = int(point.get("freeCoinTimes") or 0)
        if count == 1 and free_times != 5 and (next_free == 0 or now_ms >= next_free):
            point["freeCoinTimes"] = free_times + 1
            point["nextCoinFreeTime"] = now_ms + 300000
        else:
            point["isPayCoinFirst"] = False
        point["coinTimes"] = int(point.get("coinTimes") or 0) + count
        point["dailyCoinTimes"] = int(point.get("dailyCoinTimes") or 0) + count
        if count >= 10:
            point["coinTenTimes"] = int(point.get("coinTenTimes") or 0) + 1

    owned_class_ids = _owned_class_ids(p)
    star = 2 if is_gem else 1
    new_roles = {}
    entity_map = {}
    drop_list = []

    for _ in range(count):
        kid = _pick_draw_role(pool, count, is_gem, owned_class_ids)
        role_row = gd.role(kid) or {}
        cid = int(role_row.get("classId") or 0)
        drop_list.append({"entityId": kid, "count": 1, "extra": {"star": star}})
        if cid and cid not in owned_class_ids:
            idx, role = add_role_to_team(p, kid, level=1, star=star)
            new_roles[idx] = role
            owned_class_ids.add(cid)
        else:
            soul_kid = _soul_kind_for_class(cid)
            soul_cnt = _EQUIVALENT_SOULS.get(star, 10 * star)
            add_item_to_bag(p, soul_kid, soul_cnt)
        entity_map[str(kid)] = entity_map.get(str(kid), 0) + 1

    schema.recalc_power(p)
    tasks.complete_daily(p, 2006)
    ctx.save()

    res_fields = {"team": {"roles": new_roles}} if new_roles else {}
    res_fields.update(
        bag=p["bag"],
        coin=p["coin"],
        gem=p["gem"],
        point=point,
        _temp={"dropList": drop_list, "entityCountMap": entity_map, "newRoles": new_roles},
    )
    return ctx.ok(**res_fields)


@route("logic.pointHandler.coin")
def point_coin(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else _do_gacha(ctx, 1, False)


@route("logic.pointHandler.coinTen")
def point_coin_ten(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else _do_gacha(ctx, 10, False)


@route("logic.pointHandler.coinHundred")
def point_coin_hundred(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else _do_gacha(ctx, 10, False)


@route("logic.pointHandler.gem")
def point_gem(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else _do_gacha(ctx, 1, True)


@route("logic.pointHandler.gemTen")
def point_gem_ten(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else _do_gacha(ctx, 10, True)


@route("logic.pointHandler.gemHundred")
def point_gem_hundred(req: dict, session: dict):
    ctx = common.get(session)
    return ctx.error if ctx.error else _do_gacha(ctx, 10, True)


@route("logic.pointHandler.receivePointAward")
def receive_point_award(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    counts = rewards.grant_items(ctx.player, [{"entityId": 20003, "count": 5}])
    ctx.save()
    return ctx.ok(bag=ctx.player["bag"], _temp={"entityCountMap": counts})


# ---------- Shop ----------

def _ensure_shop_type(player: dict, shop_type: int):
    shop = player.setdefault("shop", {"goodsMap": {}, "refreshTimesMap": {}, "hideRoleClassIds": []})
    gmap = shop.setdefault("goodsMap", {})
    key = str(shop_type)
    if key not in gmap or not gmap[key]:
        bucket = {}
        for row in gd.table("shopData"):
            if isinstance(row, dict) and int(row.get("type") or 1) == shop_type:
                gid = str(row["kindId"])
                bucket[gid] = {
                    "groupId": str(row.get("group") or 101),
                    "count": int(row.get("minCount") or 1),
                    "buyTimes": 0,
                    "isSaleOut": False,
                    "entityId": int(row.get("entityId") or 20001),
                    "group": int(row.get("group") or 101),
                    "price": int(row.get("price") or 100),
                    "moneyId": int(row.get("requireEntityId") or 101),
                    "requireVip": int(row.get("requireVip") or 0),
                    "shopType": shop_type,
                    "discount": 1,
                }
                if len(bucket) >= 12:
                    break
        gmap[key] = bucket
    return shop, gmap[key]


@route("logic.shopHandler.buy")
def shop_buy(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    p = ctx.player
    raw_id = str(req.get("kindId") or "10001")
    row = gd.find("shopData", "kindId", int(raw_id)) if raw_id.isdigit() else None
    shop_type = int((row or {}).get("type") or 1)
    shop, bucket = _ensure_shop_type(p, shop_type)
    good = bucket.get(raw_id) or {
        "groupId": "101",
        "count": int((row or {}).get("minCount") or 1),
        "buyTimes": 0,
        "isSaleOut": False,
        "entityId": int((row or {}).get("entityId") or 20001),
        "group": int((row or {}).get("group") or 101),
        "price": int((row or {}).get("price") or 100),
        "moneyId": int((row or {}).get("requireEntityId") or 101),
        "requireVip": 0,
        "shopType": shop_type,
        "discount": 1,
    }
    good["buyTimes"] = int(good.get("buyTimes") or 0) + 1
    good["isSaleOut"] = True
    bucket[raw_id] = good

    if good["moneyId"] == 102:
        p["gem"] = max(0, int(p.get("gem") or 0) - int(good["price"]))
    else:
        p["coin"] = max(0, int(p.get("coin") or 0) - int(good["price"]))

    counts = rewards.grant_items(p, [{"entityId": int(good["entityId"]), "count": int(good["count"])}])
    ctx.save()
    return ctx.ok(
        bag=p["bag"],
        coin=p["coin"],
        gem=p["gem"],
        shop={"goodsMap": {str(shop_type): {raw_id: good}}},
        _temp={"entityCountMap": counts},
    )


@route("logic.shopHandler.refresh")
def shop_refresh(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    stype = int(req.get("type") or 1)
    shop = ctx.player.setdefault("shop", {"goodsMap": {}, "refreshTimesMap": {}, "hideRoleClassIds": []})
    shop.setdefault("goodsMap", {})[str(stype)] = {}
    _, bucket = _ensure_shop_type(ctx.player, stype)
    rmap = shop.setdefault("refreshTimesMap", {})
    rmap[str(stype)] = int(rmap.get(str(stype)) or 0) + 1
    ctx.save()
    return ctx.ok(shop={"goodsMap": {str(stype): bucket}, "refreshTimesMap": rmap})


# ---------- BT / GM Special Shop (7/7) ----------

@route("logic.btHandler.buyShopItem")
def bt_buy_shop_item(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    sid = str(req.get("shopId") or "1")
    gm_obj = ctx.player.setdefault("gm", {})
    bmap = gm_obj.setdefault("buyGoodsTimesMap", {})
    bmap[sid] = int(bmap.get(sid) or 0) + 1
    counts = rewards.grant_items(ctx.player, [{"entityId": 20002, "count": 5}])
    ctx.save()
    return ctx.ok(bag=ctx.player["bag"], gm={"buyGoodsTimesMap": bmap}, _temp={"entityCountMap": counts})


@route("logic.btHandler.buyAllDailyShopItems")
def bt_buy_all_daily(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    counts = rewards.grant_items(ctx.player, [{"entityId": 20002, "count": 10}, {"entityId": 101, "count": 50000}])
    ctx.save()
    return ctx.ok(bag=ctx.player["bag"], coin=ctx.player["coin"], _temp={"entityCountMap": counts})


@route("logic.btHandler.costGmPoint")
def bt_cost_gm_point(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    gid = str(req.get("goodsId") or "1")
    gm_obj = ctx.player.setdefault("gm", {})
    gm_obj["point"] = max(0, int(gm_obj.get("point") or 0) - 10)
    bmap = gm_obj.setdefault("buyGoodsTimesMap", {})
    bmap[gid] = int(bmap.get(gid) or 0) + 1
    counts = rewards.grant_items(ctx.player, [{"entityId": 20003, "count": 2}])
    ctx.save()
    return ctx.ok(bag=ctx.player["bag"], gm={"point": gm_obj["point"], "buyGoodsTimesMap": bmap}, _temp={"entityCountMap": counts})


@route("logic.btHandler.exchange")
def bt_exchange(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    cnt = max(1, int(req.get("count") or 1))
    gm_obj = ctx.player.setdefault("gm", {})
    gm_obj["point"] = int(gm_obj.get("point") or 0) + cnt * 10
    ctx.save()
    return ctx.ok(gm={"point": gm_obj["point"]})


@route("logic.btHandler.receiveGmActiveReward")
def bt_active_reward(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    lvl = int(req.get("gmLevel") or 1)
    row = gd.find("gmData", "level", lvl) or gd.first("gmData") or {}
    items = rewards.parse_drop_desc(row.get("activeRewardDesc") or "101x30000")
    counts = rewards.grant_items(ctx.player, items)
    gm_obj = ctx.player.setdefault("gm", {})
    amap = gm_obj.setdefault("activeRewardStatusMap", {})
    amap[str(lvl)] = True
    ctx.save()
    return ctx.ok(bag=ctx.player["bag"], coin=ctx.player["coin"], gm={"activeRewardStatusMap": amap}, _temp={"entityCountMap": counts})


@route("logic.btHandler.receiveGmDailyReward")
def bt_daily_reward(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    lvl = int(req.get("gmLevel") or 1)
    row = gd.find("gmData", "level", lvl) or gd.first("gmData") or {}
    items = rewards.parse_drop_desc(row.get("dailyRewardDesc") or "101x30000")
    counts = rewards.grant_items(ctx.player, items)
    gm_obj = ctx.player.setdefault("gm", {})
    dmap = gm_obj.setdefault("dailyRewardReceivedMap", {})
    dmap[str(lvl)] = True
    ctx.save()
    return ctx.ok(bag=ctx.player["bag"], coin=ctx.player["coin"], gm={"dailyRewardReceivedMap": dmap}, _temp={"entityCountMap": counts})


@route("logic.btHandler.receiveGmCardDailyReward")
def bt_card_daily_reward(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    counts = rewards.grant_items(ctx.player, [{"entityId": 102, "count": 500}])
    ctx.save()
    return ctx.ok(gem=ctx.player["gem"], _temp={"entityCountMap": counts})
