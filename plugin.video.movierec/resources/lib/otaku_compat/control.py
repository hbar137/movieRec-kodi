"""Minimal stub of Otaku's resources.lib.ui.control module.

Only implements what skip_intro.py / playing_next.py / base_window.py
actually call. Otaku's full module is ~1000 lines of UI / settings /
artwork helpers we don't need.

License: GPL-3.0 (derived from Otaku).
"""
import xbmc
import xbmcaddon

_ADDON_ID = "plugin.video.movierec"
_ADDON = xbmcaddon.Addon(_ADDON_ID)

# Defaults for settings Otaku's skip_intro / playing_next read.  We don't
# ship these as user-facing options yet (anime audio + autoplay-next are
# the only anime settings the addon exposes today), so the defaults take
# effect every time.
_DEFAULTS = {
    "skipintro.time": 90,         # seconds to skip when no aniskip data
    "skipintro.delay": 5,         # show "Skip Intro" dialog this many seconds in
    "skipintro.duration": 1,      # ... for this many minutes (when no aniskip data)
    "playingnext.defaultaction": 0,  # 0 = continue, 1 = pause when dialog times out
    "playingnext.time": 30,       # show "Playing Next" dialog N seconds before end
    "smartplay.skipintrodialog": True,
    "smartplay.playingnextdialog": True,
    "skipintro.aniskip.enable": True,
    "skipintro.aniskip.auto": False,
    "skipoutro.aniskip.enable": True,
    "skipoutro.aniskip.auto": False,
    "skipintro.aniskip.offset": 0,
    "skipoutro.aniskip.offset": 0,
}


def getInt(key):
    try:
        return int(_ADDON.getSettingInt(key))
    except Exception:
        d = _DEFAULTS.get(key, 0)
        return int(d) if isinstance(d, (int, float, bool)) else 0


def getBool(key):
    try:
        return bool(_ADDON.getSettingBool(key))
    except Exception:
        d = _DEFAULTS.get(key, False)
        return bool(d) if isinstance(d, bool) else False


def getSetting(key):
    try:
        return _ADDON.getSettingString(key)
    except Exception:
        return ""


def closeBusyDialog():
    try:
        xbmc.executebuiltin("Dialog.Close(busydialog)")
    except Exception:
        pass


def log(msg, level="info"):
    levels = {
        "info":    xbmc.LOGINFO,
        "warning": xbmc.LOGWARNING,
        "error":   xbmc.LOGERROR,
    }
    try:
        xbmc.log("[movieRec/otaku_compat] %s" % str(msg), levels.get(str(level).lower(), xbmc.LOGINFO))
    except Exception:
        pass
