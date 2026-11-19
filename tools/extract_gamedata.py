"""Extract Cocos Creator data tables (data/*.bin) from apk_root into server/gamedata/.

Usage:
    python tools/extract_gamedata.py            # extract all tables
    python tools/extract_gamedata.py --list     # list table names only
"""
import os
import io
import sys
import json
import zlib
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(HERE)
BUILD_DIR = os.path.dirname(SERVER_DIR)
ASSETS = os.path.join(BUILD_DIR, "apk_root", "assets", "assets")
OUT_DIR = os.path.join(SERVER_DIR, "gamedata")

B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
HEX = "0123456789abcdef"


def decompress_uuid(s: str) -> str:
    if len(s) != 22:
        return s
    out = [s[0], s[1]]
    for i in range(2, 22, 2):
        lhs = B64.index(s[i])
        rhs = B64.index(s[i + 1])
        out.append(HEX[lhs >> 2])
        out.append(HEX[((lhs & 3) << 2) | (rhs >> 4)])
        out.append(HEX[rhs & 0xF])
    h = "".join(out)
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def load_config():
    path = os.path.join(ASSETS, "resources", "config.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def table_uuids(cfg):
    paths = cfg["paths"]
    uuids = cfg["uuids"]
    out = {}
    for key, val in paths.items():
        if not isinstance(val, list) or not val or not isinstance(val[0], str):
            continue
        p = val[0]
        if not p.startswith("data/"):
            continue
        name = p.split("/", 1)[1]
        idx = int(key)
        if idx >= len(uuids):
            continue
        out[name] = decompress_uuid(uuids[idx])
    return out


def read_bin(uuid: str):
    p = os.path.join(ASSETS, "resources", "native", uuid[:2], uuid + ".bin")
    if not os.path.exists(p):
        return None
    with open(p, "rb") as f:
        raw = f.read()
    if raw[:2] == b"\x1f\x8b":
        raw = zlib.decompress(raw, 16 + 15)
    txt = raw.decode("utf-8", errors="replace")
    body = txt[:-64]
    try:
        return json.loads(body)
    except Exception:
        return None


def to_rows(table):
    """Cocos data tables are [header, row, row, ...] arrays."""
    if not isinstance(table, list) or not table:
        return []
    header = table[0]
    if not isinstance(header, list):
        return table
    rows = []
    for row in table[1:]:
        if not isinstance(row, list):
            continue
        rows.append({header[i]: (row[i] if i < len(row) else None) for i in range(len(header))})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    tables = table_uuids(cfg)
    if args.list:
        for name in sorted(tables):
            print(name)
        print(f"# {len(tables)} tables", file=sys.stderr)
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    written = 0
    for name, uuid in sorted(tables.items()):
        data = read_bin(uuid)
        if data is None:
            print(f"[-] {name}: missing or unreadable ({uuid})")
            continue
        rows = to_rows(data)
        out_path = os.path.join(OUT_DIR, name + ".json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, separators=(",", ":"))
        written += 1
        print(f"[+] {name}: {len(rows)} rows")
    print(f"[=] wrote {written} tables to {OUT_DIR}")


if __name__ == "__main__":
    main()
