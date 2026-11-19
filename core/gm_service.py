"""Shared GM business logic for both Web GM Panel and in-game GM GiftCodes."""
import re
import time

from core import gamedata as gd
from core import rewards, schema, activity, push
from core.db import save_db, push_mail, next_mail_id, add_role_to_team

SPECIAL_MONEY_IDS = {98, 99, 100, 101, 102}
HIGHLIGHT_ENTITY_IDS = [101, 102, 2, 99, 37, 50030, 50110, 50120, 120, 113, 114, 119]

STONE_TYPES = {"stone", "artifact", "artifactFragment", "starSign", "capsule", "fruit", "fruitFragment"}
MATERIAL_TYPES = {"evolutionItem", "fragment", "shipFragment", "ship", "title", "chatSkin", "frame"}
BOX_TYPES = {"box", "treasure"}
BULK_MATERIAL_TYPES = MATERIAL_TYPES | STONE_TYPES | {"consumables"}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _int_or_none(val):
    if val is None or val == "":
        return None
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return None


def player_brief(db: dict, p: dict) -> dict:
    uid = p.get("userId")
    user_name = p.get("userName") or ""
    for uname, uinfo in (db.get("users") or {}).items():
        if isinstance(uinfo, dict) and uinfo.get("uid") == uid:
            user_name = uname
            break
    pid = int(p.get("id") or 0)
    vip = p.get("vip") or {}
    roles = (p.get("team") or {}).get("roles") or {}
    return {
        "playerId": pid,
        "name": p.get("name", f"Ninja_{pid}"),
        "userName": user_name,
        "uid": int(uid or 0),
        "level": int(p.get("level") or 1),
        "vip": int(vip.get("level") or 0),
        "coin": int(p.get("coin") or 0),
        "gem": int(p.get("gem") or 0),
        "actionPoint": int(p.get("actionPoint") or 0),
        "skillPoint": int(p.get("skillPoint") or 0),
        "power": int(p.get("power") or 0),
        "roleCount": len(roles),
        "online": push.is_online(pid),
    }


def list_players(db: dict) -> list:
    items = [
        player_brief(db, p)
        for p in (db.get("players") or {}).values()
        if isinstance(p, dict) and p.get("id") is not None
    ]
    items.sort(key=lambda x: (not x["online"], -x["level"], x["playerId"]))
    return items


def resolve_player(db: dict, target):
    """Find player dict by playerId, name, userName, or uid."""
    if target is None:
        return None
    raw = str(target).strip()
    if not raw:
        return None
    players = db.get("players") or {}

    if raw in players and isinstance(players[raw], dict):
        return players[raw]

    low = raw.lower()
    for p in players.values():
        if isinstance(p, dict) and str(p.get("name") or "").strip().lower() == low:
            return p
    for p in players.values():
        if isinstance(p, dict) and str(p.get("userName") or "").strip().lower() == low:
            return p

    users = db.get("users") or {}
    matched_uid = None
    for uname, uinfo in users.items():
        if str(uname).strip().lower() == low and isinstance(uinfo, dict):
            matched_uid = uinfo.get("uid")
            break
    if matched_uid is None and raw.isdigit():
        matched_uid = int(raw)
    if matched_uid is not None:
        for p in players.values():
            if isinstance(p, dict) and p.get("userId") == matched_uid:
                return p
    return None


def _catalog_category_for(row: dict) -> str:
    t = row.get("type") or ""
    if t == "role":
        return "role"
    if t == "soul":
        return "soul"
    if t == "money":
        return "money"
    if t in BOX_TYPES:
        return "box"
    if t == "consumables":
        return "consumables"
    if t in STONE_TYPES:
        return "stone"
    return "material"


def _catalog_row(row: dict) -> dict:
    return {
        "kindId": int(row.get("kindId") or 0),
        "kindName": row.get("kindName") or f"Item_{row.get('kindId')}",
        "type": row.get("type") or "item",
        "color": int(row.get("color") or 1),
        "desc": row.get("desc") or "",
        "classId": row.get("classId"),
    }


