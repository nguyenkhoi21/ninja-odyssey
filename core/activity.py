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
        "topUpDays": 1 if int(vip.get("topUpGem") or 0) > 0 else 0,
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
        "spActive": 0,
        "wishTimes": 0,
        "spWishGemTimes": 0,
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


def _activity(name, desc, rewards, now, days=1, reach=None, **kw):
    need_keys = list(kw.get("needKeys") or [])
    for row in rewards or []:
        for k in (row.get("needMap") or {}).keys():
            if k not in need_keys:
                need_keys.append(k)
    reach_map = {}
    if isinstance(reach, dict):
        for k in need_keys:
            reach_map[k] = reach.get(k, 0)
    extra_reach = kw.pop("reachMap", None)
    if isinstance(extra_reach, dict):
        reach_map.update(extra_reach)
    kw["needKeys"] = need_keys
    kw["reachMap"] = reach_map
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
        "reachMap": reach_map,
        "needKeys": need_keys,
        "status": STATUS_UN_COMPLETE,
    }
    entry.update(kw)
    return entry


LEVEL_REWARDS = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60]
POWER_REWARDS = [20000, 50000, 100000, 200000, 400000, 800000, 1600000]
TASK_ACTIVE_POINTS = [0, 140, 280, 420, 560, 700, 840]


