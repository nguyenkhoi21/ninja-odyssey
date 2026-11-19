import base64
import gzip
import json

_ENCODED_TOP_FIELDS = {
    "connector.playerHandler.entry": ("player",),
    "connector.playerHandler.createPlayer": ("player",),
}


def encode_field(obj) -> str:
    """base64(gzip(utf8(json))) — the format the client's unzipBase64() expects."""
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(gzip.compress(raw, 6)).decode("ascii")


def decode_field(value):
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return value
    try:
        return json.loads(gzip.decompress(base64.b64decode(value)).decode("utf-8"))
    except Exception:
        return value


def finalize(route_name: str, res):
    """Normalize a handler response into exactly what the client expects.

    - code defaults to 200
    - _temp.route is always the *actual* dispatched route (fixes stacked @route bugs)
    - `player` / _decodeKeys payloads are gzip+base64 encoded
    """
    if not isinstance(res, dict):
        return {"code": 200, "_temp": {"route": route_name}}

    res.setdefault("code", 200)

    temp = res.get("_temp")
    if not isinstance(temp, dict):
        temp = {}
    temp["route"] = route_name
    res["_temp"] = temp

    if res.get("code") == 200:
        for key in _ENCODED_TOP_FIELDS.get(route_name, ()):
            if key in res and not isinstance(res[key], str):
                res[key] = encode_field(res[key])

        keys = temp.get("_decodeKeys") or ()
        if isinstance(keys, str):
            keys = [keys]
        kept = []
        for key in keys:
            value = temp.get(key)
            if value is None or value == "" or value == {} or value == []:
                temp.pop(key, None)
                continue
            if not isinstance(value, str):
                temp[key] = encode_field(value)
            kept.append(key)
        if keys:
            if kept:
                temp["_decodeKeys"] = kept
            else:
                temp.pop("_decodeKeys", None)

    return res