def search_catalog(query: str = "", category: str = "all", limit: int = 80) -> dict:
    q = str(query or "").strip().lower()
    cat = str(category or "all").strip()
    limit = max(1, min(300, int(limit or 80)))

    entities = [r for r in gd.all_entities() if r.get("type") != "role"]
    roles = gd.base_roles()

    counts = {
        "all": len(entities) + len(roles),
        "soul": 0,
        "role": len(roles),
        "money": 0,
        "box": 0,
        "consumables": 0,
        "stone": 0,
        "material": 0,
    }
    for r in entities:
        c = _catalog_category_for(r)
        counts[c] = counts.get(c, 0) + 1

    if cat == "role":
        pool = roles
    elif cat == "all":
        pool = entities + roles
    elif cat in ("soul", "money", "box", "consumables", "stone", "material"):
        pool = [r for r in entities if _catalog_category_for(r) == cat]
    else:
        pool = [r for r in (entities + roles) if r.get("type") == cat]

    matched = []
    for row in pool:
        if q:
            kid_s = str(row.get("kindId") or "")
            cid_s = str(row.get("classId") or "")
            name_s = str(row.get("kindName") or "").lower()
            desc_s = str(row.get("desc") or "").lower()
            if q not in kid_s and q != cid_s and q not in name_s and q not in desc_s:
                continue
        matched.append(_catalog_row(row))

    if q:
        matched.sort(
            key=lambda x: (
                0 if str(x["kindId"]) == q else (1 if x["kindName"].lower().startswith(q) else 2),
                x["kindId"],
            )
        )
    return {"items": matched[:limit], "total": len(matched), "counts": counts}


def _sync_and_save(db: dict, player: dict, extra_delta=None, push_live: bool = True) -> bool:
    schema.ensure_player_fields(player)
    activity.refresh_activity(player)
    schema.recalc_power(player)
    save_db(db)

    pid = int(player["id"])
    if not push_live or not push.is_online(pid):
        return False

    delta = {
        "coin": player.get("coin", 0),
        "gem": player.get("gem", 0),
        "actionPoint": player.get("actionPoint", 0),
        "skillPoint": player.get("skillPoint", 0),
        "level": player.get("level", 1),
        "experience": player.get("experience", 0),
        "vip": player.get("vip", {}),
        "power": player.get("power", 0),
        "topPower": player.get("topPower", 0),
        "bag": player.get("bag", {}),
        "team": player.get("team", {}),
        "timesMaxMap": player.get("timesMaxMap", {}),
        "activity": {"map": (player.get("activity") or {}).get("map", {})},
    }
    if isinstance(extra_delta, dict):
        delta.update(extra_delta)
    return push.sync(pid, delta)


def _cap_popup_counts(counts: dict, limit: int = 12) -> dict:
    if len(counts) <= limit:
        return dict(counts)
    out = {}
    for eid in HIGHLIGHT_ENTITY_IDS:
        key = str(eid)
        if key in counts:
            out[key] = counts[key]
            if len(out) >= limit:
                return out
    for key, val in counts.items():
        if key not in out:
            out[key] = val
            if len(out) >= limit:
                break
    return out


def _normalize_items(items) -> list:
    clean = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        eid = _int_or_none(it.get("entityId") or it.get("kindId"))
        cnt = _int_or_none(it.get("count") or it.get("itemCount") or 1)
        if not eid or eid <= 0 or not cnt or cnt <= 0:
            continue
        row = {"entityId": eid, "count": cnt}
        if isinstance(it.get("extra"), dict) and it["extra"]:
            row["extra"] = it["extra"]
        clean.append(row)
    return clean


def _send_mails_for_items(db: dict, player: dict, items: list, title: str, body: str) -> dict:
    pid = int(player["id"])
    mails_sent = 0
    total_counts = {}
    chunk_size = 30
    now = _now_ms()
    for i in range(0, len(items), chunk_size):
        batch = items[i: i + chunk_size]
        mail_title = title if len(items) <= chunk_size else f"{title} ({i // chunk_size + 1})"
        mail = {
            "_id": next_mail_id(db),
            "isSys": True,
            "status": 1,
            "type": 1,
            "senderId": 9999999999,
            "senderName": "GM 管理员",
            "title": mail_title,
            "body": body,
            "ctime": now,
            "expireTime": now + 604800000,
            "dropList": rewards.to_drop_list(batch),
            "isReceived": False,
        }
        if push_mail(db, pid, mail):
            mails_sent += 1
            if push.is_online(pid):
                push.new_mail(pid, mail)
        for it in batch:
            k = str(it["entityId"])
            total_counts[k] = total_counts.get(k, 0) + it["count"]

    save_db(db)
    return {
        "mailsSent": mails_sent,
        "itemTypes": len(total_counts),
        "pushed": push.is_online(pid),
        "counts": _cap_popup_counts(total_counts),
    }


