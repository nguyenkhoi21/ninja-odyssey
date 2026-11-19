import copy

from core.router import route
from core.db import add_item_to_bag, remove_item_from_bag
from core import gamedata as gd, schema, tasks
from handlers import common

EQUIP_SLOTS = {
    "stone": ("stoneItem_", 6, "stone"),
    "artifact": ("artifactItem_", 5, "artifact"),
    "capsule": ("capsuleItem_", 5, "capsule"),
    "starSign": ("starSignItem_", 4, "starSign"),
}


def _get_role(ctx, req):
    tidx = str(req.get("teamIndex") or "1")
    role = common.role_of(ctx.player, tidx)
    return tidx, role


def _recalc_role_and_team(ctx, role):
    schema.refresh_role(role)
    # Apply equipment/train/awake bonuses on top of base attr
    eqs = role.get("equipments") or {}
    bonus_hp = 0
    bonus_atk = 0
    bonus_def = 0
    for k, eq in eqs.items():
        if not isinstance(eq, dict):
            continue
        lvl = int(eq.get("level") or 1)
        star = int(eq.get("star") or 0)
        bonus_hp += lvl * 25 + star * 150
        bonus_atk += lvl * 4 + star * 25
        bonus_def += lvl * 3 + star * 20
    awake = int(role.get("awakeLevel") or 0)
    train_sum = sum(int(v or 0) for v in (role.get("trainLevelMap") or {}).values())
    bonus_hp += awake * 200 + train_sum * 80
    bonus_atk += awake * 25 + train_sum * 12
    bonus_def += awake * 20 + train_sum * 10

    attr = role["attr"]
    attr["hp"] = int(attr.get("hp", 0)) + bonus_hp
    attr["atk"] = int(attr.get("atk", 0)) + bonus_atk
    attr["def"] = int(attr.get("def", 0)) + bonus_def
    attr["mdef"] = int(attr.get("mdef", 0)) + bonus_def
    role["power"] = schema.role_power(attr, role.get("star") or 1)
    schema.recalc_power(ctx.player)


def _equip_one(ctx, role, slot_kind: str, bag_index):
    prefix, max_slots, entity_type = EQUIP_SLOTS[slot_kind]
    bag = ctx.player.setdefault("bag", {"items": {}, "lastIdx": 0})
    item = (bag.get("items") or {}).get(str(bag_index))
    if not item:
        return False
    eqs = role.setdefault("equipments", {})
    target_slot = None
    for i in range(1, max_slots + 1):
        slot_key = f"{prefix}{i}"
        if eqs.get(slot_key) is None:
            target_slot = slot_key
            break
    if target_slot is None:
        target_slot = f"{prefix}1"
        old = eqs.get(target_slot)
        if isinstance(old, dict) and old.get("kindId"):
            add_item_to_bag(ctx.player, int(old["kindId"]), 1)
    eq_obj = dict(item)
    eq_obj["count"] = 1
    eq_obj.setdefault("level", 1)
    eq_obj.setdefault("star", 1)
    remove_item_from_bag(ctx.player, bag_index, 1)
    eqs[target_slot] = eq_obj
    return True


def _equip_all(ctx, role, slot_kind: str):
    prefix, max_slots, entity_type = EQUIP_SLOTS[slot_kind]
    bag = ctx.player.setdefault("bag", {"items": {}, "lastIdx": 0})
    items = bag.get("items") or {}
    eqs = role.setdefault("equipments", {})
    equipped = False
    for i in range(1, max_slots + 1):
        slot_key = f"{prefix}{i}"
        if eqs.get(slot_key) is not None:
            continue
        for bidx, it in list(items.items()):
            if not it:
                continue
            row = gd.entity(it.get("kindId")) or {}
            if row.get("type") == entity_type or slot_kind == "stone" and "stone" in str(row.get("type") or "").lower():
                _equip_one(ctx, role, slot_kind, bidx)
                equipped = True
                break
    return equipped


def _unequip_one(ctx, role, slot_key: str):
    eqs = role.setdefault("equipments", {})
    cur = eqs.get(slot_key)
    if isinstance(cur, dict) and cur.get("kindId"):
        add_item_to_bag(ctx.player, int(cur["kindId"]), 1)
        eqs[slot_key] = None
        return True
    return False


def _unequip_all(ctx, role, slot_kind: str):
    prefix, max_slots, _ = EQUIP_SLOTS[slot_kind]
    for i in range(1, max_slots + 1):
        _unequip_one(ctx, role, f"{prefix}{i}")


# ---------- EXP / Evolve / Star / Skills ----------

