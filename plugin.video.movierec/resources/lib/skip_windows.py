"""WindowXMLDialog popups for anime: Skip Intro and Playing Next.

Both classes are non-modal — they overlay the video while it keeps
playing. Each has a background polling loop that auto-closes the popup
when its time window passes.

XML files: resources/skins/Default/1080i/{skip_intro,playing_next}.xml
Control IDs are hardcoded to match the XML:
  skip_intro:  3001 Skip   / 3002 Close
  playing_next: 3001 PlayNow / 3002 Close / 3003 SkipOutro / 3014 progressbar
"""
import xbmc
import xbmcgui

_ADDON_ID = "plugin.video.movierec"


class SkipIntroDialog(xbmcgui.WindowXMLDialog):
    """Popup shown when current_time is inside [intro_start, intro_end].
    Background loop closes it once we pass intro_end so the user isn't
    nagged after the intro is over.

    Constructor must pass `xml_file, location` positional args to
    super().__init__ — that's Otaku's BaseWindow pattern (verified
    against their Matrix-19 working addon). Passing zero args or extra
    defaultSkin/defaultRes args both break the C++-side XML lookup."""

    def __init__(self, xml_file, location, **kwargs):
        super().__init__(xml_file, location)
        self.intro_end = kwargs.get("intro_end") or 0
        self.player = xbmc.Player()
        self.playing_file = self.player.getPlayingFile() if self.player.isPlaying() else ""
        self.closed = False

    def onInit(self):
        # Poll player.getTime; auto-close when we pass intro_end.
        try:
            monitor = xbmc.Monitor()
            while not self.closed and self.player.isPlaying():
                cur = int(self.player.getTime())
                if cur >= self.intro_end:
                    break
                if monitor.waitForAbort(1):
                    break
        except RuntimeError:
            pass
        self.close()

    def onAction(self, action):
        if action.getId() in (10, 92):  # ESC / BACK
            self.close()

    def onClick(self, controlID):
        if controlID == 3001:
            # Skip Intro → seek to intro_end.
            try:
                self.player.seekTime(self.intro_end)
            except RuntimeError:
                pass
            self.close()
        elif controlID == 3002:
            self.close()

    def close(self):
        self.closed = True
        super().close()


class PlayingNextDialog(xbmcgui.WindowXMLDialog):
    """Popup shown in the last ~30s of an episode. Three buttons:
       Play Now → seek near end so the natural-end autoplay watcher fires.
       Skip Outro → seek to outro_end (if known) or near end.
       Close → dismiss.
    Plus a progress bar (control 3014) counting down to natural end.

    Same constructor pattern as SkipIntroDialog — mirror Otaku's
    BaseWindow signature exactly."""

    def __init__(self, xml_file, location, **kwargs):
        super().__init__(xml_file, location)
        self.outro_end = kwargs.get("outro_end") or 0
        self.player = xbmc.Player()
        self.playing_file = self.player.getPlayingFile() if self.player.isPlaying() else ""
        self.total_time = 0
        try:
            self.total_time = int(self.player.getTotalTime() or 0)
        except RuntimeError:
            pass
        self.duration = max(self.total_time - int(self.player.getTime() or 0), 1)
        self.closed = False

    def onInit(self):
        progress = None
        try:
            progress = self.getControl(3014)
        except Exception:
            pass
        try:
            monitor = xbmc.Monitor()
            while not self.closed and self.player.isPlaying():
                cur = int(self.player.getTime())
                remaining = self.total_time - cur
                if remaining <= 2:
                    break
                if progress is not None:
                    pct = max(0, min(100, int((remaining / self.duration) * 100)))
                    try:
                        progress.setPercent(pct)
                    except Exception:
                        pass
                if monitor.waitForAbort(1):
                    break
        except RuntimeError:
            pass
        self.close()

    def onAction(self, action):
        if action.getId() in (10, 92):
            self.close()

    def onClick(self, controlID):
        try:
            if controlID == 3001:  # Play Now → near end
                self.player.seekTime(max(self.total_time - 5, 0))
            elif controlID == 3003:  # Skip Outro
                if self.outro_end and self.outro_end > 0:
                    self.player.seekTime(self.outro_end)
                else:
                    self.player.seekTime(max(self.total_time - 5, 0))
        except RuntimeError:
            pass
        self.close()

    def close(self):
        self.closed = True
        super().close()


def show_skip_intro(intro_end):
    """Open the Skip Intro popup (non-modal). intro_end in seconds.

    Pass exactly TWO positional args (xml_file, addon_path) — mirrors
    Otaku's invocation (`SkipIntro(xml_file, control.ADDON_PATH, actionArgs=args).doModal()`).
    Kodi 19+ auto-detects the resolution from the addon's available skin
    subfolders, so passing defaultSkin/defaultRes is unnecessary and in
    some Kodi builds actively breaks the XML lookup."""
    try:
        dlg = SkipIntroDialog("skip_intro.xml", _addon_path(), intro_end=intro_end)
        dlg.doModal()
        del dlg
    except Exception as e:
        xbmc.log("[movieRec] skip-intro popup error: %s" % e, xbmc.LOGWARNING)


def show_playing_next(outro_end=0):
    """Open the Playing Next popup (non-modal). outro_end in seconds (0 = unknown)."""
    try:
        dlg = PlayingNextDialog("playing_next.xml", _addon_path(), outro_end=outro_end)
        dlg.doModal()
        del dlg
    except Exception as e:
        xbmc.log("[movieRec] playing-next popup error: %s" % e, xbmc.LOGWARNING)


def _addon_path():
    import xbmcaddon
    return xbmcaddon.Addon(_ADDON_ID).getAddonInfo("path")
