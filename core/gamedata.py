import os
import json
import threading

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(SERVER_DIR, "gamedata")

_TABLES = {}
_BY_KEY = {}
_LOCK = threading.RLock()


def _load(name: str):
    path = os.path.join(DATA_DIR, name + ".json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[-] gamedata {name}: {e}")
        return []


def table(name: str):
    with _LOCK:
        if name not in _TABLES:
            _TABLES[name] = _load(name)
        return _TABLES[name]


def index(name: str, key: str = "kindId"):
    with _LOCK:
        cache_key = name + "|" + key
        if cache_key not in _BY_KEY:
            _BY_KEY[cache_key] = {
                row.get(key): row for row in table(name) if isinstance(row, dict)
            }
        return _BY_KEY[cache_key]


def find(name: str, key: str, value):
    return index(name, key).get(value)


def find_all(name: str, key: str, value):
    return [row for row in table(name) if isinstance(row, dict) and row.get(key) == value]


def first(name: str):
    rows = table(name)
    return rows[0] if rows else None


def available():
    if not os.path.isdir(DATA_DIR):
        return []
    return sorted(f[:-5] for f in os.listdir(DATA_DIR) if f.endswith(".json"))


# ---------- convenience lookups ----------

def role(kind_id):
    return find("roleData", "kindId", kind_id)


def entity(kind_id):
    return find("entityData", "kindId", kind_id)


def smap(smap_id):
    return find("smapData", "kindId", smap_id)


def bmap(bmap_id):
    return find("bmapData", "kindId", bmap_id)


def vip(level):
    return find("vipData", "level", level)


def exp(level):
    return find("experienceData", "level", level)


def smaps_of_bmap(bmap_id):
    return [r for r in table("smapData") if isinstance(r, dict) and r.get("bmapId") == bmap_id]


def bmaps_of_type(bmap_type):
    return [r for r in table("bmapData") if isinstance(r, dict) and r.get("type") == bmap_type]


def role_star_skill_ids(kind_id):
    row = role(kind_id)
    if not row:
        return []
    return list(row.get("skillIds") or [])
