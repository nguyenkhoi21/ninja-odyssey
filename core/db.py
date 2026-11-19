import os
import json
import time
import threading
import urllib.request
import urllib.error
from datetime import datetime, timezone

from core import schema

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(SERVER_DIR, ".env")
DB_PATH = os.path.join(SERVER_DIR, "local_db.json")
_LOCK = threading.RLock()


def load_dotenv():
    """Load key = value pairs from server/.env without overriding existing env vars."""
    if not os.path.exists(ENV_PATH):
        return
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
SUPABASE_TABLE = os.environ.get("SUPABASE_TABLE", "players")
SUPABASE_ROW_ID = os.environ.get("SUPABASE_ROW_ID", "NARUTO_ODYSSES_STATE")

_DIRTY = False
_SYNC_TIMER = None
_DB_CACHE = None


def _default_db():
    return {
        "next_uid": 55924,
        "next_pid": 178471,
        "next_guild_id": 11188,
        "users": {},
        "players": {},
        "guilds": {},
        "rank": {"power": [], "arena": [], "endless": {}, "smap": {}},
        "mail_seq": 1,
        "guild_seq": 1,
        "chat": {"world": [], "guild": {}, "allServer": []},
        "reports": {},
        "videos": {},
        "activity_state": {},
        "guild_battle": {},
        "world_boss": {},
        "seasons": {},
    }


def load_db():
    global _DB_CACHE
    with _LOCK:
        if _DB_CACHE is not None:
            return _DB_CACHE
        if os.path.exists(DB_PATH):
            try:
                with open(DB_PATH, "r", encoding="utf-8") as f:
                    _DB_CACHE = json.load(f)
                    _fill_db_defaults(_DB_CACHE)
                    return _DB_CACHE
            except Exception as e:
                print(f"[-] Error reading local_db.json: {e}")
        _DB_CACHE = _default_db()
        return _DB_CACHE


def _fill_db_defaults(db):
    for key, value in _default_db().items():
        if key not in db or db[key] is None:
            db[key] = value
        elif isinstance(value, dict) and isinstance(db[key], dict):
            for sk, sv in value.items():
                db[key].setdefault(sk, sv)
    return db


def save_local_db(db=None):
    global _DB_CACHE
    with _LOCK:
        if db is None:
            db = load_db()
        _DB_CACHE = db
        tmp = DB_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, DB_PATH)


def _supabase_request(api_path: str, method: str = "GET", body=None, timeout: int = 8):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None, 0
    url = f"{SUPABASE_URL}{api_path}"
    data_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return (json.loads(raw) if raw else None), resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        print(f"[-] Supabase HTTP {e.code} on {api_path}: {raw[:200]}")
        return None, e.code
    except Exception as e:
        print(f"[-] Supabase request error: {e}")
        return None, 0


def load_db_from_supabase():
    global _DB_CACHE
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("[*] SUPABASE_URL / SUPABASE_KEY not set -> running in local JSON mode.")
        return load_db()
    print(f"[*] Loading cloud DB from Supabase ({SUPABASE_URL}) ...")
    rows, status = _supabase_request(
        f"/rest/v1/{SUPABASE_TABLE}?player_id=eq.{SUPABASE_ROW_ID}&select=player_id,data",
        "GET",
    )
    with _LOCK:
        db = load_db()
        if status == 200 and isinstance(rows, list) and rows:
            cloud_data = rows[0].get("data")
            if isinstance(cloud_data, dict):
                for key in (
                    "users", "players", "guilds", "rank", "chat", "reports", "videos",
                    "tokens", "activity_state", "guild_battle", "world_boss", "seasons",
                ):
                    if isinstance(cloud_data.get(key), dict):
                        db.setdefault(key, {}).update(cloud_data[key])
                for num_k in ("next_uid", "next_pid", "next_guild_id", "mail_seq", "guild_seq"):
                    if isinstance(cloud_data.get(num_k), int):
                        db[num_k] = max(db.get(num_k, 0), cloud_data[num_k])
                _DB_CACHE = db
                save_local_db(db)
                print(
                    f"[+] Synced cloud state from Supabase: "
                    f"{len(db.get('users', {}))} users, {len(db.get('players', {}))} players"
                )
        else:
            print(f"[*] No existing cloud row '{SUPABASE_ROW_ID}' (status={status}); using local DB.")
        return db


