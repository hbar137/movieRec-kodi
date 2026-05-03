"""Directory views: root menu, dashboard, watchlist, history, browse, search, movie detail."""
import sys
import urllib.parse

import xbmcaddon
import xbmcgui
import xbmcplugin

from . import api

ADDON = xbmcaddon.Addon()


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
        "plot": movie.get("overview") or "",
        "mediatype": "movie",
    }
    if movie.get("imdb_id"):
        info["imdbnumber"] = movie["imdb_id"]
    if rating:
        if rating.get("imdb_rating"):
            info["rating"] = float(rating["imdb_rating"])
        if rating.get("imdb_vote_count"):
            info["votes"] = str(rating["imdb_vote_count"])
    li.setInfo("video", info)
    return li


def root(handle):
    xbmcplugin.setPluginCategory(handle, "movieRec")
    xbmcplugin.setContent(handle, "files")
    items = [
        ("Dashboard", _url(action="dashboard")),
        ("Watchlist", _url(action="watchlist")),
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


def _row_value(field, state, sort_options):
    if field == "sort":
        s = state.get("sort")
        return dict(sort_options).get(s, "default") if s else "default"
    if field == "genre":
        return state.get("genre") or "any"
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
               ("sort", "genre", "language", "year_min", "year_max", "rating_min", "rd_available"))


def set_filter(handle, target_action, field, current):
    """Apply one filter change, then render the target listing directly into
    the same handle with updateListing=True. This replaces the contents of
    the current container in-place, which is the only Kodi pattern that
    reliably refreshes a list view from inside an action handler.
    Container.Update + endOfDirectory(succeeded=False) chains are racey on
    some Kodi builds and can silently drop the navigation."""
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
        try:
            genres = api.get("/genres") or []
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

    # Render the target listing directly into THIS handle, marking it as a
    # listing update so Kodi swaps the items in place without changing the
    # navigation history.
    if target_action == "watchlist":
        watchlist(handle, page=0, params=state, update_listing=True)
    else:
        browse(handle, page=0, params=state, update_listing=True)


_FILTER_FIELDS = [
    ("sort",   "Sort"),
    ("genre",  "Genre"),
    ("year",   "Year"),
    ("rating", "Min IMDB"),
    ("rd",     "Real-Debrid"),
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
        value = _row_value(field, current, sort_options)
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


_FILTER_KEYS = ("sort", "genre", "language", "year_min", "year_max", "rating_min", "rd_available")


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
    kb = xbmcgui.Dialog().input("Search movieRec", type=xbmcgui.INPUT_ALPHANUM)
    if not kb:
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return
    search_results(handle, kb)


def search_results(handle, query):
    data = api.get("/movies/search", q=query, limit=50)
    xbmcplugin.setPluginCategory(handle, "Search: %s" % query)
    xbmcplugin.setContent(handle, "movies")
    for m in data.get("movies") or []:
        _add_movie(handle, m, None, False, False)
    xbmcplugin.endOfDirectory(handle)


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
    links = data.get("debrid_links") or []

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
            if rating and rating.get("imdb_rating"):
                info["rating"] = float(rating["imdb_rating"])
            li.setInfo("video", info)
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
