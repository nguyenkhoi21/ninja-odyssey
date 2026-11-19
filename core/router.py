import traceback

from core.templates import get_ws_template
from core.payload import finalize

_ROUTES = {}
_PREFIX_HANDLERS = {}


def route(route_name: str):
    """Decorator to register an exact Pomelo route handler."""
    def decorator(fn):
        _ROUTES[route_name] = fn
        return fn
    return decorator


def prefix_handler(prefix: str):
    """Decorator to register a fallback handler for a module prefix (e.g. 'logic.guildHandler.')."""
    def decorator(fn):
        _PREFIX_HANDLERS[prefix] = fn
        return fn
    return decorator


def registered_count() -> int:
    return len(_ROUTES)


def has_route(route_name: str) -> bool:
    if route_name in _ROUTES:
        return True
    return any(route_name.startswith(p) for p in _PREFIX_HANDLERS)


def dispatch(route_name: str, req: dict, session: dict) -> dict:
    handler = _ROUTES.get(route_name)

    if handler is not None:
        try:
            res = handler(req, session)
        except Exception:
            traceback.print_exc()
            return finalize(route_name, {"code": 500, "msg": "服务器内部错误"})
        return finalize(route_name, res)

    for prefix, fn in _PREFIX_HANDLERS.items():
        if route_name.startswith(prefix):
            try:
                res = fn(route_name, req, session)
            except Exception:
                traceback.print_exc()
                return finalize(route_name, {"code": 500, "msg": "服务器内部错误"})
            return finalize(route_name, res)

    tpl = get_ws_template(route_name)
    if tpl is not None:
        return finalize(route_name, tpl)

    return finalize(route_name, {"code": 200})
