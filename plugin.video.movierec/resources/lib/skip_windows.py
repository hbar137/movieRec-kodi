"""Skip Intro / Playing Next popups for anime.

v0.4.16: rebuilt with single panel background, centered button text,
explicit video-OSD dismissal for remote input, onClick+onControl dual
handlers, and a hard timeout fallback for auto-close.
"""
import os
import xbmc
import xbmcaddon
import xbmcgui

_ADDON_ID = "plugin.video.movierec"

_ACTION_PREVIOUS_MENU = 10
_ACTION_NAV_BACK      = 92

# XBFONT alignment bits (from Kodi's GUILib): X_LEFT=0, X_RIGHT=1,
# CENTER_X=2, CENTER_Y=4, TRUNCATED=8, JUSTIFY=10. Centered both axes = 2|4 = 6.
_ALIGN_CENTER = 6

# Auto-close timeout in seconds — belt-and-suspenders in case the
# time-check loop misbehaves (player.getTime returns 0, sleeps stall, etc).
_MAX_DURATION = 90


def _white_png():
    """Path to our shipped 1x1 white texture. Tintable via colorDiffuse on
    any ControlImage / ControlButton. Resolved via xbmcvfs.translatePath
    so we always get an absolute filesystem path (not a special:// URI
    which some Kodi builds reject for control textures)."""
    import xbmcvfs
    base = xbmcvfs.translatePath(
        xbmcaddon.Addon(_ADDON_ID).getAddonInfo("path"))
    return os.path.join(base, "resources", "media", "white.png")


def _free_input():
    """Otaku's onload Dialog.Close trick — pushes any active video OSD /
    fullscreen info window out of the way so OUR dialog gets the remote
    input. Without this the OSD swallows directional + Enter keys and
    our buttons never get focus events."""
    try:
        xbmc.executebuiltin('Dialog.Close(videoosd,true)')
        xbmc.executebuiltin('Dialog.Close(fullscreeninfo,true)')
    except Exception:
        pass


class _AnimeDialogBase(xbmcgui.WindowDialog):
    """Shared scaffolding — single bg panel + watcher loop + dual onClick/
    onControl handlers. Subclasses add their own buttons and reactions."""

    # Subclasses override these:
    PANEL_W = 600
    PANEL_H = 200
    PANEL_X = 50
    PANEL_Y = 40

    def _build_panel(self):
        """One ControlImage as a solid-black bg + 2px white border on each
        edge. Subclasses call this in __init__ before adding their own
        buttons + labels (which sit on top)."""
        tex = _white_png()
        bg = xbmcgui.ControlImage(self.PANEL_X, self.PANEL_Y, self.PANEL_W,
                                   self.PANEL_H, tex, colorDiffuse="FF0E0E0E")
        top    = xbmcgui.ControlImage(self.PANEL_X, self.PANEL_Y,
                                       self.PANEL_W, 2, tex, colorDiffuse="FFFFFFFF")
        bottom = xbmcgui.ControlImage(self.PANEL_X, self.PANEL_Y + self.PANEL_H - 2,
                                       self.PANEL_W, 2, tex, colorDiffuse="FFFFFFFF")
        left   = xbmcgui.ControlImage(self.PANEL_X, self.PANEL_Y,
                                       2, self.PANEL_H, tex, colorDiffuse="FFFFFFFF")
        right  = xbmcgui.ControlImage(self.PANEL_X + self.PANEL_W - 2, self.PANEL_Y,
                                       2, self.PANEL_H, tex, colorDiffuse="FFFFFFFF")
        for c in (bg, top, bottom, left, right):
            self.addControl(c)

    def _button(self, x, y, w, h, label, *, primary=False):
        """ControlButton with the white tex tinted blue (primary) or
        dark-grey (secondary). Text centered. Focus changes the tint to
        a brighter shade."""
        tex = _white_png()
        return xbmcgui.ControlButton(
            x, y, w, h, label,
            focusTexture=tex,
            noFocusTexture=tex,
            textColor="FFFFFFFF",
            focusedColor="FFFFFFFF",
            alignment=_ALIGN_CENTER,
            textOffsetX=0,
            textOffsetY=0,
        )

    # ---- input handling: implement BOTH onClick and onControl so we
    # ---- work across Kodi versions that fire one but not the other.

    def onClick(self, controlID):
        self._dispatch(controlID)

    def onControl(self, control):
        if control is None:
            return
        try:
            self._dispatch(control.getId())
        except Exception:
            return

    def onAction(self, action):
        if action.getId() in (_ACTION_PREVIOUS_MENU, _ACTION_NAV_BACK):
            self.closed = True
            self.close()

    def _dispatch(self, control_id):
        raise NotImplementedError

    # ---- the watcher loop runs INSIDE onInit, on Kodi's UI thread, so
    # ---- input + rendering keep working while xbmc.sleep yields.

    def _watch(self, end_predicate):
        """Block until end_predicate() returns True OR _MAX_DURATION elapses
        OR self.closed is set externally. _MAX_DURATION is a safety net —
        even if the player time misbehaves, the dialog won't sit forever."""
        import time as _t
        started = _t.monotonic()
        while not self.closed:
            try:
                if not self.player.isPlaying():
                    break
                if end_predicate():
                    break
            except RuntimeError:
                break
            if _t.monotonic() - started > _MAX_DURATION:
                break
            xbmc.sleep(1000)
        try:
            self.close()
        except Exception:
            pass