def build_activity_map(player):
    """Full activity map matching the client's expected activity names & official events."""
    now = now_ms()
    reach = reach_values(player)
    received_map = player.setdefault("activity", {}).setdefault("received", {})
    act_map = player["activity"].setdefault("map", {})

    def recv(name):
        return received_map.setdefault(name, {})

    # ---- online reward
    act_map["online_reward"] = _activity(
        "online_reward", "在线奖励",
        _make_rewards(
            [{"desc": "在线5分钟", "needMap": {"onlineSeconds": 300}, "dropListDesc": "101x10000"},
             {"desc": "在线15分钟", "needMap": {"onlineSeconds": 900}, "dropListDesc": "101x20000"},
             {"desc": "在线30分钟", "needMap": {"onlineSeconds": 1800}, "dropListDesc": "102x100"},
             {"desc": "在线60分钟", "needMap": {"onlineSeconds": 3600}, "dropListDesc": "102x200"}],
            reach, recv("online_reward")),
        now, reach=reach, isRepeat=True, isKeepShow=True, priority=900,
        needKeys=["onlineSeconds"],
    )

    # ---- level up
    act_map["upgradeLevel"] = _activity(
        "upgradeLevel", "冲级达人",
        _make_rewards(
            [{"desc": f"战队等级达到{lv}奖励", "needMap": {"playerLevel": lv},
              "dropListDesc": f"50580x{max(5, lv // 5)}"} for lv in LEVEL_REWARDS],
            reach, recv("upgradeLevel")),
        now, days=30, reach=reach, isKeepShow=True, priority=101, group=1,
    )

    # ---- power up
    act_map["upgradePower"] = _activity(
        "upgradePower", "战力飙升",
        _make_rewards(
            [{"desc": f"总战力达到{p // 1000}K奖励", "needMap": {"totalPower": p},
              "dropListDesc": "50470x5"} for p in POWER_REWARDS],
            reach, recv("upgradePower")),
        now, days=30, reach=reach, isKeepShow=True, priority=102, group=1,
    )

    # ---- VIP level gifts (official)
    act_map["upgradeVip"] = _activity(
        "upgradeVip", "VIP礼包",
        _make_rewards(
            [{"desc": f"VIP{v}礼包", "needMap": {"vipLevel": v},
              "dropListDesc": "102x100,101x20000" if v == 1 else f"50130x{v * 20},101x{v * 30000}"}
             for v in range(1, 16)],
            reach, recv("upgradeVip")),
        now, days=30, reach=reach, spineResId="17", priority=104, isKeepShow=True, group=1,
    )

    # ---- task active (火影宝藏)
    ta_rewards = _make_rewards(
        [{"desc": f"活跃度达到{pt}", "needMap": {"taskActivePoint": pt},
          "dropListDesc": desc}
         for pt, desc in zip(TASK_ACTIVE_POINTS,
                             ["101x100000", "102x200", "322x1", "113x1", "114x1", "117x1", "119x1"])],
        reach, recv("task_active"))
    act_map["task_active"] = _activity(
        "task_active", "火影宝藏", ta_rewards, now, days=30, reach=reach,
        isKeepShow=True, priority=103, group=1,
    )
    adv_rewards = _make_rewards(
        [{"desc": "购买进阶奖励", "needMap": {"topUpGem": 600}, "dropListDesc": "102x1000"}],
        reach, recv("task_active_advanced"))
    act_map["task_active_advanced"] = _activity(
        "task_active_advanced", "火影宝藏进阶", adv_rewards, now, days=30, reach=reach,
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
        act_map[key] = _activity(key, desc, [], now, reach=reach, isKeepShow=False, priority=prio, group=2)
        act_map[key + "_advanced"] = _activity(
            key + "_advanced", desc + "进阶", [], now, reach=reach, isKeepShow=False, priority=prio + 50, group=2)

    # ---- cost gem (钻石累消)
    act_map["costGem_daily"] = _activity(
        "costGem_daily", "钻石累消",
        _make_rewards(
            [{"desc": "累计消耗5000钻石", "needMap": {"costGem": 5000}, "dropListDesc": "37x1,116x50"},
             {"desc": "累计消耗15000钻石", "needMap": {"costGem": 15000}, "dropListDesc": "37x1,116x50"},
             {"desc": "累计消耗30000钻石", "needMap": {"costGem": 30000}, "dropListDesc": "37x2,116x100"}],
            reach, recv("costGem_daily")),
        now, reach=reach, isKeepShow=True, priority=205, group=2, isDailyReset=True,
    )

    # ---- daily gift / ad reward (homeScene reads these)
    act_map["dailyGift"] = _activity(
        "dailyGift", "每日礼包",
        _make_rewards([{"desc": "每日登录", "needMap": {"loginDays": 1},
                        "dropListDesc": "101x20000,102x100"}],
                      reach, recv("dailyGift")),
        now, reach=reach, isKeepShow=True, priority=110, group=1, isDailyReset=True,
    )
    act_map["adRward"] = _activity(
        "adRward", "广告奖励",
        _make_rewards([{"desc": "观看广告", "needMap": {"loginDays": 1},
                        "dropListDesc": "102x50"}],
                      reach, recv("adRward")),
        now, reach=reach, isKeepShow=True, priority=111, group=1, isDailyReset=True,
    )

    # ---- login reward series & official loginReward / 8day / 14day
    act_map["loginReward"] = _activity(
        "loginReward", "登录豪礼",
        _make_rewards([{"desc": "登录奖励", "needMap": {"loginDays": 1},
                        "dropListDesc": "101x50000,102x500,37x5"}],
                      reach, recv("loginReward")),
        now, days=7, reach=reach, isKeepShow=False, priority=115,
    )
    login8_rows = [
        {"desc": "三代火影", "needMap": {"loginDays": 1}, "dropListDesc": "101x300000,50390x80"},
        {"desc": "神罗天征", "needMap": {"loginDays": 2}, "dropListDesc": "102x500,50450x40"},
        {"desc": "第3天奖励", "needMap": {"loginDays": 3}, "dropListDesc": "101x200000,37x3"},
        {"desc": "第4天奖励", "needMap": {"loginDays": 4}, "dropListDesc": "102x600,21001x20"},
        {"desc": "第5天奖励", "needMap": {"loginDays": 5}, "dropListDesc": "101x300000,113x3"},
        {"desc": "第6天奖励", "needMap": {"loginDays": 6}, "dropListDesc": "102x800,114x3"},
        {"desc": "第7天奖励", "needMap": {"loginDays": 7}, "dropListDesc": "101x500000,117x2"},
        {"desc": "第8天奖励", "needMap": {"loginDays": 8}, "dropListDesc": "102x1200,369x1"},
    ]
    act_map["login8day"] = _activity(
        "login8day", "8天登陆奖励",
        _make_rewards(login8_rows, reach, recv("login8day")),
        now, days=30, reach=reach, create_day=30, isKeepShow=True, priority=116,
    )
    login14_rows = [
        {"desc": f"第{d}天登陆奖励", "needMap": {"loginDays": d},
         "dropListDesc": "102x500" if d == 1 else ("120x5" if d == 2 else "102x300,37x2")}
        for d in range(1, 15)
    ]
    act_map["login14day"] = _activity(
        "login14day", "限时登录福利",
        _make_rewards(login14_rows, reach, recv("login14day")),
        now, days=18, reach=reach, spineResId="6", group=2, priority=106, create_day=18, isKeepShow=True,
    )
    for key, prio in (("login_1", 120), ("login_2", 121), ("login_3", 122)):
        act_map[key] = _activity(
            key, "累计登录",
            _make_rewards(
                [{"desc": f"累计登录{d}天", "needMap": {"loginDays": d},
                  "dropListDesc": "101x30000,102x100"} for d in (1, 2, 3, 5, 7)],
                reach, recv(key)),
            now, days=14, reach=reach, isKeepShow=True, priority=prio, group=1,
        )

    # ---- carnival (开服狂欢)
    for day_idx in (1, 2):
        ckey = f"carnival_login_{day_idx}"
        act_map[ckey] = _activity(
            ckey, "每日福利",
            _make_rewards(
                [{"desc": f"第{day_idx}天奖励", "needMap": {"loginDays": day_idx},
                  "dropListDesc": "369x1" if day_idx == 1 else "102x300,20001x20"}],
                reach, recv(ckey)),
            now, days=10, reach=reach, beginDay=0, durationDays=10, carnivalDay=day_idx, isKeepShow=True,
        )
    act_map["carnival_main_1_1"] = _activity(
        "carnival_main_1_1", "战队升级",
        _make_rewards(
            [{"desc": f"战队等级达到{lv}奖励", "needMap": {"playerLevel": lv},
              "dropListDesc": f"101x{lv * 2000},21001x{lv}"}
             for lv in (5, 10, 15, 20, 30)],
            reach, recv("carnival_main_1_1")),
        now, days=10, reach=reach, durationDays=10, carnivalDay=1, isKeepShow=True,
    )
    act_map["carnival_main_1_2"] = _activity(
        "carnival_main_1_2", "战力提升",
        _make_rewards(
            [{"desc": f"总战力达到{pw // 1000}K奖励", "needMap": {"totalPower": pw},
              "dropListDesc": "101x20000,20001x10"}
             for pw in (10000, 30000, 50000, 100000)],
            reach, recv("carnival_main_1_2")),
        now, days=10, reach=reach, durationDays=10, carnivalDay=2, isKeepShow=True,
    )

    # ---- official draw & topUp series
    act_map["gemTen"] = _activity(
        "gemTen", "十连抽福利",
        _make_rewards(
            [{"desc": f"钻石十连抽{t}次", "needMap": {"gemTenTimes": t},
              "dropListDesc": "102x200,37x2"} for t in (1, 3, 5, 10, 20)],
            reach, recv("gemTen")),
        now, days=14, reach=reach, priority=204, group=2, isKeepShow=True,
    )
    act_map["everyDayTopUp"] = _activity(
        "everyDayTopUp", "积天豪礼",
        _make_rewards(
            [{"desc": f"累计{d}天充值任意金额", "needMap": {"topUpGem": 1, "topUpDays": d},
              "dropListDesc": "113x2,20001x100"} for d in (1, 2, 3, 5, 7)],
            reach, recv("everyDayTopUp")),
        now, days=7, reach=reach, spineResId="1", itemResId=4, priority=206,
        showNeedKey="topUpDays", isKeepShow=True, group=1,
    )
    act_map["dailyTopUp_3"] = _activity(
        "dailyTopUp_3", "每日特惠",
        _make_rewards(
            [{"desc": "免费领取", "needMap": {"loginDays": 1}, "dropListDesc": "120x1"},
             {"desc": "累计充值100钻石", "needMap": {"topUpGem": 100}, "dropListDesc": "312x3,311x6,98x200"}],
            reach, recv("dailyTopUp_3")),
        now, days=7, reach=reach, spineResId="25", itemResId=8, priority=101,
        isAutoReceive=True, isKeepShow=True, isDailyReset=True,
    )
    act_map["dailyTopUpMoney_2"] = _activity(
        "dailyTopUpMoney_2", "每日累充",
        _make_rewards(
            [{"desc": f"今日累计充值{m}元", "needMap": {"topUpMoney": m},
              "dropListDesc": "102x300,37x3"} for m in (6, 30, 98, 198)],
            reach, recv("dailyTopUpMoney_2")),
        now, days=7, reach=reach, priority=105, isKeepShow=True, group=1, isDailyReset=True,
    )
    act_map["loginTopUp_1"] = _activity(
        "loginTopUp_1", "登录累充",
        _make_rewards(
            [{"desc": "登录并累充60钻", "needMap": {"loginDays": 1, "topUpGem": 60},
              "dropListDesc": "102x500,37x5"}],
            reach, recv("loginTopUp_1")),
        now, days=7, reach=reach, priority=107, isKeepShow=True, group=1,
    )

    # ---- SP theme activity bundle (login + loginAdvanced + spWish required by spActivity2Panel)
    act_map["spActivity_official_login"] = _activity(
        "spActivity_official_login", "登录福利",
        _make_rewards(
            [{"desc": f"登录第{d}天", "needMap": {"spLoginDays": d}, "dropListDesc": "37x5"}
             for d in range(1, 8)],
            reach, recv("spActivity_official_login")),
        now, days=7, reach=reach, type="login", sp2ClassId=82, priority=4, isKeepShow=True,
    )
    act_map["spActivity_official_login_adv"] = _activity(
        "spActivity_official_login_adv", "高级登陆奖励",
        _make_rewards(
            [{"desc": f"高级登录第{d}天", "needMap": {"spLoginDays": d, "buyGoodsId_629_times": 1},
              "dropListDesc": "37x10"} for d in range(1, 8)],
            reach, recv("spActivity_official_login_adv")),
        now, days=7, reach=reach, type="loginAdvanced", sp2ClassId=82, isKeepShow=True,
        reachMap={"spLoginDays": reach["spLoginDays"], "buyGoodsId_629_times": 0},
    )
    act_map["spActivity_official_wish"] = _activity(
        "spActivity_official_wish", "梦幻许愿",
        [],
        now, days=7, reach=reach, type="spWish", sp2ClassId=82, bgId=0, priority=10, isKeepShow=True,
        maxLuck=100, costGem=300, costGemMaxTiems=50,
        buyTicketCost={"entityId": 102, "count": 300},
        shop={"moneyId": 102, "list": []},
        reachMap={"wishTimes": reach.get("wishTimes", 0), "spWishGemTimes": reach.get("spWishGemTimes", 0), "shopBuyTimesMap": {}},
    )

    # ---- dream activity bundle (paired isActive + isActiveBox so dreamExtActivityPanel works)
    act_map["dreamActivity_official"] = _activity(
        "dreamActivity_official", "国度任务",
        _make_rewards(
            [{"desc": "登录1次", "needMap": {"loginDays": 1},
              "dropListDesc": "101x50000", "completeIncKey": "dreamActivePoint"}],
            reach, recv("dreamActivity_official")),
        now, days=7, reach=reach, spineResId="54", isKeepShow=True, isDream=True,
        isActive=True, isDailyReset=True, priority=10,
    )
    dream_point = int((player.get("activity", {}).get("dream") or {}).get("point") or 0)
    act_map["dreamActivity_official_box"] = _activity(
        "dreamActivity_official_box", "活跃宝箱",
        _make_rewards(
            [{"desc": "活跃10", "needMap": {"dreamActivePoint": 10}, "dropListDesc": "102x100"}],
            {"dreamActivePoint": dream_point}, recv("dreamActivity_official_box")),
        now, days=7, isDream=True, isActiveBox=True,
        reachMap={"dreamActivePoint": dream_point}, needKeys=["dreamActivePoint"],
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
