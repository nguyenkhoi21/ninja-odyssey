"""Activity map generation + reward claiming driven by official server templates."""
import copy
import json
import os
import threading
import time

import core.gamedata as gd

STATUS_UN_COMPLETE = 1
STATUS_CAN_RECEIVE = 2
STATUS_COMPLETE = 3

DAY = 86400000

OFFICIAL_PATH = os.path.join(gd.DATA_DIR, "official_activity.json")
_OFFICIAL_CACHE = None
_LOCK = threading.RLock()

_LEGACY_KEYS = (
    "spActivity_official_login",
    "spActivity_official_login_adv",
    "spActivity_official_wish",
    "dreamActivity_official",
    "dreamActivity_official_box",
    "smap_normal2",
    "smap_normal2_advanced",
    "smap_normal3",
    "smap_normal3_advanced",
    "smap_elite2",
    "smap_elite2_advanced",
    "smap_elite3",
    "smap_elite3_advanced",
    "login_1",
    "login_3",
    "dailyGift",
    "adRward",
    "costGem_daily",
)


def now_ms():
    return int(time.time() * 1000)


def _load_official():
    global _OFFICIAL_CACHE
    with _LOCK:
        if _OFFICIAL_CACHE is not None:
            return _OFFICIAL_CACHE
        if os.path.exists(OFFICIAL_PATH):
            try:
                with open(OFFICIAL_PATH, "r", encoding="utf-8") as f:
                    _OFFICIAL_CACHE = json.load(f)
                    return _OFFICIAL_CACHE
            except Exception as e:
                print(f"[-] Error reading official_activity.json: {e}")
        _OFFICIAL_CACHE = {"activity": {"map": {}}, "goodsList": {}}
        return _OFFICIAL_CACHE


def ensure_official_goods(player: dict):
    """Ensure player.extra.goodsList contains all official goods definitions."""
    official_goods = _load_official().get("goodsList") or {}
    extra = player.setdefault("extra", {})
    goods = extra.get("goodsList")
    if not isinstance(goods, dict) or "1" not in goods:
        goods = {}
        extra["goodsList"] = goods
    for fake_id in ("1001", "1002", "1003", "1004", "1005", "1006"):
        if fake_id in goods and fake_id not in official_goods:
            goods.pop(fake_id, None)
    for gid, row in official_goods.items():
        if gid not in goods or not isinstance(goods.get(gid), dict) or "needPoint" not in goods[gid]:
            goods[gid] = copy.deepcopy(row)
    return goods


def _max_passed_smap_id(player: dict, map_type: str) -> int:
    mtype_dict = (player.get("smapStarMap") or {}).get(str(map_type))
    if not isinstance(mtype_dict, dict):
        return 0
    best = 0
    for bmap_dict in mtype_dict.values():
        if not isinstance(bmap_dict, dict):
            continue
        for sid, star in bmap_dict.items():
            if int(star or 0) > 0 and str(sid).isdigit():
                best = max(best, int(sid))
    return best


def _sum_smap_times(player: dict, map_type: str) -> int:
    mtype_dict = (player.get("smapTimesMap") or {}).get(str(map_type))
    if not isinstance(mtype_dict, dict):
        return 0
    total = 0
    for bmap_dict in mtype_dict.values():
        if isinstance(bmap_dict, dict):
            for v in bmap_dict.values():
                if isinstance(v, (int, float)):
                    total += int(v)
        elif isinstance(bmap_dict, (int, float)):
            total += int(bmap_dict)
    return total


