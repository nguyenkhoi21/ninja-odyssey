import os
import re
import sys
import glob
import json
from collections import Counter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(os.path.dirname(BASE_DIR), "logs")
OUT_PACKETS = os.path.join(BASE_DIR, "captured_packets.json")
OUT_ROUTES = os.path.join(BASE_DIR, "route_templates.json")


def count_braces(s: str) -> int:
    in_str = False
    esc = False
    d = 0
    for ch in s:
        if esc:
            esc = False
            continue
        if ch == "\\" and in_str:
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if not in_str:
            if ch in "{[":
                d += 1
            elif ch in "}]":
                d -= 1
    return d


def collect_json(js_lines, start_idx, first_line):
    buf = [first_line]
    depth = count_braces(first_line)
    j = start_idx + 1
    while j < len(js_lines) and depth > 0:
        line = js_lines[j]
        if line.startswith(("http://", "https://", "send req:", "receive res:", "route: ")):
            break
        buf.append(line)
        depth += count_braces(line)
        j += 1
    raw = "\n".join(buf)
    try:
        return json.loads(raw), j, True
    except Exception:
        return raw, j, False


def parse_log(log_path: str):
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()

    raw_js = []
    for l in lines:
        m = re.match(r"^.*?[DE]/jswrapper\(\s*\d+\):\s*(?:JS:\s*)?(.*)$", l)
        if m:
            raw_js.append(m.group(1))

    # Filter out interleaved noise lines (onChat blocks, battle pushes, scene loads, debug prints)
    js = []
    skip_depth = 0
    for l in raw_js:
        if skip_depth > 0:
            skip_depth += count_braces(l)
            continue
        if l.startswith("onChat: "):
            rest = l[len("onChat: "):]
            skip_depth = max(0, count_braces(rest))
            continue
        if l.startswith(("LoadScene ", "no find:", "装备的数据是:", "dataApi init.", '{"route":"on')):
            continue
        js.append(l)
    packets = []
    i = 0
    while i < len(js):
        l = js[i]
        if l.startswith(("http://", "https://")):
            parts = l.split(" ", 1)
            url = parts[0]
            req_body = parts[1] if len(parts) > 1 else ""
            if i + 1 < len(js) and js[i + 1].lstrip().startswith(("{", "[")):
                res_obj, next_i, ok = collect_json(js, i + 1, js[i + 1])
                packets.append({"kind": "HTTP", "route": url, "req": req_body, "res": res_obj, "ok": ok})
                i = next_i
                continue
        elif l.startswith("route: "):
            m = re.match(r"^route:\s*([^,]+),\s*msg:\s*(.*)$", l)
            if m:
                route = m.group(1).strip()
                rest = m.group(2)
                direction = "REQ" if (i > 0 and js[i - 1] == "send req:") else ("RES" if (i > 0 and js[i - 1] == "receive res:") else "MSG")
                if rest.lstrip().startswith(("{", "[")):
                    obj, next_i, ok = collect_json(js, i, rest)
                    packets.append({"kind": f"WS_{direction}", "route": route, "data": obj, "ok": ok})
                    i = next_i
                    continue
        i += 1
    return packets


def main():
    if len(sys.argv) > 1:
        log_paths = sys.argv[1:]
    else:
        log_paths = sorted(glob.glob(os.path.join(LOGS_DIR, "*.log")))

    packets = []
    for log_path in log_paths:
        print(f"[*] Parsing {log_path} ...")
        packets.extend(parse_log(log_path))

    with open(OUT_PACKETS, "w", encoding="utf-8") as f:
        json.dump(packets, f, ensure_ascii=False, indent=2)

    # Build route_templates.json: latest valid RES for each route + HTTP path
    templates = {"http": {}, "ws": {}}
    for p in packets:
        if not p.get("ok"):
            continue
        if p["kind"] == "HTTP":
            path = p["route"].split("://", 1)[-1].split("/", 1)[-1].split("?")[0]
            templates["http"]["/" + path] = p["res"]
        elif p["kind"] in ("WS_RES", "WS_MSG"):
            templates["ws"][p["route"]] = p["data"]

    with open(OUT_ROUTES, "w", encoding="utf-8") as f:
        json.dump(templates, f, ensure_ascii=False, indent=2)

    c = Counter((p["kind"], p["route"], p["ok"]) for p in packets)
    print(f"Total parsed packets: {len(packets)}")
    for (k, r, ok), cnt in sorted(c.items()):
        print(f"  {k:8s} ok={str(ok):5s} {r:50s} x{cnt}")
    print(f"Saved templates: {len(templates['http'])} HTTP, {len(templates['ws'])} WS -> {OUT_ROUTES}")


if __name__ == "__main__":
    main()
