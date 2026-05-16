"""Minimal BaseWindow — covers what skip_intro.py and playing_next.py
inherit. Otaku's full BaseWindow loads anime metadata from their local
database + sets ~15 window properties from pickled artwork. We don't
have that database; we set only the small set of properties that the
playing_next_default.xml + skip_outro_default.xml actually read:

  - item.info.tvshowtitle  (the show title)
  - item.info.title        (the episode title)
  - item.art.thumb         (the episode thumb URL)

For skip_intro, no properties are needed (the XML has only buttons,
no metadata fields). Otaku's BaseWindow early-returns on item_type ==
'skip_intro' — we preserve that behavior.

License: GPL-3.0 (derived from Otaku).
"""
import xbmcgui

from . import control


class BaseWindow(xbmcgui.WindowXMLDialog):
    def __init__(self, xml_file, location, actionArgs=None):
        super().__init__(xml_file, location)
        control.closeBusyDialog()

        # Otaku-faithful early exit for the skip-intro popup (no metadata)
        if actionArgs is None or actionArgs.get("item_type") == "skip_intro":
            return

        # playing_next path — actionArgs carries the next-episode preview
        # data the XML reads via Window.Property(...).
        self.item_information = dict(actionArgs)
        self._set_window_properties()

    def _set_window_properties(self):
        thumb = self.item_information.get("thumb") or self.item_information.get("item.art.thumb") or ""
        if isinstance(thumb, list):
            thumb = thumb[0] if thumb else ""
        try:
            self.setProperty("item.art.thumb", str(thumb))
        except Exception:
            pass

        # The XML uses Window.Property(item.info.tvshowtitle); Otaku populates
        # it from item_information['tvshowtitle']. PlayingNext's actionArgs
        # in our wiring sets 'name' as the show title — accept either.
        tvshow = (self.item_information.get("tvshowtitle")
                  or self.item_information.get("name")
                  or self.item_information.get("item.info.tvshowtitle")
                  or "")
        try:
            self.setProperty("item.info.tvshowtitle", str(tvshow))
        except Exception:
            pass

        title = (self.item_information.get("title")
                 or self.item_information.get("item.info.title")
                 or "")
        try:
            self.setProperty("item.info.title", str(title))
        except Exception:
            pass