def flush_to_supabase():
    global _DIRTY
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    with _LOCK:
        if not _DIRTY:
            return True
        snapshot = json.loads(json.dumps(load_db(), ensure_ascii=False))
        _DIRTY = False
    payload = [
        {
            "player_id": SUPABASE_ROW_ID,
            "data": snapshot,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    ]
    _, status = _supabase_request(f"/rest/v1/{SUPABASE_TABLE}", "POST", payload)
    if status in (200, 201, 204):
        print(f"[+] Synced state ({len(snapshot.get('players', {}))} players) to Supabase.")
        return True
    with _LOCK:
        _DIRTY = True
    return False


def _schedule_supabase_flush():
    global _SYNC_TIMER
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    with _LOCK:
        if _SYNC_TIMER is not None:
            return

        def _worker():
            global _SYNC_TIMER
            with _LOCK:
                _SYNC_TIMER = None
            flush_to_supabase()

        _SYNC_TIMER = threading.Timer(1.5, _worker)
        _SYNC_TIMER.daemon = True
        _SYNC_TIMER.start()


def start_db_sync_loop(interval_sec: float = 10.0):
    def _loop():
        while True:
            time.sleep(interval_sec)
            try:
                flush_to_supabase()
            except Exception:
                pass

    t = threading.Thread(target=_loop, daemon=True)
    t.start()


def save_db(db=None):
    global _DIRTY
    with _LOCK:
        save_local_db(db)
        _DIRTY = True
    _schedule_supabase_flush()


# ---------- lookups / factories (kept for handler compatibility) ----------

make_role = schema.make_role
ensure_role_fields = schema.ensure_role_fields
make_default_player = schema.make_default_player
ensure_player_fields = schema.ensure_player_fields
recalc_power = schema.recalc_power


def get_player(db, pid):
    key = str(pid)
    p = db["players"].get(key)
    if not p:
        num_pid = int(pid) if str(pid).isdigit() else db.get("next_pid", 178471)
        p = make_default_player(num_pid, 0, f"Ninja_{num_pid}")
        db["players"][key] = p
        save_db(db)
    else:
        ensure_player_fields(p)
    return p


def find_player_by_id(db, pid):
    return db["players"].get(str(pid))


def add_item_to_bag(player: dict, kind_id: int, count: int = 1):
    bag = player.setdefault("bag", {"items": {}, "lastIdx": 0})
    items = bag.setdefault("items", {})
    for idx, item in items.items():
        if item and item.get("kindId") == kind_id and not item.get("expireTime"):
            item["count"] = item.get("count", 0) + count
            return idx, bag
    new_idx = str(bag.get("lastIdx", 0) + 1)
    bag["lastIdx"] = int(new_idx)
    items[new_idx] = {"kindId": kind_id, "count": count}
    return new_idx, bag


def remove_item_from_bag(player: dict, idx, count: int = 1):
    bag = player.setdefault("bag", {"items": {}, "lastIdx": 0})
    key = str(idx)
    item = bag.get("items", {}).get(key)
    if not item:
        return False
    have = int(item.get("count") or 0)
    if have < count:
        return False
    left = have - count
    if left <= 0:
        bag["items"][key] = None
    else:
        item["count"] = left
    return True


def add_role_to_team(player: dict, kind_id: int, level: int = 1, star: int = 1):
    team = player.setdefault(
        "team", {"roles": {}, "indexs": ["0"] * 5, "lastIdx": 0}
    )
    roles = team.setdefault("roles", {})
    new_idx = str(team.get("lastIdx", 0) + 1)
    team["lastIdx"] = int(new_idx)
    roles[new_idx] = make_role(kind_id, level=level, star=star)

    indexs = team.get("indexs") or []
    for i, cur in enumerate(indexs):
        if str(cur) == "0":
            indexs[i] = new_idx
            break
    team["indexs"] = (indexs + ["0"] * 5)[:5]
    recalc_power(player)
    return new_idx, roles[new_idx]


def next_mail_id(db):
    with _LOCK:
        seq = db.get("mail_seq", 1)
        db["mail_seq"] = seq + 1
        return seq


def push_mail(db, player_id, mail: dict):
    p = find_player_by_id(db, player_id)
    if not p:
        return None
    mail = dict(mail)
    mail.setdefault("_id", next_mail_id(db))
    mail.setdefault("ctime", int(time.time() * 1000))
    mail.setdefault("status", 1)
    mail.setdefault("isSys", True)
    mail.setdefault("dropList", [])
    mail.setdefault("senderName", "系统")
    mail.setdefault("title", "系统邮件")
    mail.setdefault("body", "")
    p.setdefault("extra", {}).setdefault("mails", []).insert(0, mail)
    return mail
