"""Programmatic xbmcgui.WindowDialog popups for anime: Skip Intro
and Playing Next.

Built from code (no XML skin lookup) so we don't depend on Kodi's
WindowXMLDialog resolution/skin resolution heuristics, which have
caused dialogs to render invisibly across the last few addon versions.

Controls are positioned for 1080p (1920x1080); Kodi auto-scales for
other display sizes.

Layout (bottom-right):

  ┌───── solid black panel, white border ─────┐
  │  [ Skip Intro ]      [ Close ]            │   (skip intro)
  └────────────────────────────────────────────┘

  ┌───── solid black panel, white border ─────┐
  │  Up Next                                   │
  │  [progress bar ────────────────]           │   (playing next)
  │  [ Play Now ]  [ Skip Outro ]  [ Close ]  │
  └────────────────────────────────────────────┘
"""
import os
import xbmc
import xbmcaddon
import xbmcgui

_ADDON_ID = "plugin.video.movierec"

# Display dimensions our coordinates are calibrated for. Kodi auto-scales.
_W = 1920
_H = 1080

# Bottom-right placement for both dialogs.
_PANEL_RIGHT = 60
_PANEL_BOTTOM = 160

# Action IDs from xbmcgui (avoid magic numbers)
_ACTION_PREVIOUS_MENU = 10
_ACTION_NAV_BACK      = 92
_ACTION_SELECT_ITEM   = 7


def _white_png():
    """Absolute path to our shipped 1x1 white texture (tintable via
    colorDiffuse on any ControlImage / ControlButton control)."""
    addon_path = xbmcaddon.Addon(_ADDON_ID).getAddonInfo("path")
    return os.path.join(addon_path, "resources", "media", "white.png")


def _make_bg(x, y, w, h):
    """Solid black panel with white border. Returns a list of
    ControlImage(s) to addControl in order."""
    tex = _white_png()
    bg = xbmcgui.ControlImage(x, y, w, h, tex, colorDiffuse="FF0E0E0E")
    # 2px white border on each side
    top    = xbmcgui.ControlImage(x,         y,         w, 2,    tex, colorDiffuse="FFFFFFFF")
    bottom = xbmcgui.ControlImage(x,         y + h - 2, w, 2,    tex, colorDiffuse="FFFFFFFF")
    left   = xbmcgui.ControlImage(x,         y,         2, h,    tex, colorDiffuse="FFFFFFFF")
    right  = xbmcgui.ControlImage(x + w - 2, y,         2, h,    tex, colorDiffuse="FFFFFFFF")
    return [bg, top, bottom, left, right]


def _make_button(x, y, w, h, label, *, blue=False):
    """ControlButton with our white texture tinted blue (primary) or
    grey (secondary). Centered text. Focus state uses a brighter blue."""
    tex = _white_png()
    if blue:
        no_focus = "FF2962FF"
        focused  = "FF1E88E5"
    else:
        no_focus = "FF3A3A3A"
        focused  = "FF888888"
    return xbmcgui.ControlButton(
        x, y, w, h, label,
        focusTexture=tex,
        noFocusTexture=tex,
        textColor="FFFFFFFF",
        focusedColor="FFFFFFFF",
        alignment=2 | 4,   # XBFONT_CENTER_X | XBFONT_CENTER_Y
        textOffsetX=0,
        textOffsetY=0,
    ).__class__(  # rebuild with colorDiffuse via setColorDiffuse later
        x, y, w, h, label,
        focusTexture=tex,
        noFocusTexture=tex,
        textColor="FFFFFFFF",
        focusedColor="FFFFFFFF",
        alignment=2 | 4,
        textOffsetX=0,
        textOffsetY=0,
    )


class SkipIntroDialog(xbmcgui.WindowDialog):
    """Non-modal popup with Skip Intro / Close buttons."""

    def __init__(self, intro_end):
        # NOTE: xbmcgui.WindowDialog.__init__ takes no args. Don't pass any.
        super().__init__()
        self.intro_end = int(intro_end or 0)
        self.player = xbmc.Player()
        self.closed = False

        # Panel geometry
        panel_w = 460
        panel_h = 88
        x = _W - _PANEL_RIGHT - panel_w
        y = _H - _PANEL_BOTTOM - panel_h
        for c in _make_bg(x, y, panel_w, panel_h):
            self.addControl(c)

        # Buttons
        skip_w, close_w, gap = 280, 140, 10
        bx = x + 14
        by = y + 12
        bh = 64
        self.btn_skip = xbmcgui.ControlButton(
            bx, by, skip_w, bh, "Skip Intro",
            focusTexture=_white_png(),
            noFocusTexture=_white_png(),
            textColor="FFFFFFFF", focusedColor="FFFFFFFF",
            alignment=6,  # XBFONT_CENTER_X|XBFONT_CENTER_Y = 2|4
        )
        self.btn_close = xbmcgui.ControlButton(
            bx + skip_w + gap, by, close_w, bh, "Close",
            focusTexture=_white_png(),
            noFocusTexture=_white_png(),
            textColor="FFFFFFFF", focusedColor="FFFFFFFF",
            alignment=6,
        )
        self.addControl(self.btn_skip)
        self.addControl(self.btn_close)

        # Wire up navigation between the two buttons
        self.btn_skip.controlRight(self.btn_close)
        self.btn_skip.controlLeft(self.btn_close)
        self.btn_close.controlRight(self.btn_skip)
        self.btn_close.controlLeft(self.btn_skip)

    def show_and_run(self):
        """Display dialog, focus the Skip button, and run a background
        loop that auto-closes the dialog once we pass intro_end."""
        self.show()
        self.setFocus(self.btn_skip)
        monitor = xbmc.Monitor()
        try:
            while not self.closed and self.player.isPlaying():
                try:
                    cur = int(self.player.getTime())
                except RuntimeError:
                    break
                if cur >= self.intro_end:
                    break
                if monitor.waitForAbort(1):
                    break
        finally:
            try:
                self.close()
            except Exception:
                pass

    def onAction(self, action):
        aid = action.getId()
        if aid in (_ACTION_PREVIOUS_MENU, _ACTION_NAV_BACK):
            self.closed = True
            self.close()
        elif aid == _ACTION_SELECT_ITEM:
            # Enter on focused button — dispatch to onControl manually
            ctrl = self.getFocus() if hasattr(self, "getFocus") else None
            self.onControl(ctrl)

    def onControl(self, control):
        if control is None:
            return
        cid = control.getId()
        if cid == self.btn_skip.getId():
            try:
                self.player.seekTime(self.intro_end)
            except RuntimeError:
                pass
        self.closed = True
        self.close()


