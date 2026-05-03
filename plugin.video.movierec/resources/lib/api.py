"""Thin HTTP client for the movieRec server's /api/kodi endpoints."""
import json
import urllib.parse
import urllib.request
import urllib.error

import xbmcaddon
import xbmcgui

ADDON = xbmcaddon.Addon()


class APIError(Exception):
    pass


class Unauthorized(APIError):
    pass


def _settings():
    base = ADDON.getSettingString("server_url").rstrip("/")
    pw = ADDON.getSettingString("server_password")
    return base, pw


def _request(method, path, params=None, body=None, timeout=20):
    base, pw = _settings()
    if not base or not pw:
        raise APIError("Server URL and password must be set in add-on settings")

    url = base + "/api/kodi" + path
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})

    data = None
    headers = {"X-MovieRec-Password": pw, "Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise Unauthorized("Server rejected password")
        body_txt = ""
        try:
            body_txt = e.read().decode("utf-8", errors="ignore")
        except Exception:
            pass
        raise APIError("HTTP %s: %s" % (e.code, body_txt or e.reason))
    except urllib.error.URLError as e:
        raise APIError("Cannot reach server: %s" % e.reason)

    if not raw:
        return None
    return json.loads(raw)


def get(path, **params):
    return _request("GET", path, params=params)


def post(path, body=None, **params):
    return _request("POST", path, params=params, body=body or {})


def put(path, body=None, **params):
    return _request("PUT", path, params=params, body=body or {})


def signed_url(path, **params):
    """Build a server URL with the password embedded as `?p=` for resources
    Kodi fetches without custom headers (subtitles)."""
    base, pw = _settings()
    qs = dict(params or {})
    qs["p"] = pw
    return base + "/api/kodi" + path + "?" + urllib.parse.urlencode(qs)


def notify(msg, heading="movieRec", icon=xbmcgui.NOTIFICATION_INFO, ms=4000):
    xbmcgui.Dialog().notification(heading, msg, icon, ms)


def handle_error(exc):
    if isinstance(exc, Unauthorized):
        notify("Bad password — open settings", icon=xbmcgui.NOTIFICATION_ERROR)
        ADDON.openSettings()
    else:
        notify(str(exc), icon=xbmcgui.NOTIFICATION_ERROR, ms=6000)
