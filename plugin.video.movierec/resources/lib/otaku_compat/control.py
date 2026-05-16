"""Minimal stub of Otaku's resources.lib.ui.control module.

Only implements what the verbatim files in this package actually call:
  - getInt        — skip_intro.py:51, playing_next.py:17, plus play.py
                    watcher (skipintro.delay / duration / playingnext.time)
  - closeBusyDialog — base_window.py:24

Otaku's full control module is ~1000 lines of UI / settings / artwork
helpers we don't need. Trimmed to the call sites we actually hit.

License: GPL-3.0 (derived from Otaku).
"""
import xbmc
import xbmcaddon

_ADDON_ID = "plugin.video.movierec"
_ADDON = xbmcaddon.Addon(_ADDON_ID)

# Defaults match Otaku's bundled values. Used whenever getInt(...) is
# called for a key the addon settings haven't defined yet.
_DEFAULTS = {
    "skipintro.time":              90,  # button-default seek when no aniskip data (+90s)
    "skipintro.delay":              5,  # show default Skip Intro dialog this many seconds in
    "skipintro.duration":           1,  # ... for this many minutes (when no aniskip data)
    "playingnext.defaultaction":    0,  # 0 = continue, 1 = pause when popup times out
    "playingnext.time":            30,  # show Up Next dialog N seconds before end
}


def getInt(key):
    try:
        return int(_ADDON.getSettingInt(key))
    except Exception:
        return int(_DEFAULTS.get(key, 0))


def closeBusyDialog():
    try:
        xbmc.executebuiltin("Dialog.Close(busydialog)")
    except Exception:
        pass