@route("logic.teamHandler.useExpItem")
def use_exp_item(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    bidx = str(req.get("bagIndex") or "")
    cnt = max(1, int(req.get("itemCount") or 1))
    bag_item = (ctx.player.get("bag", {}).get("items") or {}).get(bidx)
    exp_per = 100
    if bag_item:
        row = gd.entity(bag_item.get("kindId")) or {}
        exp_per = int((row.get("extra") or {}).get("exp") if isinstance(row.get("extra"), dict) else 100) or 100
        remove_item_from_bag(ctx.player, bidx, cnt)
    common.add_role_exp(role, exp_per * cnt, max_level=max(100, int(ctx.player.get("level") or 1)))
    _recalc_role_and_team(ctx, role)
    tasks.complete_daily(ctx.player, 2001)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}}, bag=ctx.player["bag"])


@route("logic.teamHandler.useExpItemMax")
def use_exp_item_max(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    target_lvl = max(int(role.get("level") or 1) + 1, int(ctx.player.get("level") or 1))
    role["level"] = min(100, target_lvl)
    role["experience"] = 0
    role["nextLevelExp"] = common.level_exp(role["level"]) or role["level"] * 100
    _recalc_role_and_team(ctx, role)
    tasks.complete_daily(ctx.player, 2001)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}}, bag=ctx.player["bag"])


@route("logic.teamHandler.evolveRole")
def evolve_role(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    pre_role = copy.deepcopy(role)
    cur_kid = int(role.get("kindId") or 100101)
    row = gd.role(cur_kid) or {}
    next_kid = row.get("evolutionRoleId")
    if next_kid and gd.role(int(next_kid)):
        role["kindId"] = int(next_kid)
    elif gd.role(cur_kid + 1):
        role["kindId"] = cur_kid + 1
    role["evolve"] = int(role.get("evolve") or 0) + 1
    # Unlock new skills from evolved role row
    new_row = gd.role(role["kindId"]) or {}
    skills = role.setdefault("skills", {})
    for sid in new_row.get("skillIds") or []:
        skills.setdefault(str(sid), {"kindId": sid, "level": 1})
    _recalc_role_and_team(ctx, role)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}}, _temp={"preRole": pre_role})


@route("logic.teamHandler.upgradeRoleStar")
def upgrade_role_star(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    role["star"] = min(60, int(role.get("star") or 1) + 1)
    _recalc_role_and_team(ctx, role)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}})


@route("logic.teamHandler.roleBreak")
def role_break(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    for bidx in req.get("bagIndexs") or []:
        remove_item_from_bag(ctx.player, bidx, 1)
    role["star"] = min(60, int(role.get("star") or 1) + 1)
    _recalc_role_and_team(ctx, role)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}}, bag=ctx.player["bag"])


@route("logic.teamHandler.upgradeRoleSkill")
def upgrade_role_skill(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    skid = str(req.get("skillKindId") or "")
    is_max = bool(req.get("isMax"))
    skills = role.setdefault("skills", {})
    entry = skills.setdefault(skid, {"kindId": int(skid) if skid.isdigit() else 0, "level": 1})
    cap = max(1, int(role.get("level") or 1))
    entry["level"] = cap if is_max else min(cap, int(entry.get("level") or 1) + 1)
    tasks.complete_daily(ctx.player, 2002)
    _recalc_role_and_team(ctx, role)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}}, skillPoint=ctx.player.get("skillPoint", 10))


@route("logic.teamHandler.evolveRoleSkill")
def evolve_role_skill(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    skid = int(req.get("skillKindId") or 0)
    ev = role.setdefault("evolveSkillIds", [])
    if skid and skid not in ev:
        ev.append(skid)
    role["evolveSkillCount"] = len(ev)
    role["evolveSkillRateIncreaseTimes"] = 0
    _recalc_role_and_team(ctx, role)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}})


@route("logic.teamHandler.increaseEvolveSkillSuccessRate")
def increase_evolve_skill_rate(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    role["evolveSkillRateIncreaseTimes"] = int(role.get("evolveSkillRateIncreaseTimes") or 0) + 1
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}}, gem=ctx.player.get("gem", 0))


# ---------- Awakening / Training / Soul / Friendship ----------

@route("logic.teamHandler.upgradeRoleAwakeLevel")
def upgrade_awake_level(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    role["awakeLevel"] = min(schema.MAX_AWAKE_LEVEL, int(role.get("awakeLevel") or 0) + 1)
    role["awakeRateIncreaseTimes"] = 0
    _recalc_role_and_team(ctx, role)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}}, coin=ctx.player.get("coin", 0))


@route("logic.teamHandler.increaseAwakeLevelUpgradeSuccessRate")
def increase_awake_rate(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    role["awakeRateIncreaseTimes"] = int(role.get("awakeRateIncreaseTimes") or 0) + 1
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}}, gem=ctx.player.get("gem", 0))


