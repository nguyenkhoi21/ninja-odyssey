"""Player / role factories driven by the client's own data tables.

Every field here is read by the client's Player / Team / roleScene modules; a
missing field turns into a TypeError inside the client bundle, which then
freezes the whole request queue.
"""
import time
from datetime import datetime

import core.gamedata as gd

STAR_GROWTH = {i: 1 + 0.25 * (i - 1) for i in range(1, 61)}
MAX_STAR = 5
MAX_AWAKE_LEVEL = 40
EQUIP_PREFIXES = ("evlItem_", "stoneItem_", "artifactItem_", "capsuleItem_", "starSignItem_")
EQUIP_SLOTS = {
    "evlItem_": 6,
    "stoneItem_": 6,
    "artifactItem_": 5,
    "capsuleItem_": 5,
    "starSignItem_": 4,
}

ATTR_ZERO = (
    "hpRecover mpRecover unDizzinessRate unConfusedRate unTerrorRate unSilenceRate "
    "critRate dmg2HpRate dodgeRate atkSpeedRate cdSpeedRate hitRate keepMp reboundDmgHp "
    "skillDmg2HpRate hitReduceMpRate hitRepeledRate hitReduceAtkSpeedRate hitRateSilence "
    "missReboundTeamRate missReboundRate reduceDodgeRate missUnRecoverHpTeamRate "
    "missUnRecoverHpRate reducePctDmgRate atkIgnoreDodgeRate unDeBuffRate reduceControlTimeRate"
).split()


def _star_growth(star: int) -> float:
    return STAR_GROWTH.get(max(0, min(60, int(star))) or 1, 1)


def role_attr(kind_id: int, level: int = 1, star: int = 1):
    """Mirror of client roleScene.genData attr math (initHp + growth*starGrowth*level)."""
    row = gd.role(kind_id) or {}
    growth = _star_growth(star)
    hp_growth = int((row.get("hpGrowth") or 0) * growth)
    atk_growth = int((row.get("atkGrowth") or 0) * growth)
    def_growth = int((row.get("defGrowth") or 0) * growth)
    mdef_growth = int((row.get("mdefGrowth") or 0) * growth)

    attr = {
        "hpGrowth": hp_growth,
        "atkGrowth": atk_growth,
        "defGrowth": def_growth,
        "mdefGrowth": mdef_growth,
        "hp": int((row.get("initHp") or 100) + hp_growth * level),
        "atk": int((row.get("initAtk") or 10) + atk_growth * level),
        "def": int((row.get("initDef") or 10) + def_growth * level),
        "mdef": int((row.get("initMdef") or 10) + mdef_growth * level),
        "hit": int(row.get("hit") or 100),
        "dodge": int(row.get("dodge") or 0),
        "crit": int(row.get("crit") or 0),
        "mp": 0,
    }
    for key in ATTR_ZERO:
        attr[key] = 0
    return attr


def role_power(attr: dict, star: int) -> int:
    power = 0.1 * attr.get("hp", 0) + attr.get("atk", 0) + attr.get("def", 0) + attr.get("mdef", 0)
    power += 2 * (attr.get("hit", 0) + attr.get("dodge", 0) + attr.get("crit", 0))
    power += 30 * star
    return int(power)


def make_equipments(kind_id: int):
    row = gd.role(kind_id) or {}
    init_ids = list(row.get("initEvlItemIds") or [])
    eq = {}
    for slot in range(1, 7):
        kid = init_ids[slot - 1] if slot - 1 < len(init_ids) else None
        eq[f"evlItem_{slot}"] = {"kindId": kid, "level": 1} if kid else None
    for prefix in ("stoneItem_", "artifactItem_", "capsuleItem_", "starSignItem_"):
        for slot in range(1, EQUIP_SLOTS[prefix] + 1):
            eq[f"{prefix}{slot}"] = None
    return eq


def make_skills(kind_id: int, level: int):
    row = gd.role(kind_id) or {}
    skills = {}
    for sid in row.get("skillIds") or []:
        skills[str(sid)] = {"kindId": sid, "level": max(1, level)}
    return skills


