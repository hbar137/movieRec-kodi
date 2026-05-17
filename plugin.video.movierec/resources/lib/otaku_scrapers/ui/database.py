"""Thin replacement for Otaku's resources.lib.ui.database.

Otaku's real database is sqlite-backed with per-call caching keyed by
callback name + args. The scrapers only use a tiny slice of it:

  database.get(callback, ttl_hours, *args, **kwargs)
     → cached call; we just invoke callback directly (no cache).
  database.get_show(mal_id)
     → row dict with 'kodi_meta' (pickled) carrying the show title.
       We hand it back from a thread-local context that
       pick_embed_source populates before calling a scraper.

No persistent caching means we re-scrape per resolve. That's fine for
the embed-picker flow (rare, user-initiated). If perf ever matters
here we can add an LRU keyed by (callback_name, args_hash).

License: scaffolding (no Otaku code here).
"""
import pickle

from . import control


def get(callback, ttl_hours, *args, **kwargs):
    return callback(*args, **kwargs)


def get_show(mal_id):
    """Mimic Otaku's stored show row shape.

    Otaku's pages/*.py do:
        show = database.get_show(mal_id)
        kodi_meta = pickle.loads(show.get('kodi_meta'))
        title = kodi_meta.get('name')

    We pull the title (and start_date for year-disambiguated search)
    from a thread-local set by the caller.
    """
    ctx = control.get_show_context()
    kodi_meta = {
        "name": ctx.get("title", ""),
        "start_date": ctx.get("start_date", ""),
    }
    return {"kodi_meta": pickle.dumps(kodi_meta), "mal_id": ctx.get("mal_id", 0)}


def get_show_meta(mal_id):
    return get_show(mal_id)


def cache_function(func, *args, **kwargs):
    return func(*args, **kwargs)


def clear_cache():
    pass