@route("logic.teamHandler.upgradeRoleAwakeSkill")
def upgrade_awake_skill(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    skid = str(req.get("skillKindId") or "0")
    is_max = bool(req.get("isMax"))
    ask = role.setdefault("awakeSkills", {})
    entry = ask.setdefault(skid, {"kindId": int(skid) if skid.isdigit() else 0, "level": 0})
    entry["level"] = max(1, int(role.get("awakeLevel") or 1)) if is_max else int(entry.get("level") or 0) + 1
    _recalc_role_and_team(ctx, role)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}})


@route("logic.teamHandler.unlockRoleTrain")
def unlock_role_train(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    ttype = str(req.get("type") or "1")
    role.setdefault("trainUnlockMap", {})[ttype] = True
    role.setdefault("trainLevelMap", {}).setdefault(ttype, 0)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}})


@route("logic.teamHandler.trainRole")
def train_role(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    ttype = str(req.get("type") or "1")
    tmap = role.setdefault("trainLevelMap", {})
    tmap[ttype] = int(tmap.get(ttype) or 0) + 1
    _recalc_role_and_team(ctx, role)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}})


@route("logic.teamHandler.resetRoleTrain")
def reset_role_train(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    ttype = str(req.get("type") or "1")
    role.setdefault("trainLevelMap", {})[ttype] = 0
    _recalc_role_and_team(ctx, role)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}})


@route("logic.teamHandler.soulRole")
def soul_role(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    stype = str(req.get("type") or "1")
    smap = role.setdefault("soulLevelMap", {})
    smap[stype] = int(smap.get(stype) or 0) + 1
    _recalc_role_and_team(ctx, role)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}})


@route("logic.teamHandler.unlockFriendship")
def unlock_friendship(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    fs_id = str(req.get("friendShipId") or "101")
    ctx.player.setdefault("friendshipUnlockMap", {})[fs_id] = True
    ctx.player.setdefault("team", {}).setdefault("friendships", {})[fs_id] = True
    schema.recalc_power(ctx.player)
    ctx.save()
    return ctx.ok(team=ctx.player["team"], friendshipUnlockMap=ctx.player["friendshipUnlockMap"])


# ---------- Equipment (evlItem_*) ----------

@route("logic.teamHandler.upgradeEquipment")
@route("logic.teamHandler.upgradeEquipmentMax")
def upgrade_equipment(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    eq_type = str(req.get("equipmentType") or "evlItem_1")
    eqs = role.setdefault("equipments", {})
    cur = eqs.get(eq_type)
    if isinstance(cur, dict):
        cap = max(1, int(role.get("level") or 1))
        cur["level"] = cap if req.get("isMax") or "Max" in str(req.get("_route") or "") else min(cap, int(cur.get("level") or 1) + 1)
    _recalc_role_and_team(ctx, role)
    tasks.complete_daily(ctx.player, 2003)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}}, coin=ctx.player.get("coin", 0))


@route("logic.teamHandler.upgradeAllEquipmentMax")
def upgrade_all_equipment_max(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    eqs = role.setdefault("equipments", {})
    cap = max(1, int(role.get("level") or 1))
    for i in range(1, 7):
        cur = eqs.get(f"evlItem_{i}")
        if isinstance(cur, dict):
            cur["level"] = max(int(cur.get("level") or 1), cap)
    _recalc_role_and_team(ctx, role)
    tasks.complete_daily(ctx.player, 2003)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}}, coin=ctx.player.get("coin", 0))


@route("logic.teamHandler.evolveEquipment")
def evolve_equipment(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    eq_type = str(req.get("equipmentType") or "evlItem_1")
    eqs = role.setdefault("equipments", {})
    cur = eqs.get(eq_type)
    if isinstance(cur, dict):
        cur["kindId"] = int(cur.get("kindId") or 30101) + 1
        cur["level"] = int(cur.get("level") or 1) + 1
    _recalc_role_and_team(ctx, role)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}}, bag=ctx.player["bag"], coin=ctx.player.get("coin", 0))


@route("logic.teamHandler.evolveAllEquipment")
def evolve_all_equipment(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    eqs = role.setdefault("equipments", {})
    for i in range(1, 7):
        cur = eqs.get(f"evlItem_{i}")
        if isinstance(cur, dict):
            cur["kindId"] = int(cur.get("kindId") or 30101) + 1
            cur["level"] = int(cur.get("level") or 1) + 1
    _recalc_role_and_team(ctx, role)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}}, bag=ctx.player["bag"], coin=ctx.player.get("coin", 0))


# ---------- Stones / Artifacts / Capsules / StarSigns ----------