def add_items(
    db: dict,
    player: dict,
    items: list,
    via_mail: bool = False,
    title: str = "GM 福利礼包",
    body: str = "来自 GM 的专属福利，请查收！",
    push_live: bool = True,
):
    clean = _normalize_items(items)
    if not clean:
        raise ValueError("Không có vật phẩm hợp lệ để thêm")

    if via_mail:
        res = _send_mails_for_items(db, player, clean, title, body)
        return res, res["counts"]

    counts = rewards.grant_items(player, clean)
    pushed = _sync_and_save(db, player, push_live=push_live)
    popup = _cap_popup_counts(counts)
    return {
        "itemTypes": len(counts),
        "totalAdded": sum(counts.values()),
        "pushed": pushed,
        "counts": popup,
    }, popup


def _resolve_role_row(kind_or_class_id: int):
    val = int(kind_or_class_id)
    if val < 1000:
        for r in gd.base_roles():
            if int(r.get("classId") or 0) == val:
                return r
    row = gd.role(val)
    if row:
        return row
    ent = gd.entity(val)
    if ent and ent.get("type") == "role":
        return {"kindId": val, "classId": val}
    raise ValueError(f"Không tìm thấy tướng với ID/classId={val}")


def add_role(db: dict, player: dict, kind_or_class_id: int, level: int = 1, star: int = 5, push_live: bool = True):
    row = _resolve_role_row(kind_or_class_id)
    kid = int(row["kindId"])
    lv = max(1, min(1000, int(level or 1)))
    st = max(1, min(60, int(star or 5)))

    idx, role = add_role_to_team(player, kid, level=lv, star=st)
    role["level"] = lv
    role["star"] = st
    role["nextLevelExp"] = (gd.exp(lv) or {}).get("roleExp") or lv * 100
    schema.refresh_role(role)
    pushed = _sync_and_save(db, player, push_live=push_live)

    ent = gd.entity(kid) or {}
    role_name = ent.get("kindName") or f"Role_{kid}"
    return {
        "teamIndex": idx,
        "kindId": kid,
        "roleName": role_name,
        "level": lv,
        "star": st,
        "pushed": pushed,
        "role": role,
    }


def _vip_unlock_gem(vip_level: int) -> int:
    if vip_level <= 0:
        return 0
    prev = gd.vip(vip_level - 1)
    if prev and isinstance(prev.get("nextLevelTopUpGem"), (int, float)):
        return int(prev["nextLevelTopUpGem"])
    return vip_level * 1000