def make_role(kind_id: int, level: int = 1, star: int = 1):
    row = gd.role(kind_id)
    if not row:
        kind_id = 100101
        row = gd.role(kind_id) or {}
    attr = role_attr(kind_id, level, star)
    equipments = make_equipments(kind_id)

    role = {
        "kindId": kind_id,
        "classId": row.get("classId", 1),
        "group": row.get("group", 1),
        "level": level,
        "experience": 0,
        "nextLevelExp": (gd.exp(level) or {}).get("roleExp") or level * 100,
        "star": star,
        "evolve": 0,
        "power": role_power(attr, star),
        "initAttr": dict(attr),
        "attr": attr,
        "skills": make_skills(kind_id, level),
        "awakeSkills": {},
        "awakeLevel": 0,
        "awakeRateIncreaseTimes": 0,
        "evolveSkillIds": [],
        "evolveSkillCount": 0,
        "evolveSkillRateIncreaseTimes": 0,
        "equipments": equipments,
        "trainLevelMap": {},
        "trainUnlockMap": {},
        "soulLevelMap": {},
        "friendshipId": 0,
    }
    return role


def ensure_role_fields(role: dict):
    kind_id = role.get("kindId") or 100101
    level = role.get("level") or 1
    star = role.get("star") or 1
    defaults = make_role(kind_id, level, star)

    for key, value in defaults.items():
        if key not in role or role[key] is None:
            role[key] = value

    eq = role.get("equipments")
    if not isinstance(eq, dict):
        eq = {}
    for key, value in defaults["equipments"].items():
        eq.setdefault(key, value)
    role["equipments"] = eq

    if not isinstance(role.get("skills"), dict) or not role["skills"]:
        role["skills"] = defaults["skills"]
    else:
        role_row = gd.role(kind_id) or {}
        init_sid = role_row.get("initSkillId")
        init_sid_str = str(init_sid) if init_sid is not None else None
        cleaned = {}
        for sk_key, sk_val in role["skills"].items():
            if not isinstance(sk_val, dict):
                continue
            sid = sk_val.get("kindId")
            if init_sid_str and (str(sk_key) == init_sid_str or str(sid) == init_sid_str):
                continue
            fskill = gd.find("fightSkillData", "kindId", sid) if sid is not None else None
            if not fskill or fskill.get("effect") is None:
                continue
            cleaned[str(sk_key)] = sk_val
        role["skills"] = cleaned or defaults["skills"]

    attr = role.get("attr")
    if not isinstance(attr, dict):
        attr = dict(defaults["attr"])
        role["attr"] = attr
    for key, value in defaults["attr"].items():
        attr.setdefault(key, value)

    if not isinstance(role.get("initAttr"), dict):
        role["initAttr"] = dict(defaults["initAttr"])

    role["power"] = role_power(attr, role.get("star") or 1)
    return role


def refresh_role(role: dict):
    """Recompute attr / power after a level/star/equipment change."""
    kind_id = role.get("kindId") or 100101
    role["attr"] = role_attr(kind_id, role.get("level", 1), role.get("star", 1))
    role["initAttr"] = dict(role["attr"])
    role["power"] = role_power(role["attr"], role.get("star", 1))
    return role


def _empty_activity_map():
    now = int(time.time() * 1000)
    day = 86400000
    return {
        "online_reward": {
            "name": "online_reward",
            "desc": "在线奖励",
            "rewards": [],
            "beginDay": 0,
            "durationDays": 1,
            "delayDays": 0,
            "isRepeat": True,
            "start_time": now,
            "end_time": now + day,
            "isSuccess": False,
            "needKeys": ["onlineTime"],
            "reachMap": {},
        }
    }