class SkipIntroDialog(_AnimeDialogBase):
    PANEL_W = 600
    PANEL_H = 140
    PANEL_X = 50
    PANEL_Y = 50

    def __init__(self, intro_end):
        super().__init__()
        self.intro_end = int(intro_end or 0)
        self.player = xbmc.Player()
        self.closed = False

        self._build_panel()

        self.lbl = xbmcgui.ControlLabel(
            self.PANEL_X + 20, self.PANEL_Y + 16, self.PANEL_W - 40, 28,
            "[B]Skip Intro?[/B]",
            textColor="FFFFFFFF",
        )
        bx = self.PANEL_X + 20
        by = self.PANEL_Y + 56
        bh = 64
        bw_skip, bw_close, gap = 280, 160, 10
        self.btn_skip = self._button(bx, by, bw_skip, bh, "Skip Intro", primary=True)
        self.btn_close = self._button(bx + bw_skip + gap, by, bw_close, bh, "Close")
        for c in (self.lbl, self.btn_skip, self.btn_close):
            self.addControl(c)
        self.btn_skip.controlRight(self.btn_close)
        self.btn_skip.controlLeft(self.btn_close)
        self.btn_close.controlRight(self.btn_skip)
        self.btn_close.controlLeft(self.btn_skip)

    def onInit(self):
        _free_input()
        try:
            self.setFocus(self.btn_skip)
        except Exception:
            pass
        self._watch(lambda: int(self.player.getTime()) >= self.intro_end)

    def _dispatch(self, control_id):
        if control_id == self.btn_skip.getId():
            try:
                self.player.seekTime(self.intro_end)
            except RuntimeError:
                pass
        self.closed = True
        try:
            self.close()
        except Exception:
            pass