def reach_values(player: dict, daily_buy: bool = False) -> dict:
    """Compute all activity needMap / reachMap values from live player state."""
    p = player
    vip = p.get("vip") or {}
    task = p.get("task") or {}
    extra = p.get("extra") or {}
    point = p.get("point") or {}
    roles = (p.get("team") or {}).get("roles") or {}
    reach_ext = p.get("activityReach") or {}
    dream_obj = (p.get("activity") or {}).get("dream") or {}

    color_counts = {c: 0 for c in range(2, 8)}
    role_lv_counts = {lv: 0 for lv in (20, 30, 35, 40, 45, 50)}
    evo_lv_counts = {lv: 0 for lv in (20, 30, 35, 40, 45, 50)}
    role_star3 = 0
    skill_level_sum = 0

    for role in roles.values():
        if not isinstance(role, dict):
            continue
        if int(role.get("star") or 1) >= 3:
            role_star3 += 1
        rlv = int(role.get("level") or 1)
        for thresh in role_lv_counts:
            if rlv >= thresh:
                role_lv_counts[thresh] += 1
        ent = gd.entity(role.get("kindId")) or {}
        color = int(ent.get("color") or 1)
        for c in color_counts:
            if color >= c:
                color_counts[c] += 1
        for sk in (role.get("skills") or {}).values():
            if isinstance(sk, dict):
                skill_level_sum += int(sk.get("level") or 1)
        for eq in (role.get("equipments") or {}).values():
            if isinstance(eq, dict):
                elv = int(eq.get("level") or 1)
                for thresh in evo_lv_counts:
                    if elv >= thresh:
                        evo_lv_counts[thresh] += 1

    open_days = int(extra.get("openDays") or 1)
    dream_point = int(reach_ext.get("dreamActivePoint") or dream_obj.get("point") or 0)

    reach = {
        "playerLevel": int(p.get("level") or 1),
        "vipLevel": int(vip.get("level") or 0),
        "totalPower": int(p.get("power") or 0),
        "incPower": int(p.get("power") or 0),
        "gemTenTimes": int(point.get("gemTenTimes") or 0),
        "gemPointTimes": int(point.get("gemTimes") or 0),
        "topUpGem": int(vip.get("topUpGem") or 0),
        "topUpMoney": int(vip.get("topUpMoney") or 0),
        "topUpDays": int(reach_ext.get("topUpDays") or (1 if int(vip.get("topUpGem") or 0) > 0 else 0)),
        "costGem": int(p.get("costGem") or 0),
        "haveGem": int(p.get("gem") or 0),
        "loginDays": open_days,
        "loginDays2": open_days,
        "spLoginDays": open_days,
        "taskActivePoint": int(task.get("activePoint") or 0),
        "taskActivePoint2": int(reach_ext.get("taskActivePoint2") or task.get("activePoint") or 0),
        "onlineSeconds": int(p.get("onlineTime") or 0),
        "endlessTopPassId": int((p.get("endless") or {}).get("topPassId") or 0),
        "mapType1SmapId": _max_passed_smap_id(p, "1"),
        "mapType2SmapId": _max_passed_smap_id(p, "2"),
        "mapType1Times": _sum_smap_times(p, "1"),
        "mapType2Times": _sum_smap_times(p, "2"),
        "mapType3Times": _sum_smap_times(p, "3"),
        "mapType4Times": _sum_smap_times(p, "4"),
        "roleCount": len(roles),
        "roleStar3Count": role_star3,
        "skillLevel": skill_level_sum,
        "arenaTimes": int(reach_ext.get("arenaTimes") or (p.get("arena") or {}).get("challengeTimes") or 0),
        "expeditionTimes": int(reach_ext.get("expeditionTimes") or (p.get("expedition") or {}).get("passId") or 0),
        "buyCoinTimes": int(vip.get("buyCoinTimes") or 0),
        "buyActionPointTimes": int(vip.get("buyActionPointTimes") or 0),
        "saveGemUpgradeLevelSaveGem": int((p.get("activitySaveGem") or {}).get("saveGemUpgradeLevel") or 0),
        "dreamActivePoint": dream_point,
        "isDailyGiftPackCard": 1 if int(p.get("dailyGiftPackCardExpire") or 0) > now_ms() else 0,
        "wishTimes": int(reach_ext.get("wishTimes") or 0),
        "spWishGemTimes": int(reach_ext.get("spWishGemTimes") or 0),
        "totalWishTimes": int(reach_ext.get("totalWishTimes") or 0),
        "shopBuyTimesMap": dict(reach_ext.get("shopBuyTimesMap") or {}),
        "A_arenaTimes": int(reach_ext.get("A_arenaTimes") or 0),
        "A_buyActionPointTimes": int(reach_ext.get("A_buyActionPointTimes") or 0),
        "A_buyCoinTimes": int(reach_ext.get("A_buyCoinTimes") or 0),
        "A_tailTimes": int(reach_ext.get("A_tailTimes") or 0),
        "guildDrumTimes": int(reach_ext.get("guildDrumTimes") or 0),
        "guildWorshipTimes": int(reach_ext.get("guildWorshipTimes") or 0),
        "A_practiceTimes": int(reach_ext.get("A_practiceTimes") or 0),
        "worldBossTimes": int(reach_ext.get("worldBossTimes") or 0),
        "guildBossTimes": int(reach_ext.get("guildBossTimes") or 0),
        "A_eyeTimes": int(reach_ext.get("A_eyeTimes") or 0),
        "spActive": int(reach_ext.get("spActive") or 0),
    }
    for c, cnt in color_counts.items():
        reach[f"roleColor{c}Count"] = cnt
    for lv, cnt in role_lv_counts.items():
        reach[f"roleLevel{lv}Count"] = cnt
    for lv, cnt in evo_lv_counts.items():
        reach[f"evoItemLevel{lv}Count"] = cnt

    buy_map = (p.get("dailyBuyGoodsTimesMap") if daily_buy else p.get("buyGoodsTimesMap")) or {}
    for gid, cnt in buy_map.items():
        reach[f"buyGoodsId_{gid}_times"] = int(cnt or 0)

    for k, v in reach_ext.items():
        if k not in reach:
            reach[k] = v
    return reach


