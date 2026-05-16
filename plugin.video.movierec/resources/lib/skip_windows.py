"""Minimal-rendering skip-intro / playing-next dialogs.

v0.4.15: stripped down to find what actually renders. Top-left
positioning guaranteed visible regardless of coordinate-system base.
No textures (skin defaults). Just labels and buttons.
"""
import xbmc
import xbmcaddon
import xbmcgui

_ADDON_ID = "plugin.video.movierec"
_ACTION_PREVIOUS_MENU = 10
_ACTION_NAV_BACK      = 92


class SkipIntroDialog(xbmcgui.WindowDialog):
    """Top-left placement, no custom textures — should render with the
    skin's default button style on any Kodi build."""

    def __init__(self, intro_end):
        super().__init__()
        self.intro_end = int(intro_end or 0)
        self.player = xbmc.Player()
        self.closed = False

        # Top-left absolute coords — visible in both 1280x720 and 1920x1080
        # coordinate spaces. The label exists so we can tell SOMETHING is
        # rendering even before we touch button styling.
        self.lbl = xbmcgui.ControlLabel(
            50, 50, 600, 36, "[B]movieRec[/B]: Skip Intro?",
            textColor="FFFFFFFF",
        )
        self.btn_skip = xbmcgui.ControlButton(
            50, 100, 280, 64, "Skip Intro",
            textColor="FFFFFFFF", focusedColor="FFFFFF00",
        )
        self.btn_close = xbmcgui.ControlButton(
            340, 100, 200, 64, "Close",
            textColor="FFFFFFFF", focusedColor="FFFFFF00",
        )
        self.addControl(self.lbl)
        self.addControl(self.btn_skip)
        self.addControl(self.btn_close)

        self.btn_skip.controlRight(self.btn_close)
        self.btn_close.controlLeft(self.btn_skip)

    def onInit(self):
        try:
            self.setFocus(self.btn_skip)
        except Exception:
            pass
        while not self.closed:
            try:
                if not self.player.isPlaying():
                    break
                cur = int(self.player.getTime())
            except RuntimeError:
                break
            if cur >= self.intro_end:
                break
            xbmc.sleep(1000)
        self.close()

    def onAction(self, action):
        if action.getId() in (_ACTION_PREVIOUS_MENU, _ACTION_NAV_BACK):
            self.closed = True
            self.close()

    def onControl(self, control):
        if control is None:
            return
        try:
            cid = control.getId()
        except Exception:
            return
        if cid == self.btn_skip.getId():
            try:
                self.player.seekTime(self.intro_end)
            except RuntimeError:
                pass
        self.closed = True
        self.close()


class PlayingNextDialog(xbmcgui.WindowDialog):
    """Same minimal pattern for the end-of-episode panel."""

    def __init__(self, outro_end):
        super().__init__()
        self.outro_end = int(outro_end or 0)
        self.player = xbmc.Player()
        try:
            self.total_time = int(self.player.getTotalTime() or 0)
        except RuntimeError:
            self.total_time = 0
        self.closed = False

        self.lbl = xbmcgui.ControlLabel(
            50, 50, 700, 36, "[B]movieRec[/B]: Up Next",
            textColor="FFFFFFFF",
        )
        self.btn_play = xbmcgui.ControlButton(
            50, 100, 180, 64, "Play Now",
            textColor="FFFFFFFF", focusedColor="FFFFFF00",
        )
        self.btn_skipoutro = xbmcgui.ControlButton(
            240, 100, 200, 64, "Skip Outro",
            textColor="FFFFFFFF", focusedColor="FFFFFF00",
        )
        self.btn_close = xbmcgui.ControlButton(
            450, 100, 160, 64, "Close",
            textColor="FFFFFFFF", focusedColor="FFFFFF00",
        )
        for c in (self.lbl, self.btn_play, self.btn_skipoutro, self.btn_close):
            self.addControl(c)
        self.btn_play.controlRight(self.btn_skipoutro)
        self.btn_skipoutro.controlLeft(self.btn_play)
        self.btn_skipoutro.controlRight(self.btn_close)
        self.btn_close.controlLeft(self.btn_skipoutro)

    def onInit(self):
        try:
            self.setFocus(self.btn_play)
        except Exception:
            pass
        while not self.closed:
            try:
                if not self.player.isPlaying():
                    break
                cur = int(self.player.getTime())
            except RuntimeError:
                break
            if self.total_time - cur <= 2:
                break
            xbmc.sleep(1000)
        self.close()

    def onAction(self, action):
        if action.getId() in (_ACTION_PREVIOUS_MENU, _ACTION_NAV_BACK):
            self.closed = True
            self.close()

    def onControl(self, control):
        if control is None:
            return
        try:
            cid = control.getId()
        except Exception:
            return
        try:
            if cid == self.btn_play.getId():
                self.player.seekTime(max(self.total_time - 5, 0))
            elif cid == self.btn_skipoutro.getId():
                if self.outro_end and self.outro_end > 0:
                    self.player.seekTime(self.outro_end)
                else:
                    self.player.seekTime(max(self.total_time - 5, 0))
        except RuntimeError:
            pass
        self.closed = True
        self.close()


# ─── Public entry points ──────────────────────────────────────────────

def show_skip_intro(intro_end):
    """Open Skip Intro popup. doModal blocks the calling daemon thread
    until close; Kodi marshals the UI to its main thread via onInit."""
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
