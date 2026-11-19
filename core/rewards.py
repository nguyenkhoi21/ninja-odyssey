"""Drop-list parsing shared by mail, tasks, activities, activities rewards, etc."""
import random

import core.gamedata as gd


_SOUL_BY_CLASS_CACHE = None
_EQUIVALENT_SOULS = {1: 10, 2: 30, 3: 80, 4: 180, 5: 330}


def soul_kind_for_class(cid: int) -> int:
    global _SOUL_BY_CLASS_CACHE
    if _SOUL_BY_CLASS_CACHE is None:
        _SOUL_BY_CLASS_CACHE = {
            int(r["classId"]): int(r["kindId"])
            for r in gd.table("soulData")
            if isinstance(r, dict) and r.get("classId") is not None and r.get("kindId") is not None
        }
    return _SOUL_BY_CLASS_CACHE.get(int(cid or 0), 20001)


def equivalent_souls_count(star: int) -> int:
    return _EQUIVALENT_SOULS.get(int(star or 1), 10 * max(1, int(star or 1)))


def parse_drop_desc(desc: str):
    """Parse '101x50000,20002x2,100301_star_2x1' into [{entityId, count, extra}]."""
    out = []
    if not desc or not isinstance(desc, str):
        return out
    for part in desc.split(","):
        part = part.strip()
        if not part:
            continue
        extra = {}
        entity_part = part
        # star suffix: 100301_star_2x1
        if "_star_" in entity_part:
            head, tail = entity_part.split("_star_", 1)
            star_val, _, rest = tail.partition("x")
            try:
                extra["star"] = int(star_val)
            except ValueError:
                extra["star"] = 1
            entity_part = head + "x" + (rest or "1")
        if "x" not in entity_part:
            continue
        eid_s, cnt_s = entity_part.rsplit("x", 1)
        try:
            eid = int(float(eid_s))
            cnt = int(float(cnt_s))
        except ValueError:
            continue
        row = {"entityId": eid, "count": cnt}
        if extra:
            row["extra"] = extra
        out.append(row)
    return out


def roll_drop_class(class_id: int, times: int = 1, _depth: int = 0):
    """Roll from dropData by classId+groupId using weight."""
    if _depth > 5:
        return []
    rows = [r for r in gd.table("dropData") if isinstance(r, dict) and r.get("classId") == class_id]
    if not rows:
        return []
    results = []
    for _ in range(times):
        total = sum(max(1, int(r.get("weight") or 1)) for r in rows)
        pick = random.randint(1, total)
        acc = 0
        for r in rows:
            acc += max(1, int(r.get("weight") or 1))
            if pick <= acc:
                eid = int(r.get("entityId") or 0)
                ref_cid = int(r.get("refClassId") or 0)
                cnt = max(1, int(r.get("count") or 1))
                if eid:
                    extra = r.get("extra")
                    item = {"entityId": eid, "count": cnt}
                    if isinstance(extra, dict) and extra:
                        item["extra"] = extra
                    results.append(item)
                elif ref_cid:
                    for _ in range(cnt):
                        results.extend(roll_drop_class(ref_cid, 1, _depth + 1))
                break
    return results


def merge_drops(items):
    """Aggregate identical entity ids into one entry (client reward display)."""
    merged = {}
    order = []
    for it in items:
        key = (it["entityId"], json_key(it.get("extra")))
        if key not in merged:
            merged[key] = dict(it)
            order.append(key)
        else:
            merged[key]["count"] += it.get("count", 0)
    return [merged[k] for k in order]


def json_key(value):
    if value is None:
        return None
    if isinstance(value, dict):
        return tuple(sorted((k, json_key(v)) for k, v in value.items()))
    if isinstance(value, list):
        return tuple(json_key(v) for v in value)
    return value


def to_entity_count_map(items):
    """entityCountMap uses str(entityId) -> count, with role stars flattened per entity."""
    out = {}
    for it in items:
        key = str(it["entityId"])
        out[key] = out.get(key, 0) + int(it.get("count") or 0)
    return out


def to_drop_list(items):
    out = []
    for it in items:
        row = {"entityId": it["entityId"], "count": it.get("count", 1)}
        if isinstance(it.get("extra"), dict):
            row["extra"] = it["extra"]
        else:
            row["extra"] = 0
        out.append(row)
    return out


def grant_items(player: dict, items):
    """Apply drops to the player's economy (coins/gems/items) and return entityCountMap."""
    from core.db import add_item_to_bag

    counts = {}
    for it in items:
        eid = int(it.get("entityId") or 0)
        cnt = int(it.get("count") or 0)
        if not eid or cnt <= 0:
            continue
        row = gd.entity(eid) or {}
        etype = row.get("type")
        if eid == 101:
            player["coin"] = player.get("coin", 0) + cnt
        elif eid == 102:
            player["gem"] = player.get("gem", 0) + cnt
        elif eid == 100:
            player["experience"] = player.get("experience", 0) + cnt
        elif eid == 99:
            player["actionPoint"] = player.get("actionPoint", 0) + cnt
        elif eid == 98:
            vip = player.setdefault("vip", {})
            vip["topUpGem"] = vip.get("topUpGem", 0) + cnt
        elif etype == "role":
            from core.db import add_role_to_team
            extra = it.get("extra")
            star = max(1, int(extra.get("star") or 1)) if isinstance(extra, dict) and extra.get("star") else 1
            role_row = gd.role(eid) or {}
            cid = int(role_row.get("classId") or 0)
            roles_map = (player.get("team") or {}).get("roles") or {}
            owned_cids = {
                int(r.get("classId") or (gd.role(r.get("kindId")) or {}).get("classId") or 0)
                for r in roles_map.values()
                if isinstance(r, dict)
            }
            new_roles = player.setdefault("_lastNewRoles", {})
            for _ in range(cnt):
                if cid and cid in owned_cids:
                    soul_kid = soul_kind_for_class(cid)
                    soul_cnt = equivalent_souls_count(star)
                    add_item_to_bag(player, soul_kid, soul_cnt)
                else:
                    idx, role = add_role_to_team(player, eid, level=1, star=star)
                    new_roles[idx] = role
                    if cid:
                        owned_cids.add(cid)
        else:
            add_item_to_bag(player, eid, cnt)
        counts[str(eid)] = counts.get(str(eid), 0) + cnt
    return counts