def make_default_player(pid: int, uid: int, name: str, user_name: str = ""):
    now = int(time.time() * 1000)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    starter_kind = 100101
    starter = make_role(starter_kind, level=1, star=1)
    vip_row = gd.vip(0) or {}

    item_rows = gd.table("entityData")
    starter_items = {}
    idx = 0
    for kid, count in ((20001, 20), (20002, 5), (20003, 2), (101, 0)):
        if count <= 0:
            continue
        idx += 1
        starter_items[str(idx)] = {"kindId": kid, "count": count}

    return {
        "sid": "connector-server-1",
        "logicSid": "logic-server-1",
        "id": pid,
        "name": name or f"Ninja_{pid}",
        "userId": uid,
        "serverId": 1,
        "oldServerId": 1,
        "channel": "Android",
        "userName": user_name or f"user_{uid}",
        "accountId": str(uid),
        "atime": now,
        "ctime": now,
        "resetTime": now,
        "guildId": 0,
        "guildName": None,
        "guildSkill": {
            "levelMap": {"HP": 0, "ATK": 0, "DEF": 0, "MDEF": 0},
            "attr": {"hp": 0, "atk": 0, "def": 0, "mdef": 0},
        },
        "photoInfo": {"photoImgId": 1003, "shipImgId": 900, "chatImgId": 0},
        "experience": 0,
        "level": 1,
        "power": starter["power"],
        "topPower": starter["power"],
        "coin": 50000,
        "gem": 0,
        "sysGem": 0,
        "costGem": 0,
        "topUpPoint": 0,
        "starCount": 0,
        "signInTime": 0,
        "signInDays": 0,
        "onlineTime": 0,
        "actionPoint": 120,
        "skillPoint": 10,
        "timesMaxMap": {"skillPoint": 10, "actionPoint": 120},
        "nextRecoverTimeMap": {"actionPoint": now, "skillPoint": now},
        "honourPoint": 0,
        "honourReceivedMap": {},
        "dailyTopUpMoney": 0,
        "dailyGiftPackCardExpire": 0,
        "buyGoodsTimesMap": {},
        "dailyBuyGoodsTimesMap": {},
        "weeklyBuyGoodsTimesMap": {},
        "vip": {
            "level": 0,
            "topUpMoney": 0,
            "topUpTrueMoney": 0,
            "topUpGem": 0,
            "giftGem": 0,
            "buyActionPointTimes": 0,
            "resetSmapTimesTimesMap": {},
            "buyCoinTimes": 0,
            "buyChallengeTimesTimes": 0,
            "buy3v3ChallengeTimesTimes": 0,
            "buySkillPointTimes": 0,
            "resetExpeditionTimes": 0,
            "tailChallengeTimesTimes": 0,
            "shipUpgradeLevelTimes": 0,
            "endlessSkipTimes": 0,
            "buyEyeChallengeTimesTimes": 0,
            "worshipStatueTimes": 0,
            "buyMapType5Times": 0,
            "resetSixExpeditionTimes": 0,
            "worshipStatueExtTimes": 0,
            "worshipStatue3v3Times": 0,
            "worshipStatueDoubleTimesMap": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
            "buyGiftIds": [],
        },
        "bag": {"items": starter_items, "lastIdx": idx},
        "team": {
            "roles": {"1": starter},
            "indexs": ["1", "0", "0", "0", "0"],
            "shipIndexs": ["0", "0", "0", "0", "0"],
            "lastIdx": 1,
            "friendshipAttr": {},
            "titleAttr": {},
            "friendships": {},
        },
        "friend": {"infoMap": {}, "list": [], "actionPointReceiveTimes": 0, "count": 0},
        "smapStarMap": {},
        "bmapBoxReceivedMap": {},
        "smapTimesMap": {},
        "smap": {"nowId": 10101, "maxId": 10101},
        "point": {
            "nextCoinFreeTime": 0,
            "nextGemFreeTime": 0,
            "coinTimes": 0,
            "gemTimes": 0,
            "coinTenTimes": 0,
            "gemTenTimes": 0,
            "freeCoinTimes": 1,
            "dailyCoinTimes": 0,
            "dailyUseGemTimes": 0,
            "isPayCoinFirst": True,
            "isPayGemFirst": True,
        },
        "gm": {
            "level": 0,
            "activeRewardStatusMap": {},
            "dailyRewardReceivedMap": {},
            "buyGoodsTimesMap": {},
            "point": 0,
        },
        "titleInfoMap": {},
        "chatSkinIds": [0],
        "friendshipUnlockMap": {},
        "arena": {
            "rank": 10001,
            "topRank": 10001,
            "winTimes": 0,
            "challengeTimes": 5,
            "maxChallengeTimes": 5,
            "remainingChallengeTimes": 5,
            "nextChallengeTime": 0,
            "defenseTeamIndexs": ["1"],
            "defenseShipIndexs": [],
        },
        "arena3v3": {
            "rank": 10001,
            "score": 0,
            "receiveCoin": 0,
            "challengeTimes": 5,
            "defenseTeamIndexsMap": {},
            "defenseShipIndexsMap": {},
        },
        "topArena3v3": {"rank": 0, "score": 0, "resetTime": 0, "topInfoMap": {}},
        "expedition": {
            "passId": 0,
            "prePassId": 0,
            "status": 1,
            "challengerInfo": {
                "idx": 0,
                "team": {
                    "playerId": 0,
                    "playerName": "",
                    "playerLevel": 1,
                    "playerPhotoInfo": {"photoImgId": 1003, "shipImgId": 900},
                    "roles": [],
                },
            },
        },
        "endless": {
            "maxFloor": 1,
            "nowFloor": 1,
            "topPassId": 0,
            "otherTopPassIdMap": {},
            "pursuitTeamIndexsMap": {},
            "pursuitShipIndexsMap": {},
            "resetTimesMap": {},
        },
        "shop": {"goodsMap": {}, "refreshTimesMap": {}, "hideRoleClassIds": []},
        "task": {
            "main": {},
            "daily": {},
            "achievement": {},
            "dailyActivePoint": 0,
            "weeklyActivePoint": 0,
            "activePoint": 0,
            "receivedIds": [],
            "receivedPointMap": {"daily": {}, "weekly": {}},
        },
        "activity": {
            "map": _empty_activity_map(),
            "received": {},
            "dream": {"point": 0, "curPos": 0, "logs": []},
            "scorePointInfoMap": {},
        },
        "island": {
            "attackerIds": [],
            "resources": {},
            "defenseTeamIndexs": [],
            "defenseShipIndexs": [],
            "reviveTimesMap": {},
        },
        "timePeak": {
            "selectBlessingIdsMap": {},
            "statusMap": {},
            "boxReceivedMap": {},
            "extInfoMap": {},
            "openBmapIds": [],
            "altarMap": {},
        },
        "practice": {
            "remainingChallengeTimes": 5,
            "remainingDefenseTimes": 5,
            "sixRemainingChallengeTimes": 3,
            "defenseInfoMap": {},
            "rank": 0,
        },
        "eye": {"list": [], "rank": 0, "challengeTimes": 2, "receiveTime": 0},
        "extra": {
            "serverTime": now,
            "serverTimeStr": now_str,
            "openDays": 1,
            "crossSid": 1,
            "mails": [],
            "goodsList": {},
            "banner": {"list": []},
            "guildBattle": {},
            "newGuildBattle": {},
            "activityGuildBattle": {},
            "allServerBattle": {},
            "worldBoss": {},
            "guildBoss": {},
            "prestigeBattle": {},
            "worshipBattle": {},
            "doubleBattle": {},
            "teamBattle": {},
            "chat": {"worldList": [], "guildList": [], "allServerList": []},
            "prestigeBattleRankTop1": None,
            "arenaRankTop1": None,
            "arena3v3RankTop1": None,
            "topArena3v3RankTop1": None,
            "isNoOneTimes": [],
            "star": 0,
        },
    }


