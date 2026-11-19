"""Activity map generation + reward claiming.

The client iterates `player.activity.map` and reads, per entry:
  name, desc, rewards[{needMap, dropListDesc, status}], start_time, end_time,
  isKeepShow, isSuccess, reachMap, needKeys, priority, group, ...
`status` uses 1=UN_COMPLETE, 2=CAN_RECEIVE, 3=COMPLETE.
"""
import time

import core.gamedata as gd

STATUS_UN_COMPLETE = 1
STATUS_CAN_RECEIVE = 2
STATUS_COMPLETE = 3

DAY = 86400000


def now_ms():
    return int(time.time() * 1000)


def _player_level(p):
    return int(p.get("level") or 1)


def reach_values(p):
    """Everything an activity needMap can reference."""
    vip = p.get("vip", {})
    task = p.get("task", {})
    extra = p.get("extra", {})
    reach = {
        "playerLevel": _player_level(p),
        "vipLevel": int(vip.get("level") or 0),
        "totalPower": int(p.get("power") or 0),
        "incPower": int(p.get("power") or 0),
        "gemTenTimes": int(p.get("point", {}).get("gemTenTimes") or 0),
        "topUpGem": int(vip.get("topUpGem") or 0),
        "topUpMoney": int(vip.get("topUpMoney") or 0),
        "costGem": int(p.get("costGem") or 0),
        "haveGem": int(p.get("gem") or 0),
        "loginDays": int(extra.get("openDays") or 1),
        "spLoginDays": int(extra.get("openDays") or 1),
        "taskActivePoint": int(task.get("activePoint") or 0),
        "onlineSeconds": int(p.get("onlineTime") or 0),
        "guildDrumTimes": 0,
        "guildWorshipTimes": 0,
        "A_practiceTimes": 0,
        "worldBossTimes": 0,
        "guildBossTimes": 0,
        "A_eyeTimes": 0,
        "A_tailTimes": 0,
        "endlessTopPassId": int(p.get("endless", {}).get("topPassId") or 0),
    }
    for k, v in (p.get("activityReach") or {}).items():
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


def _make_rewards(rows, reach, received):
    out = []
    for idx, row in enumerate(rows):
        need = row.get("needMap") or {}
        status = _status_for(need, reach, str(idx) in received)
        out.append({
            "desc": row.get("desc"),
            "needMap": need,
            "dropListDesc": row.get("dropListDesc"),
            "status": status,
        })
    return out


def _activity(name, desc, rewards, now, days=1, **kw):
    entry = {
        "name": name,
        "desc": desc,
        "rewards": rewards,
        "beginDay": 0,
        "durationDays": days,
        "delayDays": 0,
        "isRepeat": False,
        "start_time": now - DAY,
        "end_time": now + days * DAY,
        "isSuccess": False,
        "reachMap": {},
        "needKeys": [],
        "status": STATUS_UN_COMPLETE,
    }
    entry.update(kw)
    return entry


LEVEL_REWARDS = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60]
POWER_REWARDS = [20000, 50000, 100000, 200000, 400000, 800000, 1600000]
TASK_ACTIVE_POINTS = [0, 140, 280, 420, 560, 700, 840]


