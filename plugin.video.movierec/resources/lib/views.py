"""Directory views: root menu, dashboard, watchlist, history, browse, search, movie detail."""
import json
import os
import sys
import urllib.parse

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

from . import api

ADDON = xbmcaddon.Addon()

_SEARCH_HISTORY_FILE = os.path.join(
    xbmcvfs.translatePath("special://profile/addon_data/plugin.video.movierec/"),
    "search_history.json",
)
_SEARCH_HISTORY_MAX = 20


def _load_search_history():
    try:
        with open(_SEARCH_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [str(q) for q in data if q]
    except (OSError, ValueError):
        pass
    return []


def _save_search_history(history):
    d = os.path.dirname(_SEARCH_HISTORY_FILE)
    try:
        os.makedirs(d, exist_ok=True)
        with open(_SEARCH_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history[:_SEARCH_HISTORY_MAX], f, ensure_ascii=False)
    except OSError:
        pass


def _record_search(query):
    q = (query or "").strip()
    if not q:
        return
    history = _load_search_history()
    # MRU: drop any case-insensitive duplicate, prepend the new query.
    history = [h for h in history if h.lower() != q.lower()]
    history.insert(0, q)
    _save_search_history(history)


def _clear_search_history():
    try:
        os.remove(_SEARCH_HISTORY_FILE)
    except OSError:
        pass


def _url(**kwargs):
    base = sys.argv[0]
    return base + "?" + urllib.parse.urlencode({k: v for k, v in kwargs.items() if v is not None})


def _page_size():
    try:
        return int(ADDON.getSettingInt("page_size"))
    except Exception:
        return 40


def _poster_url(poster_path):
    if not poster_path:
        return ""
    if poster_path.startswith("http"):
        return poster_path
    return "https://image.tmdb.org/t/p/w500" + poster_path


def _parse_rt_percent(s):
    """RT scores arrive as strings like '99%' or '99'. Return float 0-100."""
    if not s:
        return 0.0
    try:
        return float(str(s).strip().rstrip("%"))
    except ValueError:
        return 0.0


def _attach_ratings(li, movie, rating):
    """Surface up to five ratings on the ListItem so the skin's info pane can
    render them while the user scrolls. Uses Kodi's standard setRating() for
    the four types Estuary and most third-party skins know about, plus
    Rating.* properties (Seren/Fenlight convention) so skins that read
    properties — and Filmarks, which has no standard rating type — still
    display.

    `movie` is the API's Movie dict (carries tmdb_vote_average); `rating` is
    the per-row card-rating dict from /browse, /watchlist, /search etc.
    `rating` may be None on TMDB-only search rows."""
    rating = rating or {}

    # IMDb (0-10) — also used as the default rating Kodi shows on row labels.
    try:
        imdb = float(rating.get("imdb_rating") or 0)
    except (TypeError, ValueError):
        imdb = 0.0
    try:
        imdb_votes = int(rating.get("imdb_vote_count") or 0)
    except (TypeError, ValueError):
        imdb_votes = 0
    if imdb > 0:
        li.setRating("imdb", imdb, imdb_votes, True)
        li.setProperty("Rating.IMDb", "%.1f" % imdb)
        if imdb_votes > 0:
            li.setProperty("Votes.IMDb", str(imdb_votes))

    # TMDB (0-10) — comes from movies table.
    try:
        tmdb = float(movie.get("tmdb_vote_average") or 0)
    except (TypeError, ValueError):
        tmdb = 0.0
    try:
        tmdb_votes = int(movie.get("tmdb_vote_count") or 0)
    except (TypeError, ValueError):
        tmdb_votes = 0
    if tmdb > 0:
        # Mark TMDB as default only if we don't have IMDb — gives the row a
        # visible rating either way.
        li.setRating("tmdb", tmdb, tmdb_votes, imdb <= 0)
        li.setProperty("Rating.TMDb", "%.1f" % tmdb)

    # Rotten Tomatoes (0-100; the "tomatoes" rating type is the meter score).
    rt_pct = _parse_rt_percent(rating.get("rt_score"))
    if rt_pct > 0:
        li.setRating("tomatoes", rt_pct, 0, False)
        li.setProperty("Rating.RT", "%d%%" % int(round(rt_pct)))

    # Metacritic (0-100).
    try:
        mc = int(rating.get("metacritic") or 0)
    except (TypeError, ValueError):
        mc = 0
    if mc > 0:
        li.setRating("metacritic", float(mc), 0, False)
        li.setProperty("Rating.Metacritic", str(mc))

    # Filmarks: no standard Kodi rating type. Stored 0-5; surface 0-10 to
    # match the web UI. Skins that read Rating.* properties (Seren/Fenlight
    # style) can render this.
    try:
        fm = float(rating.get("filmarks_rating") or 0)
    except (TypeError, ValueError):
        fm = 0.0
    if fm > 0:
        li.setProperty("Rating.Filmarks", "%.1f" % (fm * 2.0))


def _inline_rating_suffix(movie, rating):
    """Compose a compact ratings suffix like
    `  [COLOR khaki]IMDb 7.4[/COLOR] · [COLOR cyan]TMDB 7.4[/COLOR] · ...`
    so the user can see scores while scrolling on every skin (Estuary
    included — it doesn't render multi-rating panels). Sources missing for
    a movie are simply skipped."""
    rating = rating or {}
    parts = []

    try:
        imdb = float(rating.get("imdb_rating") or 0)
    except (TypeError, ValueError):
        imdb = 0.0
    if imdb > 0:
        parts.append("[COLOR khaki]IMDb %.1f[/COLOR]" % imdb)

    try:
        tmdb = float(movie.get("tmdb_vote_average") or 0)
    except (TypeError, ValueError):
        tmdb = 0.0
    if tmdb > 0:
        parts.append("[COLOR deepskyblue]TMDB %.1f[/COLOR]" % tmdb)

    rt_pct = _parse_rt_percent(rating.get("rt_score"))
    if rt_pct > 0:
        parts.append("[COLOR tomato]RT %d%%[/COLOR]" % int(round(rt_pct)))

    try:
        mc = int(rating.get("metacritic") or 0)
    except (TypeError, ValueError):
        mc = 0
    if mc > 0:
        parts.append("[COLOR limegreen]MC %d[/COLOR]" % mc)

    try:
        fm = float(rating.get("filmarks_rating") or 0)
    except (TypeError, ValueError):
        fm = 0.0
    if fm > 0:
        parts.append("[COLOR orange]FM %.1f[/COLOR]" % (fm * 2.0))

    if not parts:
        return ""
    return "  " + " · ".join(parts)


def _format_runtime(minutes):
    try:
        m = int(minutes or 0)
    except (TypeError, ValueError):
        return ""
    if m <= 0:
        return ""
    h, rem = divmod(m, 60)
    if h <= 0:
        return "%dm" % rem
    if rem == 0:
        return "%dh" % h
    return "%dh %dm" % (h, rem)


def _meta_line(movie):
    parts = []
    year = movie.get("year") or 0
    if year:
        parts.append(str(year))
    rt = _format_runtime(movie.get("runtime"))
    if rt:
        parts.append(rt)
    return " · ".join(parts)


def _plot_with_ratings(movie, rating):
    """Prepend a meta line (year · runtime) and a colour-coded ratings line
    to the plot text. Estuary's Wide List, Info Wall, and similar views
    render ListItem.Plot in their info panel — so this is how we surface
    metadata + ratings while the user scrolls, without touching the row
    labels themselves."""
    plot = movie.get("overview") or ""
    header_lines = []
    meta = _meta_line(movie)
    if meta:
        header_lines.append("[B]%s[/B]" % meta)
    ratings = _inline_rating_suffix(movie, rating).strip()
    if ratings:
        header_lines.append(ratings)
    if not header_lines:
        return plot
    header = "\n".join(header_lines)
    if not plot:
        return header
    return header + "\n\n" + plot


def _movie_listitem(movie, rating=None, watched=False, rd_available=False):
    title = movie.get("title", "")
    year = movie.get("year") or 0
    label = "%s (%d)" % (title, year) if year else title
    if rd_available:
        label = "[COLOR green][RD][/COLOR] " + label
    if watched:
        label = "[COLOR gray][WATCHED][/COLOR] " + label

    li = xbmcgui.ListItem(label=label)
    poster = _poster_url(movie.get("poster_path"))
    li.setArt({"poster": poster, "thumb": poster, "fanart": poster})

    info = {
        "title": title,
        "year": year,
        "plot": _plot_with_ratings(movie, rating),
        "mediatype": "movie",
    }
    if movie.get("imdb_id"):
        info["imdbnumber"] = movie["imdb_id"]
    li.setInfo("video", info)

    _attach_ratings(li, movie, rating)
    return li


def root(handle):
    xbmcplugin.setPluginCategory(handle, "movieRec")
    xbmcplugin.setContent(handle, "files")
    items = [
        ("Dashboard", _url(action="dashboard")),
        ("Watchlist", _url(action="watchlist")),
        ("Shows", _url(action="shows_root")),
        ("History", _url(action="history")),
        ("Browse", _url(action="browse_menu")),
        ("Search", _url(action="search")),
    ]
    for label, url in items:
        li = xbmcgui.ListItem(label=label)
        li.setArt({"icon": "DefaultFolder.png"})
        xbmcplugin.addDirectoryItem(handle, url, li, isFolder=True)
    xbmcplugin.endOfDirectory(handle)


def _add_movie(handle, movie, rating, watched, rd_available):
    li = _movie_listitem(movie, rating=rating, watched=watched, rd_available=rd_available)
    url = _url(action="movie", movie_id=movie["id"])
    xbmcplugin.addDirectoryItem(handle, url, li, isFolder=True)


def _section_header(handle, label):
    sep = xbmcgui.ListItem(label="[B]── %s ──[/B]" % label)
    xbmcplugin.addDirectoryItem(handle, _url(action="root"), sep, isFolder=False)


def dashboard(handle):
    data = api.get("/dashboard")
    xbmcplugin.setPluginCategory(handle, "Dashboard")
    xbmcplugin.setContent(handle, "movies")

    ratings = data.get("ratings") or {}
    watched_map = data.get("watched") or {}
    rd_map = data.get("rd_available") or {}

    def _rd(mid):
        return bool(rd_map.get(str(mid)) or rd_map.get(mid))

    def _r(mid):
        return ratings.get(str(mid)) or ratings.get(mid)

    seen_section = False

    # 1. New on Digital / VOD — watchlist alerts only
    alerts = data.get("letterboxd_alerts") or []
    wl_alerts = [a for a in alerts if a.get("alert_type") == "watchlist" and a.get("movie")]
    if wl_alerts:
        _section_header(handle, "New on Digital / VOD")
        for a in wl_alerts:
            m = a.get("movie") or {}
            mid = a.get("movie_id") or m.get("id")
            m["id"] = mid
            _add_movie(handle, m, _r(mid), bool(watched_map.get(str(mid))), _rd(mid))
        seen_section = True

    # 2. Your Watchlist
    wl = data.get("watchlist") or []
    if wl:
        _section_header(handle, "Your Watchlist")
        for w in wl:
            m = w.get("movie") or {}
            mid = w["movie_id"]
            m["id"] = mid
            _add_movie(handle, m, _r(mid), bool(watched_map.get(str(mid))), _rd(mid))
        seen_section = True

    # 3. Top Rated on Your Watchlist (server's top_unwatched is highest-rated unwatched watchlist items)
    top = data.get("top_unwatched") or []
    if top:
        _section_header(handle, "Top Rated on Your Watchlist")
        for m in top:
            mid = m["id"]
            _add_movie(handle, m, _r(mid), False, _rd(mid))
        seen_section = True

    if not seen_section:
        li = xbmcgui.ListItem(label="(Empty dashboard)")
        xbmcplugin.addDirectoryItem(handle, _url(action="root"), li, isFolder=False)

    xbmcplugin.endOfDirectory(handle)


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

_BROWSE_SORTS = [
    ("popularity_desc", "Popularity ↓"),
    ("popularity_asc", "Popularity ↑"),
    ("rating_desc", "Rating ↓"),
    ("rating_asc", "Rating ↑"),
    ("year_desc", "Year ↓"),
    ("year_asc", "Year ↑"),
    ("title_asc", "Title A→Z"),
]

_WATCHLIST_SORTS = [
    ("priority_desc", "Priority ↓"),
    ("priority_asc", "Priority ↑"),
    ("added_desc", "Date added ↓"),
    ("added_asc", "Date added ↑"),
    ("rating_desc", "Rating ↓"),
    ("year_desc", "Year ↓"),
    ("title_asc", "Title A→Z"),
]


_LANGUAGE_NAMES_CACHE = {}
_COUNTRY_NAMES_CACHE = {}


def _code_name_lookup(field, target_action):
    """Fetch /languages or /countries for the given scope, returning
    (items, name_by_code). Both are cached per (field, scope) within the
    process so back-and-forth between filter rows doesn't re-hit the API."""
    cache = _LANGUAGE_NAMES_CACHE if field == "language" else _COUNTRY_NAMES_CACHE
    key = target_action
    if key in cache:
        return cache[key]
    path = "/languages" if field == "language" else "/countries"
    try:
        items = api.get(path, scope=target_action) or []
    except api.APIError:
        items = []
    name_by_code = {it.get("code"): it.get("name") or it.get("code") for it in items}
    cache[key] = (items, name_by_code)
    return items, name_by_code


def _row_value(field, state, sort_options, target_action="browse"):
    if field == "sort":
        s = state.get("sort")
        return dict(sort_options).get(s, "default") if s else "default"
    if field == "genre":
        return state.get("genre") or "any"
    if field == "language":
        code = state.get("language")
        if not code:
            return "any"
        _, names = _code_name_lookup("language", target_action)
        return names.get(code, code)
    if field == "country":
        code = state.get("country")
        if not code:
            return "any"
        _, names = _code_name_lookup("country", target_action)
        return names.get(code, code)
    if field == "year":
        ymin, ymax = state.get("year_min"), state.get("year_max")
        if not ymin and not ymax:
            return "any"
        return "%s – %s" % (ymin or "…", ymax or "…")
    if field == "rating":
        return state.get("rating_min") or "any"
    if field == "rd":
        return "yes" if state.get("rd_available") == "true" else "no"
    return ""


def _has_active_filters(state):
    return any(state.get(k) for k in
               ("sort", "genre", "language", "country",
                "year_min", "year_max", "rating_min", "rd_available"))


def set_filter(handle, target_action, field, current):
    """Apply one filter change, then redirect to the target listing URL via
    Container.Update(...,replace) so the set_filter entry never stays in the
    navigation stack — otherwise pressing back from a movie detail re-triggers
    set_filter and reopens the picker dialog."""
    dlg = xbmcgui.Dialog()
    state = dict(current)
    sort_options = _WATCHLIST_SORTS if target_action == "watchlist" else _BROWSE_SORTS

    # Drop transient keys before mutating
    state.pop("page", None)
    state.pop("action", None)
    state.pop("target", None)
    state.pop("field", None)

    if field == "clear":
        state = {}

    elif field == "rd":
        if state.get("rd_available") == "true":
            state.pop("rd_available", None)
        else:
            state["rd_available"] = "true"

    elif field == "sort":
        labels = ["(default)"] + [lbl for _, lbl in sort_options]
        cur = state.get("sort")
        preselect = 0
        for idx, (k, _) in enumerate(sort_options, start=1):
            if k == cur:
                preselect = idx
                break
        i = dlg.select("Sort by", labels, preselect=preselect)
        if i == 0:
            state.pop("sort", None)
        elif i > 0:
            state["sort"] = sort_options[i - 1][0]
        # i < 0 → cancelled; keep current state and re-render unchanged.

    elif field == "genre":
        # Scope the dropdown to the current view so the user only sees genres
        # that actually have movies behind them (avoids picking e.g. Drama in
        # a watchlist where no watchlisted movie carries that genre).
        try:
            genres = api.get("/genres", scope=target_action) or []
        except api.APIError:
            genres = []
        labels = ["(any)"] + list(genres)
        preselect = 0
        cur = state.get("genre")
        if cur and cur in genres:
            preselect = genres.index(cur) + 1
        i = dlg.select("Genre", labels, preselect=preselect)
        if i == 0:
            state.pop("genre", None)
        elif i > 0:
            state["genre"] = genres[i - 1]

    elif field in ("language", "country"):
        # Re-fetch fresh (don't reuse the row-render cache) so a newly added
        # movie shows up in the dropdown without restarting Kodi.
        path = "/languages" if field == "language" else "/countries"
        title = "Language" if field == "language" else "Country"
        try:
            items = api.get(path, scope=target_action) or []
        except api.APIError:
            items = []
        codes = [it.get("code") for it in items]
        labels = ["(any)"] + [it.get("name") or it.get("code") for it in items]
        preselect = 0
        cur = state.get(field)
        if cur and cur in codes:
            preselect = codes.index(cur) + 1
        i = dlg.select(title, labels, preselect=preselect)
        if i == 0:
            state.pop(field, None)
        elif i > 0:
            state[field] = codes[i - 1]

    elif field == "year":
        ymin = dlg.input("Year from (blank = any)",
                         state.get("year_min") or "", type=xbmcgui.INPUT_NUMERIC)
        ymax = dlg.input("Year to (blank = any)",
                         state.get("year_max") or "", type=xbmcgui.INPUT_NUMERIC)
        if ymin:
            state["year_min"] = ymin
        else:
            state.pop("year_min", None)
        if ymax:
            state["year_max"] = ymax
        else:
            state.pop("year_max", None)

    elif field == "rating":
        r = dlg.input("Min IMDB rating 0-10 (blank = any)",
                      state.get("rating_min") or "", type=xbmcgui.INPUT_NUMERIC)
        if r:
            state["rating_min"] = r
        else:
            state.pop("rating_min", None)

    # Hybrid: render the target listing in-place via updateListing=True so the
    # filter takes effect instantly (this is the only path that reliably draws
    # on Bravia/Android TV — Container.Update alone is dropped silently there).
    # Then fire Container.Update with the target URL and `replace` so the
    # set_filter entry is swapped out of the back stack. If that builtin is
    # honored, back from a movie detail lands on the filtered listing; if it's
    # dropped, the visible filter still applied — we just regress to "back
    # reopens the dialog" instead of breaking the filter.
    if target_action == "watchlist":
        watchlist(handle, page=0, params=state, update_listing=True)
    else:
        browse(handle, page=0, params=state, update_listing=True)

    target_url = _url(action=target_action, **state)
    xbmc.executebuiltin("Container.Update(%s,replace)" % target_url)


_FILTER_FIELDS = [
    ("sort",     "Sort"),
    ("genre",    "Genre"),
    ("language", "Language"),
    ("country",  "Country"),
    ("year",     "Year"),
    ("rating",   "Min IMDB"),
    ("rd",       "Real-Debrid"),
]


def _add_filter_entries(handle, action, current, sort_options):
    """Render one row per filter at the top of the listing. Each row shows
    the field name and its current value; clicking the row pops a single
    focused dialog and re-renders the list with the new value.

    Each row sets the SpecialSort=top property so Kodi's skin keeps these
    rows pinned above the movies even when the user toggles its native
    sort/order in the side panel."""
    base = {k: v for k, v in current.items() if k != "action"}
    icon = "DefaultAddonsSearch.png"

    for field, label in _FILTER_FIELDS:
        value = _row_value(field, current, sort_options, target_action=action)
        row_label = "[COLOR cyan]» %s:[/COLOR] [COLOR yellow]%s[/COLOR]" % (label, value)
        li = xbmcgui.ListItem(label=row_label)
        li.setArt({"icon": icon, "thumb": icon})
        li.setProperty("SpecialSort", "top")
        url = _url(action="set_filter", target=action, field=field, **base)
        xbmcplugin.addDirectoryItem(handle, url, li, isFolder=True)

    if _has_active_filters(current):
        clear_li = xbmcgui.ListItem(label="[COLOR red]» Clear all filters[/COLOR]")
        clear_li.setArt({"icon": icon, "thumb": icon})
        clear_li.setProperty("SpecialSort", "top")
        clear_url = _url(action="set_filter", target=action, field="clear")
        xbmcplugin.addDirectoryItem(handle, clear_url, clear_li, isFolder=True)


# ---------------------------------------------------------------------------
# Paged listings
# ---------------------------------------------------------------------------


def _paged_list(handle, response, items_key, get_movie, page, action_kwargs, update_listing=False):
    items = response.get(items_key) or []
    total = response.get("total") or 0
    limit = response.get("limit") or _page_size()
    ratings = response.get("ratings") or {}
    watched_map = response.get("watched") or {}
    rd_map = response.get("rd_available") or {}

    xbmcplugin.setContent(handle, "movies")
    for item in items:
        m = get_movie(item)
        mid = m["id"]
        r = ratings.get(str(mid)) or ratings.get(mid)
        w = bool(watched_map.get(str(mid)) or watched_map.get(mid))
        rd = bool(rd_map.get(str(mid)) or rd_map.get(mid))
        _add_movie(handle, m, r, w, rd)

    if (page + 1) * limit < total:
        kwargs = dict(action_kwargs)
        kwargs["page"] = page + 1
        next_li = xbmcgui.ListItem(label="Next page →")
        xbmcplugin.addDirectoryItem(handle, _url(**kwargs), next_li, isFolder=True)

    xbmcplugin.endOfDirectory(handle, updateListing=update_listing, cacheToDisc=False)


_FILTER_KEYS = ("sort", "genre", "language", "country",
                "year_min", "year_max", "rating_min", "rd_available")


def _filter_kwargs(params):
    return {k: params[k] for k in _FILTER_KEYS if params.get(k)}


def watchlist(handle, page, params, update_listing=False):
    limit = _page_size()
    api_kwargs = dict(_filter_kwargs(params))
    api_kwargs.update({"page": page, "limit": limit})
    data = api.get("/watchlist", **api_kwargs)
    xbmcplugin.setPluginCategory(handle, "Watchlist")

    current = dict(_filter_kwargs(params))
    _add_filter_entries(handle, "watchlist", current, _WATCHLIST_SORTS)

    def get_movie(item):
        m = item.get("movie") or {}
        m["id"] = item["movie_id"]
        return m

    action_kwargs = {"action": "watchlist"}
    action_kwargs.update(current)
    _paged_list(handle, data, "items", get_movie, page, action_kwargs, update_listing=update_listing)


def history(handle, page=0):
    limit = _page_size()
    data = api.get("/history", page=page, limit=limit)
    xbmcplugin.setPluginCategory(handle, "History")

    def get_movie(item):
        m = item.get("movie") or {}
        m["id"] = item["movie_id"]
        return m

    _paged_list(handle, data, "entries", get_movie, page, {"action": "history"})


def shows_root(handle):
    xbmcplugin.setPluginCategory(handle, "Shows")
    items = [
        ("All shows", _url(action="shows_browse")),
        ("Show watchlist", _url(action="show_watchlist")),
    ]
    for label, url in items:
        li = xbmcgui.ListItem(label=label)
        li.setArt({"icon": "DefaultFolder.png"})
        xbmcplugin.addDirectoryItem(handle, url, li, isFolder=True)
    xbmcplugin.endOfDirectory(handle)


def browse_menu(handle):
    xbmcplugin.setPluginCategory(handle, "Browse")
    items = [
        ("All movies", _url(action="browse")),
        ("By genre", _url(action="genres")),
    ]
    for label, url in items:
        li = xbmcgui.ListItem(label=label)
        xbmcplugin.addDirectoryItem(handle, url, li, isFolder=True)
    xbmcplugin.endOfDirectory(handle)


def genres(handle):
    data = api.get("/genres") or []
    xbmcplugin.setPluginCategory(handle, "Genres")
    for g in data:
        li = xbmcgui.ListItem(label=g)
        xbmcplugin.addDirectoryItem(handle, _url(action="browse", genre=g), li, isFolder=True)
    xbmcplugin.endOfDirectory(handle)


def browse(handle, page, params, update_listing=False):
    limit = _page_size()
    api_kwargs = dict(_filter_kwargs(params))
    api_kwargs.update({"page": page, "limit": limit})
    data = api.get("/browse", **api_kwargs)
    xbmcplugin.setPluginCategory(handle, params.get("genre") or "Browse")

    current = dict(_filter_kwargs(params))
    _add_filter_entries(handle, "browse", current, _BROWSE_SORTS)

    action_kwargs = {"action": "browse"}
    action_kwargs.update(current)
    _paged_list(handle, data, "movies", lambda m: m, page, action_kwargs, update_listing=update_listing)


def search(handle):
    """Show 'New search…' prompt + past searches as a directory listing.
    Picking a past query re-runs it; picking 'New search…' opens the input
    dialog and records the result."""
    xbmcplugin.setPluginCategory(handle, "Search")
    xbmcplugin.setContent(handle, "files")

    new_li = xbmcgui.ListItem(label="[B]» New search…[/B]")
    new_li.setArt({"icon": "DefaultAddonsSearch.png"})
    new_li.setProperty("SpecialSort", "top")
    xbmcplugin.addDirectoryItem(handle, _url(action="search_new"), new_li, isFolder=True)

    history = _load_search_history()
    if history:
        sep = xbmcgui.ListItem(label="[B]── Past searches ──[/B]")
        sep.setProperty("SpecialSort", "top")
        xbmcplugin.addDirectoryItem(handle, _url(action="search"), sep, isFolder=False)

        for q in history:
            li = xbmcgui.ListItem(label=q)
            li.setArt({"icon": "DefaultAddonsSearch.png"})
            xbmcplugin.addDirectoryItem(handle,
                                        _url(action="search_results", q=q),
                                        li, isFolder=True)

        clear_li = xbmcgui.ListItem(label="[COLOR red]» Clear search history[/COLOR]")
        clear_li.setArt({"icon": "DefaultAddonsSearch.png"})
        xbmcplugin.addDirectoryItem(handle, _url(action="search_clear"), clear_li, isFolder=True)

    xbmcplugin.endOfDirectory(handle)


def search_new(handle):
    """Pop the input dialog, record the query, and render results."""
    kb = xbmcgui.Dialog().input("Search movieRec", type=xbmcgui.INPUT_ALPHANUM)
    if not kb:
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return
    _record_search(kb)
    search_results(handle, kb)


def search_clear(handle):
    """Confirm + clear search history, then redraw the search root."""
    if xbmcgui.Dialog().yesno("Search history",
                              "Clear all saved searches?",
                              nolabel="Cancel", yeslabel="Clear"):
        _clear_search_history()
    # Re-render the search root in place so the user sees the cleared state.
    xbmc.executebuiltin("Container.Update(%s,replace)" % _url(action="search"))
    xbmcplugin.endOfDirectory(handle, succeeded=False)


def search_results(handle, query):
    """Combined local + TMDB search. Local hits render first; TMDB-only hits
    render below a section header. Clicking a TMDB-only hit triggers an
    import-then-open flow (see `import_movie`)."""
    if not query:
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return
    _record_search(query)

    try:
        data = api.get("/search", q=query) or {}
    except api.APIError as e:
        api.handle_error(e)
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return

    local = data.get("local") or []
    tmdb_only = data.get("tmdb") or []

    xbmcplugin.setPluginCategory(handle, "Search: %s" % query)
    xbmcplugin.setContent(handle, "movies")

    if not local and not tmdb_only:
        li = xbmcgui.ListItem(label="(No matches)")
        xbmcplugin.addDirectoryItem(handle, _url(action="search"), li, isFolder=False)
        xbmcplugin.endOfDirectory(handle)
        return

    for m in local:
        ratings = m.get("ratings")
        watched = bool(m.get("watched"))
        # rd_available isn't returned by /search; default to False — the
        # detail page will resolve on demand anyway.
        _add_movie(handle, m, ratings, watched, False)

    if tmdb_only:
        sep = xbmcgui.ListItem(label="[B]── More on TMDB ──[/B]")
        xbmcplugin.addDirectoryItem(handle, _url(action="search"), sep, isFolder=False)
        for m in tmdb_only:
            li = _movie_listitem(m, rating=None, watched=False, rd_available=False)
            # Tag TMDB-only items so they're visually distinct from local ones.
            li.setLabel("[COLOR cyan][+TMDB][/COLOR] " + li.getLabel())
            url = _url(action="import_movie", movie_id=m["id"])
            xbmcplugin.addDirectoryItem(handle, url, li, isFolder=True)

    xbmcplugin.endOfDirectory(handle)


def import_movie(handle, movie_id):
    """Import a TMDB-only result into the local DB, then jump to its detail
    page. Used by search_results' TMDB-only rows."""
    progress = xbmcgui.DialogProgressBG()
    progress.create("movieRec", "Importing from TMDB…")
    try:
        try:
            api.post("/movies/import/%d" % movie_id, _timeout=60)
        except api.APIError as e:
            api.handle_error(e)
            xbmcplugin.endOfDirectory(handle, succeeded=False)
            return
    finally:
        progress.close()
    # Hand off to the standard detail flow (which kicks off RD resolve).
    movie_detail(handle, movie_id)


def _quality_rank(q):
    return {"4K": 1, "1080p": 2, "720p": 3}.get(q, 4)


def movie_detail(handle, movie_id, update_listing=False, auto_resolve=True):
    # Always resolve on entry — RD's cached release list rotates and stream
    # URLs expire, so a fresh resolve guarantees the picker shows what's
    # currently playable. resolve_links re-enters movie_detail with
    # auto_resolve=False so a genuinely empty resolve doesn't loop.
    if auto_resolve:
        resolve_links(handle, movie_id, update_listing=update_listing)
        return

    data = api.get("/movies/%d" % movie_id)
    movie = data.get("movie") or {}
    rating = data.get("rating")
    filmarks = data.get("filmarks")
    links = data.get("debrid_links") or []

    # Build a card-style ratings dict so each link row in the picker carries
    # the same rating data the list views attach (Filmarks is stored 0-5 in
    # the API; _attach_ratings takes care of the 0-10 display).
    card_rating = {}
    if rating:
        card_rating.update({
            "imdb_rating": rating.get("imdb_rating") or 0,
            "imdb_vote_count": rating.get("imdb_vote_count") or 0,
            "rt_score": rating.get("rt_score") or "",
            "metacritic": rating.get("metacritic") or 0,
        })
    if filmarks and filmarks.get("rating"):
        card_rating["filmarks_rating"] = filmarks.get("rating")

    # Last-played link (so the picker can flag where the user left off).
    last_link_id = 0
    try:
        pb = api.get("/playback-state/%d" % movie_id) or {}
        last_link_id = int(pb.get("last_link_id") or 0)
    except api.APIError:
        pass

    xbmcplugin.setPluginCategory(handle, movie.get("title") or "Movie")
    xbmcplugin.setContent(handle, "videos")

    if not links:
        li = xbmcgui.ListItem(label="[B]» Retry Real-Debrid resolve[/B]")
        li.setArt({"icon": "DefaultAddonsSearch.png"})
        li.setProperty("SpecialSort", "top")
        url = _url(action="resolve_links", movie_id=movie_id)
        xbmcplugin.addDirectoryItem(handle, url, li, isFolder=True)
    else:
        links_sorted = sorted(links, key=lambda l: (_quality_rank(l.get("quality", "")),
                                                    -int(l.get("seeders") or 0)))
        for link in links_sorted:
            qual = link.get("quality") or "?"
            size_gb = (link.get("file_size") or 0) / (1024 ** 3)
            label = "[%s] %s  (%.1f GB, %d seeders)" % (
                qual, link.get("filename") or link.get("torrent_title") or "",
                size_gb, link.get("seeders") or 0)
            if last_link_id and int(link.get("id") or 0) == last_link_id:
                label = "[COLOR yellow]▶ Last played[/COLOR]  " + label
            li = xbmcgui.ListItem(label=label)
            li.setArt({"poster": _poster_url(movie.get("poster_path"))})
            info = {
                "title": movie.get("title") or "",
                "year": movie.get("year") or 0,
                "plot": movie.get("overview") or "",
                "mediatype": "movie",
            }
            if movie.get("imdb_id"):
                info["imdbnumber"] = movie["imdb_id"]
            li.setInfo("video", info)
            _attach_ratings(li, movie, card_rating)
            li.setProperty("IsPlayable", "true")
            url = _url(action="play", link_id=link["id"], movie_id=movie_id)
            xbmcplugin.addDirectoryItem(handle, url, li, isFolder=False)

    xbmcplugin.endOfDirectory(handle, updateListing=update_listing, cacheToDisc=False)


def resolve_links(handle, movie_id, update_listing=True):
    """Trigger Real-Debrid resolve, wait for links to come back, then render
    movie_detail (now populated with resolved links) into the current
    container so the user can pick which release to play. auto_resolve is
    forced off in the re-render so a failed resolve doesn't loop."""
    import time
    progress = xbmcgui.DialogProgressBG()
    progress.create("movieRec", "Resolving via Real-Debrid…")
    found = False
    try:
        try:
            # Resolve scrapes Torrentio + resolves up to 5 magnets through RD
            # synchronously — easily 30-60s on a cold movie. Use a generous
            # client-side timeout; the user already sees a progress bar.
            api.post("/realdebrid/resolve/%d" % movie_id, _timeout=120)
        except api.APIError as e:
            api.handle_error(e)
            progress.close()
            movie_detail(handle, movie_id, update_listing=update_listing, auto_resolve=False)
            return

        # Poll up to 60s — the server's background pass keeps adding releases
        # to the DB after the synchronous first batch returns.
        for i in range(30):
            progress.update(int(100 * (i + 1) / 30))
            status = api.get("/realdebrid/resolve-status/%d" % movie_id)
            if status.get("links"):
                found = True
                break
            time.sleep(2)
    finally:
        progress.close()

    if not found:
        api.notify("No cached releases found", icon=xbmcgui.NOTIFICATION_WARNING)
    movie_detail(handle, movie_id, update_listing=update_listing, auto_resolve=False)
