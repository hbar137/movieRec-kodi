"""otaku_scrapers package — vendored Otaku per-site anime scrapers.

This __init__ runs once when the package is first imported. We use it
to install a small malsync compatibility patch: Otaku's scrapers
(especially AnimePahe) bail early when malsync.get_title returns None,
which happens whenever a show's mal_id is 0 or simply isn't in
malsync's database (the case for many obscure / brand-new titles like
"African Office Worker").

The patch falls back to the show title we already have locally — set
via control.set_show_context(...) before any scraper is invoked. With
this in place a missing malsync entry is no longer a hard stop.

Lives in this __init__ rather than the vendored malsync.py because
scripts/update-otaku-scrapers.py overwrites the vendored file on every
refresh. This file is on the OURS list and stays put.
"""

from .endpoints import malsync as _malsync
from .ui import control as _control


_orig_get_title = _malsync.get_title


def _patched_get_title(mal_id, site=""):
    title = None
    if mal_id:
        try:
            title = _orig_get_title(mal_id, site)
        except Exception:
            title = None
    if not title:
        title = (_control.get_show_context() or {}).get("title") or None
    return title


_malsync.get_title = _patched_get_title