@route("logic.teamHandler.equipStone")
def equip_stone(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    _equip_one(ctx, role, "stone", req.get("bagIndex"))
    _recalc_role_and_team(ctx, role)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}}, bag=ctx.player["bag"])


@route("logic.teamHandler.equipAllStone")
def equip_all_stone(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    _equip_all(ctx, role, "stone")
    _recalc_role_and_team(ctx, role)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}}, bag=ctx.player["bag"])


@route("logic.teamHandler.unEquipStone")
def unequip_stone(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    _unequip_one(ctx, role, str(req.get("equipmentType") or "stoneItem_1"))
    _recalc_role_and_team(ctx, role)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}}, bag=ctx.player["bag"])


@route("logic.teamHandler.unEquipAllStone")
def unequip_all_stone(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    _unequip_all(ctx, role, "stone")
    _recalc_role_and_team(ctx, role)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}}, bag=ctx.player["bag"])


@route("logic.teamHandler.equipArtifact")
def equip_artifact(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    _equip_one(ctx, role, "artifact", req.get("bagIndex"))
    _recalc_role_and_team(ctx, role)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}}, bag=ctx.player["bag"])


@route("logic.teamHandler.equipAllArtifact")
def equip_all_artifact(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    _equip_all(ctx, role, "artifact")
    _recalc_role_and_team(ctx, role)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}}, bag=ctx.player["bag"])


@route("logic.teamHandler.unEquipArtifact")
def unequip_artifact(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    _unequip_one(ctx, role, str(req.get("equipmentType") or "artifactItem_1"))
    _recalc_role_and_team(ctx, role)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}}, bag=ctx.player["bag"])


@route("logic.teamHandler.unEquipAllArtifact")
def unequip_all_artifact(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    _unequip_all(ctx, role, "artifact")
    _recalc_role_and_team(ctx, role)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}}, bag=ctx.player["bag"])


@route("logic.teamHandler.replaceAllArtifact")
def replace_all_artifact(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, src = _get_role(ctx, req)
    tgt_idx = str(req.get("targetTeamIndex") or "")
    tgt = common.role_of(ctx.player, tgt_idx)
    if not src or not tgt:
        return ctx.err("忍者不存在")
    for i in range(1, 6):
        k = f"artifactItem_{i}"
        src["equipments"][k], tgt["equipments"][k] = tgt["equipments"].get(k), src["equipments"].get(k)
    _recalc_role_and_team(ctx, src)
    _recalc_role_and_team(ctx, tgt)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: src, tgt_idx: tgt}})


@route("logic.teamHandler.equipCapsule")
def equip_capsule(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    _equip_one(ctx, role, "capsule", req.get("bagIndex"))
    _recalc_role_and_team(ctx, role)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}}, bag=ctx.player["bag"])


@route("logic.teamHandler.equipAllCapsule")
def equip_all_capsule(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    _equip_all(ctx, role, "capsule")
    _recalc_role_and_team(ctx, role)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}}, bag=ctx.player["bag"])


@route("logic.teamHandler.unEquipCapsule")
def unequip_capsule(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    _unequip_one(ctx, role, str(req.get("equipmentType") or "capsuleItem_1"))
    _recalc_role_and_team(ctx, role)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}}, bag=ctx.player["bag"])


@route("logic.teamHandler.unEquipAllCapsule")
def unequip_all_capsule(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    _unequip_all(ctx, role, "capsule")
    _recalc_role_and_team(ctx, role)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}}, bag=ctx.player["bag"])


@route("logic.teamHandler.equipStarSign")
def equip_star_sign(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    _equip_one(ctx, role, "starSign", req.get("bagIndex"))
    _recalc_role_and_team(ctx, role)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}}, bag=ctx.player["bag"])


@route("logic.teamHandler.equipAllStarSign")
def equip_all_star_sign(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    _equip_all(ctx, role, "starSign")
    _recalc_role_and_team(ctx, role)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}}, bag=ctx.player["bag"])


@route("logic.teamHandler.unEquipStarSign")
def unequip_star_sign(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    _unequip_one(ctx, role, str(req.get("equipmentType") or "starSignItem_1"))
    _recalc_role_and_team(ctx, role)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}}, bag=ctx.player["bag"])


@route("logic.teamHandler.unEquipAllStarSign")
def unequip_all_star_sign(req: dict, session: dict):
    ctx = common.get(session)
    if ctx.error:
        return ctx.error
    tidx, role = _get_role(ctx, req)
    if not role:
        return ctx.err("忍者不存在")
    _unequip_all(ctx, role, "starSign")
    _recalc_role_and_team(ctx, role)
    ctx.save()
    return ctx.ok(team={**ctx.player["team"], "roles": {tidx: role}}, bag=ctx.player["bag"])