def set_stats(
    db: dict,
    player: dict,
    coin=None,
    gem=None,
    action_point=None,
    skill_point=None,
    level=None,
    vip_level=None,
    mode: str = "add",
    push_live: bool = True,
):
    is_set = (str(mode or "add").lower() == "set")
    popup = {}

    c_val = _int_or_none(coin)
    if c_val is not None:
        player["coin"] = max(0, c_val if is_set else int(player.get("coin") or 0) + c_val)
        popup["101"] = max(1, c_val)

    g_val = _int_or_none(gem)
    if g_val is not None:
        player["gem"] = max(0, g_val if is_set else int(player.get("gem") or 0) + g_val)
        popup["102"] = max(1, g_val)

    ap_val = _int_or_none(action_point)
    if ap_val is not None:
        player["actionPoint"] = max(0, ap_val if is_set else int(player.get("actionPoint") or 0) + ap_val)
        popup["99"] = max(1, ap_val)

    sp_val = _int_or_none(skill_point)
    if sp_val is not None:
        player["skillPoint"] = max(0, sp_val if is_set else int(player.get("skillPoint") or 0) + sp_val)

    lv_val = _int_or_none(level)
    if lv_val is not None:
        new_lv = lv_val if is_set else int(player.get("level") or 1) + lv_val
        new_lv = max(1, min(500, new_lv))
        player["level"] = new_lv
        player.setdefault("timesMaxMap", {})["actionPoint"] = max(120, 120 + new_lv * 2)
        player["timesMaxMap"].setdefault("skillPoint", 10)

    vip_val = _int_or_none(vip_level)
    if vip_val is not None:
        new_vip = max(0, min(16, vip_val))
        vip = player.setdefault("vip", {})
        vip["level"] = new_vip
        need_gem = _vip_unlock_gem(new_vip)
        if int(vip.get("topUpGem") or 0) < need_gem:
            vip["topUpGem"] = need_gem
        if new_vip > 0:
            vip["topUpMoney"] = max(int(vip.get("topUpMoney") or 0), max(100, need_gem // 10))
            vip["topUpTrueMoney"] = max(int(vip.get("topUpTrueMoney") or 0), vip["topUpMoney"])

    pushed = _sync_and_save(db, player, push_live=push_live)
    return {"pushed": pushed, "player": player_brief(db, player)}, popup


def _items_for_types(types: set, count: int, exclude_ids=()):
    excl = set(exclude_ids or ())
    return [
        {"entityId": int(row["kindId"]), "count": count}
        for row in gd.all_entities()
        if row.get("type") in types and int(row.get("kindId") or 0) not in excl
    ]


def apply_preset(db: dict, player: dict, preset: str, via_mail: bool = False, push_live: bool = True):
    name = str(preset or "").strip().lower()
    popup = {}

    if name == "gold":
        info, popup = add_items(db, player, [{"entityId": 101, "count": 100000000}], via_mail=via_mail, title="GM 巨额金币", push_live=push_live)
        return f"Đã thêm 100.000.000 Vàng cho {player['name']}", info, popup

    if name == "diamond":
        info, popup = add_items(
            db,
            player,
            [{"entityId": 102, "count": 1000000}, {"entityId": 2, "count": 100000}],
            via_mail=via_mail,
            title="GM 钻石代金券礼包",
            push_live=push_live,
        )
        return f"Đã thêm 1.000.000 Kim Cương & 100.000 Phiếu thay thế cho {player['name']}", info, popup

    if name == "vit":
        items = [
            {"entityId": 99, "count": 99999},
            {"entityId": 21003, "count": 999},
            {"entityId": 22001, "count": 999},
        ]
        set_stats(db, player, skill_point=9999, mode="add", push_live=False)
        info, popup = add_items(db, player, items, via_mail=via_mail, title="GM 体力补给礼包", push_live=push_live)
        return f"Đã thêm 99.999 Thể Lực, 9.999 Điểm KN, 999 Ramen & Sách KN cho {player['name']}", info, popup

    if name == "vip":
        info, popup = set_stats(db, player, vip_level=16, mode="set", push_live=push_live)
        return f"Đã mở khóa Max VIP 16 cho {player['name']}", info, popup

    if name == "level100":
        info, popup = set_stats(db, player, level=100, mode="set", push_live=push_live)
        return f"Đã nâng cấp tài khoản {player['name']} lên Level 100", info, popup

    if name == "currency":
        items = _items_for_types({"money"}, 99999, exclude_ids=SPECIAL_MONEY_IDS)
        info, popup = add_items(db, player, items, via_mail=via_mail, title="GM 全币种/SP卷轴礼包", push_live=push_live)
        return f"Đã thêm {len(items)} loại Tiền Tệ / Cuộn SP / Vé quay x99.999", info, popup

    if name == "soul":
        items = _items_for_types({"soul"}, 2000)
        info, popup = add_items(db, player, items, via_mail=via_mail, title="GM 全忍者灵魂石礼包", push_live=push_live)
        return f"Đã thêm {len(items)} loại Hồn Tướng x2.000", info, popup

    if name == "box":
        items = _items_for_types(BOX_TYPES, 999)
        info, popup = add_items(db, player, items, via_mail=via_mail, title="GM 全宝箱礼包", push_live=push_live)
        return f"Đã thêm {len(items)} loại Rương & Bảo vật x999", info, popup

    if name == "materials":
        items = _items_for_types(BULK_MATERIAL_TYPES, 999)
        info, popup = add_items(db, player, items, via_mail=via_mail, title="GM 全材料/神石/神器礼包", push_live=push_live)
        return f"Đã thêm {len(items)} loại Nguyên liệu / Đá / Thần khí x999", info, popup

    if name == "all_roles":
        roles_map = (player.get("team") or {}).get("roles") or {}
        owned_classes = {
            int(r.get("classId") or 0)
            for r in roles_map.values()
            if isinstance(r, dict) and r.get("classId")
        }
        lv = max(1, int(player.get("level") or 1))
        added = 0
        for row in gd.base_roles():
            cid = int(row.get("classId") or 0)
            if cid in owned_classes:
                continue
            add_role_to_team(player, int(row["kindId"]), level=lv, star=5)
            added += 1
        pushed = _sync_and_save(db, player, push_live=push_live)
        return (
            f"Đã mở khóa thêm {added} tướng 5★ (tổng {len(player['team']['roles'])} tướng)",
            {"addedRoles": added, "pushed": pushed},
            {"101": 1},
        )

    if name == "max_team":
        roles_map = (player.get("team") or {}).get("roles") or {}
        target_lv = max(100, int(player.get("level") or 1))
        updated = 0
        for role in roles_map.values():
            if not isinstance(role, dict):
                continue
            role["level"] = max(int(role.get("level") or 1), target_lv)
            role["star"] = max(int(role.get("star") or 1), 5)
            role["awakeLevel"] = max(int(role.get("awakeLevel") or 0), 10)
            role["nextLevelExp"] = (gd.exp(role["level"]) or {}).get("roleExp") or role["level"] * 100
            schema.refresh_role(role)
            updated += 1
        pushed = _sync_and_save(db, player, push_live=push_live)
        return f"Đã nâng tối đa {updated} tướng trong đội hình (Lv.{target_lv}, 5★)", {"updatedRoles": updated, "pushed": pushed}, {}

    if name == "full":
        set_stats(db, player, vip_level=16, skill_point=9999, mode="set", push_live=False)
        items = [
            {"entityId": 101, "count": 100000000},
            {"entityId": 102, "count": 1000000},
            {"entityId": 2, "count": 100000},
            {"entityId": 99, "count": 99999},
        ]
        items.extend(_items_for_types({"money"}, 99999, exclude_ids=SPECIAL_MONEY_IDS))
        items.extend(_items_for_types({"soul"}, 2000))
        items.extend(_items_for_types(BOX_TYPES, 999))
        items.extend(_items_for_types(BULK_MATERIAL_TYPES, 999))
        info, popup = add_items(db, player, items, via_mail=via_mail, title="GM 终极豪华大礼包", push_live=push_live)
        return (
            f"FULL PACK thành công cho {player['name']}: VIP16, +100M Vàng, +1M KC, +99K Thể Lực & {len(items)} loại vật phẩm!",
            info,
            popup,
        )

    raise ValueError(f"Preset GM không hợp lệ: {preset}")


_PRESET_CODES = {
    "GMGOLD": "gold",
    "TESTGOLD": "gold",
    "GMGEM": "diamond",
    "GMDIAMOND": "diamond",
    "TESTGEM": "diamond",
    "GMVIT": "vit",
    "GMAP": "vit",
    "TESTVIT": "vit",
    "GMSOUL": "soul",
    "GMHERO": "soul",
    "TESTHERO": "soul",
    "GMALLROLE": "all_roles",
    "GMROLEALL": "all_roles",
    "GMBOX": "box",
    "TESTBOX": "box",
    "GMCOIN": "currency",
    "GMCURRENCY": "currency",
    "TESTCOIN": "currency",
    "GMMAXTEAM": "max_team",
    "GMFULL": "full",
    "TESTALL": "full",
    "GMALL": "full",
}


def try_execute_gm_giftcode(db: dict, player: dict, raw_code: str):
    """Execute repeatable GM GiftCode commands.

    Returns `(handled: bool, popup_counts: dict, message: str)`.
    """
    code_str = str(raw_code or "").strip()
    if not code_str:
        return False, {}, ""

    parts = [p for p in re.split(r"[\s_:]+", code_str) if p]
    cmd = parts[0].upper()

    if cmd in _PRESET_CODES:
        msg, _, popup = apply_preset(db, player, _PRESET_CODES[cmd], via_mail=False, push_live=False)
        return True, popup, msg

    if cmd in ("GMITEM", "TESTITEM"):
        items = (
            _items_for_types({"money"}, 99999, exclude_ids=SPECIAL_MONEY_IDS)
            + _items_for_types(BOX_TYPES, 999)
            + _items_for_types(BULK_MATERIAL_TYPES, 999)
        )
        _, popup = add_items(db, player, items, via_mail=False, push_live=False)
        return True, popup, f"Đã phát {len(items)} loại vật phẩm & rương"

    if cmd in ("GMVIP", "TESTVIP"):
        lv = _int_or_none(parts[1]) if len(parts) >= 2 else 16
        lv = 16 if lv is None else max(0, min(16, lv))
        set_stats(db, player, vip_level=lv, mode="set", push_live=False)
        return True, {"98": max(1, lv)}, f"VIP {lv}"

    if cmd == "GMLEVEL":
        lv = _int_or_none(parts[1]) if len(parts) >= 2 else 100
        lv = 100 if lv is None else max(1, min(500, lv))
        set_stats(db, player, level=lv, mode="set", push_live=False)
        return True, {"100": lv}, f"Level {lv}"

    if cmd == "GMADD" and len(parts) >= 2:
        eid = _int_or_none(parts[1])
        cnt = _int_or_none(parts[2]) if len(parts) >= 3 else 1
        if eid and eid > 0:
            cnt = max(1, cnt or 1)
            _, popup = add_items(db, player, [{"entityId": eid, "count": cnt}], via_mail=False, push_live=False)
            return True, popup, f"Added {eid}x{cnt}"

    if cmd == "GMROLE" and len(parts) >= 2:
        rid = _int_or_none(parts[1])
        star = _int_or_none(parts[2]) if len(parts) >= 3 else 5
        if rid and rid > 0:
            try:
                res = add_role(db, player, rid, level=max(1, int(player.get("level") or 1)), star=star or 5, push_live=False)
                return True, {str(res["kindId"]): 1}, res["roleName"]
            except ValueError:
                pass

    if cmd == "GMMAIL" and len(parts) >= 2:
        eid = _int_or_none(parts[1])
        cnt = _int_or_none(parts[2]) if len(parts) >= 3 else 1
        if eid and eid > 0:
            cnt = max(1, cnt or 1)
            _, popup = add_items(db, player, [{"entityId": eid, "count": cnt}], via_mail=True)
            return True, popup, f"Mailed {eid}x{cnt}"

    return False, {}, ""


def list_giftcode_commands() -> list:
    return [
        {"code": "GMFULL", "alias": "TESTALL, GMALL", "desc": "Max VIP 16, +100M Vàng, +1M KC, +99K Thể lực, Full tiền tệ/cuộn SP, Full 84 hồn tướng x2000, Full rương & nguyên liệu x999"},
        {"code": "GMGOLD", "alias": "TESTGOLD", "desc": "Thêm 100.000.000 Vàng"},
        {"code": "GMGEM", "alias": "GMDIAMOND, TESTGEM", "desc": "Thêm 1.000.000 Kim Cương & 100.000 Phiếu thay thế"},
        {"code": "GMVIT", "alias": "GMAP, TESTVIT", "desc": "Thêm 99.999 Thể lực, 9.999 Điểm KN, 999 Ramen & Sách KN"},
        {"code": "GMVIP", "alias": "TESTVIP, GMVIP 16", "desc": "Mở khóa VIP (mặc định VIP 16, hoặc ghi GMVIP <0..16>)"},
        {"code": "GMLEVEL 100", "alias": "GMLEVEL", "desc": "Đặt cấp độ tài khoản (mặc định 100)"},
        {"code": "GMSOUL", "alias": "GMHERO, TESTHERO", "desc": "Thêm 2.000 Hồn cho toàn bộ 84 tướng"},
        {"code": "GMALLROLE", "alias": "GMROLEALL", "desc": "Mở khóa toàn bộ 84 tướng 5★ chưa sở hữu"},
        {"code": "GMMAXTEAM", "alias": "-", "desc": "Nâng tối đa tất cả tướng trong đội (Lv.100+, 5★, Thức tỉnh 10)"},
        {"code": "GMCOIN", "alias": "GMCURRENCY, TESTCOIN", "desc": "Thêm 99.999 toàn bộ tiền tệ shop, cuộn SP (21..50), vé quay, phù văn"},
        {"code": "GMBOX", "alias": "TESTBOX", "desc": "Thêm 999 toàn bộ Rương & Bảo vật"},
        {"code": "GMITEM", "alias": "TESTITEM", "desc": "Thêm toàn bộ Nguyên liệu, Đá, Thần khí, Rương & Tiền tệ"},
        {"code": "GMADD <id> [sl]", "alias": "VD: GMADD 50030 500", "desc": "Thêm vật phẩm/hồn tướng bất kỳ theo kindId"},
        {"code": "GMROLE <id> [sao]", "alias": "VD: GMROLE 82 5", "desc": "Thêm tướng theo classId (1..84) hoặc kindId và số sao"},
        {"code": "GMMAIL <id> [sl]", "alias": "VD: GMMAIL 102 9999", "desc": "Gửi vật phẩm qua hộp thư hệ thống"},
    ]
