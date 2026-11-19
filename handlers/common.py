"""Shared helpers for handler modules."""
import time

from core.db import load_db, save_db
from core import session as sess
from core import schema
from core import rewards
from core import gamedata as gd
from core import push


def now_ms():
    return int(time.time() * 1000)


class Ctx:
    """Per-request context: db handle + the calling player."""

    __slots__ = ("db", "player", "session", "error")

    def __init__(self, db, player, session, error=None):
        self.db = db
        self.player = player
        self.session = session
        self.error = error

    def ok(self, **kw):
        res = {"code": 200}
        res.update(kw)
        return res

    def err(self, msg, code=500):
        return {"code": code, "msg": msg}

    def temp(self, **kw):
        t = {}
        t.update(kw)
        return t

    def save(self):
        save_db(self.db)

    def grant(self, items, temp_key="entityCountMap"):
        """Apply drops to the player and return a temp dict entry."""
        counts = rewards.grant_items(self.player, items)
        schema.recalc_power(self.player)
        return counts, {temp_key: counts} if counts else {}


def get(session, require=True):
    db = load_db()
    player = sess.current_player(db, session)
    if player is None:
        if require:
            return Ctx(db, None, session, {"code": 500, "msg": "未登录"})
        return Ctx(db, None, session, None)
    return Ctx(db, player, session)


def role_of(player, team_index):
    roles = player.get("team", {}).get("roles", {})
    role = roles.get(str(team_index))
    if isinstance(role, dict):
        schema.ensure_role_fields(role)
    return role


def team_payload(player):
    return {"team": player.get("team", {})}


def bag_payload(player):
    return {"bag": player.get("bag", {"items": {}, "lastIdx": 0})}


def sync_push(player, **payload):
    """Push a delta to the player's own connection."""
    try:
        push.sync(player.get("id"), payload)
    except Exception:
        pass


def drop_desc_items(desc):
    return rewards.parse_drop_desc(desc)


def level_exp(level):
    row = gd.exp(level) or {}
    return int(row.get("roleExp") or 0)


def player_level_exp(level):
    row = gd.exp(level) or {}
    return int(row.get("playerExp") or 0)


def add_player_exp(ctx, amount, max_level=100):
    p = ctx.player
    p["experience"] = int(p.get("experience") or 0) + int(amount)
    while int(p.get("level") or 1) < max_level:
        need = player_level_exp(int(p.get("level") or 1))
        if need <= 0 or p["experience"] < need:
            break
        p["experience"] -= need
        p["level"] = int(p.get("level") or 1) + 1
    return p["level"]


def add_role_exp(role, amount, max_level=100):
    role["experience"] = int(role.get("experience") or 0) + int(amount)
    changed = False
    while int(role.get("level") or 1) < max_level:
        need = int(role.get("nextLevelExp") or level_exp(role.get("level", 1)) or 0)
        if need <= 0 or role["experience"] < need:
            break
        role["experience"] -= need
        role["level"] = int(role.get("level") or 1) + 1
        role["nextLevelExp"] = level_exp(role["level"])
        changed = True
    if changed:
        schema.refresh_role(role)
    return changed