def _status_for(need_map, reach, already_received):
    if already_received:
        return STATUS_COMPLETE
    ok = True
    for key, need in (need_map or {}).items():
        have = reach.get(key, 0)
        if isinstance(have, (int, float)) and have < need:
            ok = False
            break
    return STATUS_CAN_RECEIVE if ok else STATUS_UN_COMPLETE


def _ensure_active_window(obj: dict, now: int, default_days: int = 7):
    if not isinstance(obj, dict):
        return
    st = obj.get("start_time")
    et = obj.get("end_time")
    if st in (None, -1) or et in (None, -1):
        return
    if et <= now + 3600000 or st > now:
        days = max(1, int(obj.get("durationDays") or default_days))
        obj["start_time"] = now - DAY
        obj["end_time"] = now + days * DAY


def _update_entry_from_reach(entry: dict, reach: dict, received: dict, now: int):
    _ensure_active_window(entry, now)

    need_keys = list(entry.get("needKeys") or [])
    for rw in entry.get("rewards") or []:
        if isinstance(rw, dict):
            for k in (rw.get("needMap") or {}).keys():
                if k not in need_keys:
                    need_keys.append(k)

    reach_map = entry.get("reachMap")
    if not isinstance(reach_map, dict):
        reach_map = {}
    for k in need_keys:
        if k == "shopBuyTimesMap":
            reach_map.setdefault(k, {})
            if isinstance(reach.get(k), dict):
                reach_map[k] = dict(reach[k])
        else:
            reach_map[k] = reach.get(k, 0)
    for k in list(reach_map.keys()):
        if k in reach:
            reach_map[k] = reach[k]
    entry["reachMap"] = reach_map
    if need_keys:
        entry["needKeys"] = need_keys

    rewards = entry.get("rewards")
    if isinstance(rewards, list):
        for idx, rw in enumerate(rewards):
            if not isinstance(rw, dict):
                continue
            need = rw.get("needMap") or {}
            is_recv = str(idx) in received
            max_times = rw.get("buyMaxTimes")
            has_goods_key = any(str(k).startswith("buyGoodsId_") for k in need)
            if max_times and has_goods_key and not rw.get("isNoAutoReceive"):
                buy_cnt = 0
                for k in need:
                    if str(k).startswith("buyGoodsId_"):
                        buy_cnt = max(buy_cnt, int(reach.get(k, 0) or 0))
                max_t = int(max_times)
                rw["buyTimes"] = min(max_t, buy_cnt)
                rw["status"] = STATUS_COMPLETE if (buy_cnt >= max_t or is_recv) else STATUS_UN_COMPLETE
            else:
                st = _status_for(need, reach, is_recv)
                rw["status"] = st
                if max_times:
                    rw["buyTimes"] = int(max_times) if st == STATUS_COMPLETE else 0
        entry["isSuccess"] = False


