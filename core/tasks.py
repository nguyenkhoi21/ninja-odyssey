"""Task system: main task chain + daily tasks, driven by gamedata/taskData.json."""
import time

import core.gamedata as gd

MAIN_GROUP = 1
DAILY_GROUP = 2


def now_ms():
    return int(time.time() * 1000)


def _task_row(task_id):
    return gd.find("taskData", "kindId", task_id)


def _rows_of_group(group_id):
    return sorted(
        (r for r in gd.table("taskData") if isinstance(r, dict) and r.get("groupId") == group_id),
        key=lambda r: (r.get("rankId") or 0, r.get("kindId") or 0),
    )


def _show_text(task_row, player):
    """Progress text like '1/3' derived from the task's require map."""
    require = task_row.get("require") or {}
    parts = []
    for key, need in require.items():
        have = _require_value(player, key)
        parts.append(f"{min(have, need)}/{need}")
    return ",".join(parts) if parts else "0/1"


def _require_value(player, key):
    reach = {
        "playerLevel": int(player.get("level") or 1),
        "totalPower": int(player.get("power") or 0),
        "roleColor2Count": 0,
        "roleCount": len(player.get("team", {}).get("roles") or {}),
        "smapPassCount": 0,
        "taskActivePoint": int(player.get("task", {}).get("activePoint") or 0),
    }
    return reach.get(key, int(player.get("taskCounters", {}).get(key) or 0))


def _is_complete(task_row, player):
    require = task_row.get("require") or {}
    if not require:
        return False
    for key, need in require.items():
        if _require_value(player, key) < need:
            return False
    return True


def ensure_main_task(player):
    """Keep task.main[1] pointing at the first unfinished main task."""
    task = player.setdefault("task", {})
    main = task.setdefault("main", {})
    received = set(str(x) for x in task.get("receivedIds") or [])

    cur = main.get("1") or {}
    cur_id = cur.get("taskId")
    rows = _rows_of_group(MAIN_GROUP)
    if not rows:
        return main

    if cur_id is None or str(cur_id) in received:
        for row in rows:
            tid = row.get("kindId")
            if str(tid) in received:
                continue
            cur_id = tid
            break
        else:
            cur_id = rows[-1].get("kindId")

    row = _task_row(cur_id)
    if row is None:
        return main
    main["1"] = {
        "taskId": cur_id,
        "isComplete": _is_complete(row, player),
        "show": _show_text(row, player),
        "preRankId": row.get("rankId") or 1,
    }
    return main


def ensure_daily_tasks(player):
    task = player.setdefault("task", {})
    daily = task.setdefault("daily", {})
    received = set(str(x) for x in task.get("receivedIds") or [])
    for row in _rows_of_group(DAILY_GROUP):
        tid = row.get("kindId")
        key = str(tid)
        if key in daily:
            continue
        if key in received:
            daily[key] = {"taskId": tid, "isComplete": True, "show": _show_text(row, player)}
            continue
        daily[key] = {
            "taskId": tid,
            "isComplete": _is_complete(row, player),
            "show": _show_text(row, player),
        }
    return daily


def complete_daily(player, task_id, complete=True, show=None):
    """Mark a daily task complete (called by other systems)."""
    task = player.setdefault("task", {})
    daily = task.setdefault("daily", {})
    key = str(task_id)
    row = _task_row(task_id) or {}
    entry = daily.get(key) or {"taskId": task_id}
    entry["isComplete"] = complete
    entry["show"] = show or ("1/1" if complete else _show_text(row, player))
    daily[key] = entry
    return entry


def claim_task_award(player, task_id):
    """Returns (dropListDesc, error)."""
    task = player.setdefault("task", {})
    received = task.setdefault("receivedIds", [])
    row = _task_row(task_id)
    if row is None:
        return None, "任务不存在"
    key = str(task_id)
    if key in [str(x) for x in received]:
        return None, "奖励已领取"

    main = task.setdefault("main", {})
    daily = task.setdefault("daily", {})
    entry = main.get("1") if (main.get("1") or {}).get("taskId") == task_id else daily.get(key)
    if not entry or not entry.get("isComplete"):
        return None, "任务未完成"

    received.append(task_id)
    if (main.get("1") or {}).get("taskId") == task_id:
        ensure_main_task(player)
    return row.get("dropListDesc") or "", None


def active_point_rewards(player, kind="daily"):
    """Active point milestones (client task.receivedPointMap[kind][point])."""
    received = player.setdefault("task", {}).setdefault("receivedPointMap", {})
    bucket = received.setdefault(kind, {})
    return bucket
