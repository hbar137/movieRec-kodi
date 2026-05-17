"""Thin replacement for Otaku's resources.lib.ui.utils.

Otaku's full utils handles directory listings, playback state, artwork
manipulation, and parallel HTTP fan-out. The scrapers only call:

  utils.parallel_process(items, fn) → list(thread-pool map of fn over items)
  utils.allocate_item(...)          → BrowserBase paginator placeholder
                                       (we don't surface paginated lists)

License: scaffolding (no Otaku code here).
"""
import concurrent.futures


def parallel_process(items, fn, max_workers=10):
    if not items:
        return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        return list(ex.map(fn, items))


def allocate_item(*args, **kwargs):
    # BrowserBase uses this to build the "Next page →" entry it appends
    # to provider result lists. We don't render that from the embed
    # picker (we just want the source list), so the return value is
    # never inspected.
    return {}


def to_unicode(s, enc="utf-8", errors="ignore"):
    if isinstance(s, bytes):
        return s.decode(enc, errors=errors)
    return s


def safe_int(s, default=0):
    try:
        return int(s)
    except (TypeError, ValueError):
        return default