def _merge_dict_defaults(target: dict, defaults: dict):
    for key, value in defaults.items():
        if key not in target:
            target[key] = value
        elif isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge_dict_defaults(target[key], value)


def ensure_player_fields(player: dict):
    now = int(time.time() * 1000)
    defaults = make_default_player(
        player.get("id", 0), player.get("userId", 0), player.get("name", ""), player.get("userName", "")
    )
    for key, value in defaults.items():
        if key not in player or player[key] is None:
            player[key] = value
        elif isinstance(value, dict) and isinstance(player[key], dict):
            _merge_dict_defaults(player[key], value)

    player["extra"]["serverTime"] = now
    player["extra"]["serverTimeStr"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    endless = player.setdefault("endless", {})
    if int(endless.get("topPassId") or 0) >= 40000:
        endless["topPassId"] = 0

    player.setdefault("activity", {}).setdefault("scorePointInfoMap", {})
    rpm = player.setdefault("task", {}).setdefault("receivedPointMap", {})
    if not isinstance(rpm, dict):
        rpm = {}
        player["task"]["receivedPointMap"] = rpm
    rpm.setdefault("daily", {})
    rpm.setdefault("weekly", {})

    roles = player.get("team", {}).get("roles", {})
    for role in roles.values():
        if isinstance(role, dict):
            ensure_role_fields(role)

    team = player.get("team", {})
    indexs = team.get("indexs")
    if not isinstance(indexs, list) or len(indexs) != 5:
        filled = [k for k in roles][:5]
        team["indexs"] = (filled + ["0"] * 5)[:5]
    recalc_power(player)
    return player


def recalc_power(player: dict):
    team = player.get("team", {})
    indexs = team.get("indexs") or []
    total = 0
    for idx in indexs:
        if str(idx) == "0":
            continue
        role = team.get("roles", {}).get(str(idx))
        if isinstance(role, dict):
            total += role.get("power") or 0
    player["power"] = total
    player["topPower"] = max(player.get("topPower") or 0, total)
    return total