def build_activity_map(player: dict):
    """Populate player.activity and extra.goodsList from official templates and live reach values."""
    now = now_ms()
    official = _load_official()
    official_act = official.get("activity") or {}
    ensure_official_goods(player)

    act = player.setdefault("activity", {})
    received_map = act.setdefault("received", {})
    act_map = act.setdefault("map", {})

    for old_k in _LEGACY_KEYS:
        act_map.pop(old_k, None)

    for sub_key, sub_val in official_act.items():
        if sub_key == "map":
            continue
        if sub_key == "dream":
            dream = act.get("dream")
            if not isinstance(dream, dict) or "activityItem" not in dream:
                tpl_dream = copy.deepcopy(sub_val)
                if isinstance(dream, dict):
                    tpl_dream["curPos"] = int(dream.get("curPos") or 1)
                    tpl_dream["point"] = int(dream.get("point") or 0)
                    tpl_dream["logs"] = list(dream.get("logs") or [])
                act["dream"] = tpl_dream
            _ensure_active_window(act["dream"].get("activityItem"), now)
        elif sub_key == "scorePointInfoMap":
            cur_sp = act.get("scorePointInfoMap")
            if not isinstance(cur_sp, dict) or "scorePoint1" not in cur_sp:
                act["scorePointInfoMap"] = copy.deepcopy(sub_val)
            for sp_info in act["scorePointInfoMap"].values():
                if isinstance(sp_info, dict):
                    _ensure_active_window(sp_info.get("activityItem"), now)
        elif sub_key not in act or act[sub_key] is None:
            act[sub_key] = copy.deepcopy(sub_val)
            if isinstance(act[sub_key], dict):
                _ensure_active_window(act[sub_key], now)
        elif isinstance(act[sub_key], dict):
            _ensure_active_window(act[sub_key], now)

    reach_all = reach_values(player, daily_buy=False)
    reach_daily = reach_values(player, daily_buy=True)

    official_map = official_act.get("map") or {}
    for name, tpl_entry in official_map.items():
        if not isinstance(tpl_entry, dict):
            continue
        entry = copy.deepcopy(tpl_entry)
        use_daily = bool(entry.get("isDailyReset"))
        _update_entry_from_reach(
            entry,
            reach_daily if use_daily else reach_all,
            received_map.setdefault(name, {}),
            now,
        )
        act_map[name] = entry

    return act_map


def refresh_activity(player: dict):
    build_activity_map(player)
    return player["activity"]["map"]


def claim_activity(player: dict, name: str, reward_idx):
    """Mark one reward claimed; returns (dropListDesc|None, error|None)."""
    act_map = player.setdefault("activity", {}).setdefault("map", {})
    entry = act_map.get(name)
    if not entry:
        return None, "活动不存在"
    rewards = entry.get("rewards") or []
    try:
        idx = int(reward_idx)
    except (TypeError, ValueError):
        return None, "参数错误"
    if idx < 0 or idx >= len(rewards):
        return None, "奖励不存在"
    row = rewards[idx]
    if row.get("status") == STATUS_COMPLETE:
        return None, "已领取"
    if row.get("status") != STATUS_CAN_RECEIVE:
        return None, "条件未达成"

    received = player["activity"].setdefault("received", {}).setdefault(name, {})
    received[str(idx)] = True
    row["status"] = STATUS_COMPLETE
    if row.get("buyMaxTimes"):
        row["buyTimes"] = int(row["buyMaxTimes"])
    entry["isSuccess"] = False

    inc_key = row.get("completeIncKey")
    if inc_key:
        inc_val = int(row.get("completeIncVal") or 10)
        reach_ext = player.setdefault("activityReach", {})
        reach_ext[inc_key] = int(reach_ext.get(inc_key) or 0) + inc_val
        if inc_key == "dreamActivePoint":
            dream = player.setdefault("activity", {}).setdefault("dream", {})
            dream["point"] = int(dream.get("point") or 0) + inc_val

    refresh_activity(player)
    return row.get("dropListDesc"), None


def auto_receive_for_goods(player: dict, goods_id: str) -> list:
    """Collect dropListDesc strings from isAutoReceive activities unlocked by goods_id."""
    from core import rewards as rw_mod

    gid_key = f"buyGoodsId_{goods_id}_times"
    refresh_activity(player)
    act_map = (player.get("activity") or {}).get("map") or {}
    received_map = (player.get("activity") or {}).setdefault("received", {})
    auto_items = []

    for name, entry in act_map.items():
        if not isinstance(entry, dict) or not entry.get("isAutoReceive"):
            continue
        rewards = entry.get("rewards") or []
        for idx, rw in enumerate(rewards):
            if not isinstance(rw, dict) or rw.get("isNoAutoReceive"):
                continue
            need = rw.get("needMap") or {}
            if gid_key not in need:
                continue
            max_t = int(rw.get("buyMaxTimes") or 1)
            use_daily = bool(entry.get("isDailyReset"))
            buy_map = (player.get("dailyBuyGoodsTimesMap") if use_daily else player.get("buyGoodsTimesMap")) or {}
            cur_t = int(buy_map.get(str(goods_id)) or 0)
            if cur_t >= int(need.get(gid_key) or 1):
                desc = rw.get("dropListDesc")
                if desc:
                    auto_items.extend(rw_mod.parse_drop_desc(desc))
                if cur_t >= max_t:
                    received_map.setdefault(name, {})[str(idx)] = True
                    rw["status"] = STATUS_COMPLETE
    if auto_items:
        refresh_activity(player)
    return auto_items


def add_task_active_point(player: dict, amount: int):
    task = player.setdefault("task", {})
    task["activePoint"] = int(task.get("activePoint") or 0) + int(amount)
    return task["activePoint"]