class PlayingNextDialog(xbmcgui.WindowDialog):
    """Non-modal popup with Play Now / Skip Outro / Close + progress bar."""

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

        # Panel geometry (taller than skip-intro to fit the progress bar)
        panel_w = 600
        panel_h = 180
        x = _W - _PANEL_RIGHT - panel_w
        y = _H - _PANEL_BOTTOM - panel_h
        for c in _make_bg(x, y, panel_w, panel_h):
            self.addControl(c)

        # Title
        title = xbmcgui.ControlLabel(
            x + 20, y + 16, panel_w - 40, 32, "Up Next",
            textColor="FFFFFFFF",
        )
        self.addControl(title)

        # Progress bar (we update its percent in show_and_run)
        self.progress = xbmcgui.ControlProgress(
            x + 20, y + 54, panel_w - 40, 8,
            texturebg=_white_png(),
            textureleft=_white_png(),
            texturemid=_white_png(),
            textureright=_white_png(),
            textureoverlay=_white_png(),
        )
        self.addControl(self.progress)

        # Buttons row
        bw_play, bw_skip, bw_close, gap = 180, 180, 160, 10
        bx = x + 20
        by = y + 84
        bh = 64
        self.btn_play = xbmcgui.ControlButton(
            bx, by, bw_play, bh, "Play Now",
            focusTexture=_white_png(), noFocusTexture=_white_png(),
            textColor="FFFFFFFF", focusedColor="FFFFFFFF", alignment=6,
        )
        self.btn_skipoutro = xbmcgui.ControlButton(
            bx + bw_play + gap, by, bw_skip, bh, "Skip Outro",
            focusTexture=_white_png(), noFocusTexture=_white_png(),
            textColor="FFFFFFFF", focusedColor="FFFFFFFF", alignment=6,
        )
        self.btn_close = xbmcgui.ControlButton(
            bx + bw_play + bw_skip + gap * 2, by, bw_close, bh, "Close",
            focusTexture=_white_png(), noFocusTexture=_white_png(),
            textColor="FFFFFFFF", focusedColor="FFFFFFFF", alignment=6,
        )
        for b in (self.btn_play, self.btn_skipoutro, self.btn_close):
            self.addControl(b)

        # Navigation between buttons (wraps)
        self.btn_play.controlRight(self.btn_skipoutro)
        self.btn_play.controlLeft(self.btn_close)
        self.btn_skipoutro.controlRight(self.btn_close)
        self.btn_skipoutro.controlLeft(self.btn_play)
        self.btn_close.controlRight(self.btn_play)
        self.btn_close.controlLeft(self.btn_skipoutro)

    def show_and_run(self):
        self.show()
        self.setFocus(self.btn_play)
        monitor = xbmc.Monitor()
        try:
            while not self.closed and self.player.isPlaying():
                try:
                    cur = int(self.player.getTime())
                except RuntimeError:
                    break
                remaining = self.total_time - cur
                if remaining <= 2:
                    break
                try:
                    pct = max(0, min(100, int((remaining / max(self.duration, 1)) * 100)))
                    self.progress.setPercent(pct)
                except Exception:
                    pass
                if monitor.waitForAbort(1):
                    break
        finally:
            try:
                self.close()
            except Exception:
                pass

    def onAction(self, action):
        aid = action.getId()
        if aid in (_ACTION_PREVIOUS_MENU, _ACTION_NAV_BACK):
            self.closed = True
            self.close()
        elif aid == _ACTION_SELECT_ITEM:
            ctrl = self.getFocus() if hasattr(self, "getFocus") else None
            self.onControl(ctrl)

    def onControl(self, control):
        if control is None:
            return
        cid = control.getId()
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
    """Open the Skip Intro popup (programmatic, non-modal)."""
    try:
        SkipIntroDialog(intro_end).show_and_run()
    except Exception as e:
        xbmc.log("[movieRec] skip-intro popup error: %s" % e, xbmc.LOGWARNING)


def show_playing_next(outro_end=0):
    """Open the Playing Next popup (programmatic, non-modal)."""
    try:
        PlayingNextDialog(outro_end).show_and_run()
    except Exception as e:
        xbmc.log("[movieRec] playing-next popup error: %s" % e, xbmc.LOGWARNING)
