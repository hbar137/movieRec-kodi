"""Thin replacement for Otaku's resources.lib.ui.control.

Otaku's real control.py is ~850 lines wired into their addon settings,
artwork, dialogs, watch progress, etc. The scrapers only need a handful
of helpers from it — those are listed below. Everything else is left
unimplemented because no vendored scraper calls it.

Living here (instead of being vendored from upstream) means we don't
have to manage `xbmcaddon.Addon('plugin.video.otaku')` calls that would
crash when Otaku isn't installed (which is our whole point — we vendor
the scrapers so the user does NOT have to keep Otaku installed).

License: scaffolding (no Otaku code here).
"""
import os
import sys
import threading

import xbmc
import xbmcaddon
import xbmcvfs


_ADDON_ID = "plugin.video.movierec"
_ADDON = xbmcaddon.Addon(_ADDON_ID)


# --- logging ---------------------------------------------------------------
def log(msg, level="info"):
    # Otaku logs noisily; route through Kodi's logger so users with
    # debug logging on can see the trace.
    xbmc.log(f"[movierec.otaku] {msg}", xbmc.LOGINFO)


# --- settings (defaults; embed-source picker doesn't expose these) ---------
def getSetting(key, default=""):
    try:
        return _ADDON.getSettingString(key) or default
    except Exception:
        return default


def setSetting(key, value):
    try:
        _ADDON.setSettingString(key, str(value))
    except Exception:
        pass


def getBool(key, default=False):
    try:
        return _ADDON.getSettingBool(key)
    except Exception:
        return default


def setBool(key, value):
    try:
        _ADDON.setSettingBool(key, bool(value))
    except Exception:
        pass


def getInt(key, default=0):
    try:
        return _ADDON.getSettingInt(key)
    except Exception:
        return default


def setInt(key, value):
    try:
        _ADDON.setSettingInt(key, int(value))
    except Exception:
        pass


def getString(key, default=""):
    return getSetting(key, default)


def setString(key, value):
    setSetting(key, value)


def getStringList(key):
    # Used by BrowserBase to read enabled embed servers. Return a
    # permissive list so all known providers are considered enabled.
    return [
        "MegaCloud", "Mega Cloud", "Vidstreaming", "Vidcloud",
        "StreamSB", "StreamTape", "Vidplay", "Filemoon", "MyCloud",
        "Kwik",
    ]


def setStringList(key, value):
    pass


# --- addon paths -----------------------------------------------------------
ADDON_ID = _ADDON_ID
ADDON_NAME = "movieRec"
ADDON_PATH = xbmcvfs.translatePath(_ADDON.getAddonInfo("path"))
ADDON_PROFILE = xbmcvfs.translatePath(_ADDON.getAddonInfo("profile"))
dataPath = ADDON_PROFILE

# A subdirectory under our profile that Otaku's scrapers + client may
# write cookies / session state into. Created lazily.
_OTAKU_STATE_DIR = os.path.join(ADDON_PROFILE, "otaku_state")
if not xbmcvfs.exists(_OTAKU_STATE_DIR):
    xbmcvfs.mkdirs(_OTAKU_STATE_DIR)

completed_json = os.path.join(_OTAKU_STATE_DIR, "completed.json")
cookies_path = os.path.join(_OTAKU_STATE_DIR, "cookies.dat")
session_path = os.path.join(_OTAKU_STATE_DIR, "sessions.json")


def getAddonInfo(key, default=""):
    return _ADDON.getAddonInfo(key) or default


# --- helpers ---------------------------------------------------------------
def bin(s):
    if isinstance(s, str):
        return s.encode("utf-8")
    return s


def is_addon_visible():
    # The scrapers use this to decide whether to suppress paginator
    # "Next page" items. We don't paginate from the embed picker.
    return True


def hide_busy_dialog():
    pass


def show_busy_dialog():
    pass


def execute(cmd):
    xbmc.executebuiltin(cmd)


def refresh():
    pass


# Kodi version detection used by Otaku for property-name fallbacks.
try:
    _kodi_major = int(xbmc.getInfoLabel("System.BuildVersion").split(".", 1)[0])
except Exception:
    _kodi_major = 20
kodi_version = float(_kodi_major)


# --- thread-local show context --------------------------------------------
# pick_embed_source sets the title here before invoking a scraper so
# our database.get_show() shim can return show metadata without a real
# Otaku-style cache.
_show_context = threading.local()


def set_show_context(mal_id, title, start_date):
    _show_context.mal_id = mal_id
    _show_context.title = title
    _show_context.start_date = start_date


def get_show_context():
    return {
        "mal_id": getattr(_show_context, "mal_id", 0),
        "title": getattr(_show_context, "title", ""),
        "start_date": getattr(_show_context, "start_date", ""),
    }
