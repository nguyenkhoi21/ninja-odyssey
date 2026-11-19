import os
import json
import copy

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_PATH = os.path.join(SERVER_DIR, "route_templates.json")

_TEMPLATES = None


def get_templates():
    global _TEMPLATES
    if _TEMPLATES is None:
        if os.path.exists(TEMPLATES_PATH):
            with open(TEMPLATES_PATH, "r", encoding="utf-8") as f:
                _TEMPLATES = json.load(f)
        else:
            _TEMPLATES = {"http": {}, "ws": {}}
    return _TEMPLATES


def get_http_template(path: str, default=None):
    t = get_templates().get("http", {}).get(path)
    return copy.deepcopy(t) if t is not None else copy.deepcopy(default)


def get_ws_template(route: str):
    t = get_templates().get("ws", {}).get(route)
    return copy.deepcopy(t) if t is not None else None