class PlayingNextDialog(_AnimeDialogBase):
    PANEL_W = 720
    PANEL_H = 200
    PANEL_X = 50
    PANEL_Y = 50

    def __init__(self, outro_end):
        super().__init__()
        self.outro_end = int(outro_end or 0)
        self.player = xbmc.Player()
        try:
            self.total_time = int(self.player.getTotalTime() or 0)
        except RuntimeError:
            self.total_time = 0
        try:
            self.duration = max(self.total_time - int(self.player.getTime() or 0), 1)
        except RuntimeError:
            self.duration = 1
        self.closed = False

        self._build_panel()

        self.lbl = xbmcgui.ControlLabel(
            self.PANEL_X + 20, self.PANEL_Y + 16, self.PANEL_W - 40, 28,
            "[B]Up Next[/B]",
            textColor="FFFFFFFF",
        )
        self.progress = xbmcgui.ControlProgress(
            self.PANEL_X + 20, self.PANEL_Y + 54, self.PANEL_W - 40, 8,
            texturebg=_white_png(),
            textureleft=_white_png(),
            texturemid=_white_png(),
            textureright=_white_png(),
            textureoverlay=_white_png(),
        )
        bx = self.PANEL_X + 20
        by = self.PANEL_Y + 100
        bh = 64
        bw_play, bw_skip, bw_close, gap = 200, 200, 200, 10
        self.btn_play     = self._button(bx,                              by, bw_play,  bh, "Play Now",   primary=True)
        self.btn_skipoutro = self._button(bx + bw_play + gap,             by, bw_skip,  bh, "Skip Outro", primary=True)
        self.btn_close    = self._button(bx + bw_play + bw_skip + gap*2, by, bw_close, bh, "Close")
        for c in (self.lbl, self.progress, self.btn_play, self.btn_skipoutro, self.btn_close):
            self.addControl(c)
        self.btn_play.controlRight(self.btn_skipoutro)
        self.btn_play.controlLeft(self.btn_close)
        self.btn_skipoutro.controlRight(self.btn_close)
        self.btn_skipoutro.controlLeft(self.btn_play)
        self.btn_close.controlRight(self.btn_play)
        self.btn_close.controlLeft(self.btn_skipoutro)

    def onInit(self):
        _free_input()
        try:
            self.setFocus(self.btn_play)
        except Exception:
            pass
        def predicate():
            cur = int(self.player.getTime())
            remaining = self.total_time - cur
            try:
                pct = max(0, min(100, int((remaining / max(self.duration, 1)) * 100)))
                self.progress.setPercent(pct)
            except Exception:
                pass
            return remaining <= 2
        self._watch(predicate)

    def _dispatch(self, control_id):
        try:
            if control_id == self.btn_play.getId():
                self.player.seekTime(max(self.total_time - 5, 0))
            elif control_id == self.btn_skipoutro.getId():
                if self.outro_end and self.outro_end > 0:
                    self.player.seekTime(self.outro_end)
                else:
                    self.player.seekTime(max(self.total_time - 5, 0))
        except RuntimeError:
            pass
        self.closed = True
        try:
            self.close()
        except Exception:
            pass


# ─── Public entry points ──────────────────────────────────────────────

def show_skip_intro(intro_end):
    xbmcgui.Dialog().notification("movieRec",
        "DIAG: opening skip-intro popup (end=%ds)" % int(intro_end or 0),
        xbmcgui.NOTIFICATION_INFO, 3000)
    try:
        dlg = SkipIntroDialog(intro_end)
        dlg.doModal()
        del dlg
    except Exception as e:
        xbmc.log("[movieRec] skip-intro popup error: %s" % e, xbmc.LOGWARNING)
        xbmcgui.Dialog().notification("movieRec",
            "DIAG: skip-intro popup error: %s" % str(e)[:60],
            xbmcgui.NOTIFICATION_ERROR, 5000)


def show_playing_next(outro_end=0):
    xbmcgui.Dialog().notification("movieRec",
        "DIAG: opening playing-next popup",
        xbmcgui.NOTIFICATION_INFO, 3000)
    try:
        dlg = PlayingNextDialog(outro_end)
        dlg.doModal()
        del dlg
    except Exception as e:
        xbmc.log("[movieRec] playing-next popup error: %s" % e, xbmc.LOGWARNING)
        xbmcgui.Dialog().notification("movieRec",
            "DIAG: playing-next popup error: %s" % str(e)[:60],
            xbmcgui.NOTIFICATION_ERROR, 5000)