def build_activity_map(player):
    """Full activity map matching the client's expected activity names."""
    now = now_ms()
    reach = reach_values(player)
    received_map = player.setdefault("activity", {}).setdefault("received", {})
    act_map = player["activity"].setdefault("map", {})

    def recv(name):
        return received_map.setdefault(name, {})

    # ---- online reward
    online = _activity(
        "online_reward", "在线奖励",
        _make_rewards(
            [{"desc": "在线5分钟", "needMap": {"onlineSeconds": 300}, "dropListDesc": "101x10000"},
             {"desc": "在线15分钟", "needMap": {"onlineSeconds": 900}, "dropListDesc": "101x20000"},
             {"desc": "在线30分钟", "needMap": {"onlineSeconds": 1800}, "dropListDesc": "102x100"},
             {"desc": "在线60分钟", "needMap": {"onlineSeconds": 3600}, "dropListDesc": "102x200"}],
            reach, recv("online_reward")),
        now, isRepeat=True, isKeepShow=True, priority=900,
        needKeys=["onlineSeconds"],
    )
    act_map["online_reward"] = online

    # ---- level up
    act_map["upgradeLevel"] = _activity(
        "upgradeLevel", "冲级达人",
        _make_rewards(
            [{"desc": f"战队等级达到{lv}奖励", "needMap": {"playerLevel": lv},
              "dropListDesc": f"50580x{max(5, lv // 5)}"} for lv in LEVEL_REWARDS],
            reach, recv("upgradeLevel")),
        now, isKeepShow=True, priority=101, group=1,
    )

    # ---- power up
    act_map["upgradePower"] = _activity(
        "upgradePower", "战力飙升",
        _make_rewards(
            [{"desc": f"总战力达到{p // 1000}K奖励", "needMap": {"totalPower": p},
              "dropListDesc": "50470x5"} for p in POWER_REWARDS],
            reach, recv("upgradePower")),
        now, isKeepShow=True, priority=102, group=1,
    )

    # ---- task active (火影宝藏)
    ta_rewards = _make_rewards(
        [{"desc": f"活跃度达到{pt}", "needMap": {"taskActivePoint": pt},
          "dropListDesc": desc}
         for pt, desc in zip(TASK_ACTIVE_POINTS,
                             ["101x100000", "102x200", "322x1", "113x1", "114x1", "117x1", "119x1"])],
        reach, recv("task_active"))
    act_map["task_active"] = _activity(
        "task_active", "火影宝藏", ta_rewards, now,
        isKeepShow=True, priority=103, group=1,
    )
    adv_rewards = _make_rewards(
        [{"desc": "购买进阶奖励", "needMap": {"topUpGem": 600}, "dropListDesc": "102x1000"}],
        reach, recv("task_active_advanced"))
    act_map["task_active_advanced"] = _activity(
        "task_active_advanced", "火影宝藏进阶", adv_rewards, now,
        isKeepShow=True, priority=104, group=1,
        reachMap={"taskActivePoint": reach["taskActivePoint"], "topUpGem": reach["topUpGem"]},
    )

    # ---- normal / elite smap token activities (drive bmapScene)
    for key, desc, prio in (("smap_normal1", "普通关卡", 201),
                            ("smap_normal2", "普通关卡", 202),
                            ("smap_normal3", "普通关卡", 203),
                            ("smap_elite1", "精英关卡", 211),
                            ("smap_elite2", "精英关卡", 212),
                            ("smap_elite3", "精英关卡", 213)):
        act_map[key] = _activity(key, desc, [], now, isKeepShow=False, priority=prio, group=2)
        act_map[key + "_advanced"] = _activity(
            key + "_advanced", desc + "进阶", [], now, isKeepShow=False, priority=prio + 50, group=2)

    # ---- cost gem (钻石累消)
    act_map["costGem_daily"] = _activity(
        "costGem_daily", "钻石累消",
        _make_rewards(
            [{"desc": "累计消耗5000钻石", "needMap": {"costGem": 5000}, "dropListDesc": "37x1,116x50"},
             {"desc": "累计消耗15000钻石", "needMap": {"costGem": 15000}, "dropListDesc": "37x1,116x50"},
             {"desc": "累计消耗30000钻石", "needMap": {"costGem": 30000}, "dropListDesc": "37x2,116x100"}],
            reach, recv("costGem_daily")),
        now, isKeepShow=True, priority=205, group=2, isDailyReset=True,
    )

    # ---- daily gift / ad reward (homeScene reads these)
    act_map["dailyGift"] = _activity(
        "dailyGift", "每日礼包",
        _make_rewards([{"desc": "每日登录", "needMap": {"loginDays": 1},
                        "dropListDesc": "101x20000,102x100"}],
                      reach, recv("dailyGift")),
        now, isKeepShow=True, priority=110, group=1, isDailyReset=True,
    )
    act_map["adRward"] = _activity(
        "adRward", "广告奖励",
        _make_rewards([{"desc": "观看广告", "needMap": {"loginDays": 1},
                        "dropListDesc": "102x50"}],
                      reach, recv("adRward")),
        now, isKeepShow=True, priority=111, group=1, isDailyReset=True,
    )

    # ---- login reward series
    for key, prio in (("login_1", 120), ("login_2", 121), ("login_3", 122)):
        act_map[key] = _activity(
            key, "累计登录",
            _make_rewards(
                [{"desc": f"累计登录{d}天", "needMap": {"loginDays": d},
                  "dropListDesc": "101x30000,102x100"} for d in (1, 2, 3, 5, 7)],
                reach, recv(key)),
            now, isKeepShow=True, priority=prio, group=1,
        )

    return act_map


def refresh_activity(player):
    build_activity_map(player)
    for entry in player["activity"]["map"].values():
        statuses = [r.get("status") for r in entry.get("rewards") or []]
        entry["isSuccess"] = bool(statuses) and all(s == STATUS_COMPLETE for s in statuses)
    return player["activity"]["map"]


def claim_activity(player, name, reward_idx):
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
    statuses = [r.get("status") for r in rewards]
    entry["isSuccess"] = all(s == STATUS_COMPLETE for s in statuses)
    return row.get("dropListDesc"), None


def add_task_active_point(player, amount):
    task = player.setdefault("task", {})
    task["activePoint"] = int(task.get("activePoint") or 0) + int(amount)
    return task["activePoint"]
