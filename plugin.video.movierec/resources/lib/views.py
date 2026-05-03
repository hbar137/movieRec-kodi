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


def _filter_summary(params, sort_options):
    bits = []
    sort = params.get("sort")
    if sort:
        label = dict(sort_options).get(sort, sort)
        bits.append("sort=%s" % label)
    for key in ("genre", "language"):
        v = params.get(key)
        if v:
            bits.append("%s=%s" % (key, v))
    if params.get("year_min") or params.get("year_max"):
        bits.append("year=%s-%s" % (params.get("year_min") or "", params.get("year_max") or ""))
    if params.get("rating_min"):
        bits.append("rating≥%s" % params["rating_min"])
    if params.get("rd_available") == "true":
        bits.append("RD only")
    return ", ".join(bits) if bits else "none"


def _prompt_filters(action, sort_options, current):
    """Pop a chained dialog and return a new params dict (or None if cancelled)."""
    dlg = xbmcgui.Dialog()

    # Sort
    sort_labels = ["(keep)"] + [lbl for _, lbl in sort_options]
    idx = dlg.select("Sort by", sort_labels)
    if idx is None or idx < 0:
        return None
    new_params = dict(current)
    if idx > 0:
        new_params["sort"] = sort_options[idx - 1][0]

    # Genre
    try:
        genres = api.get("/genres") or []
    except api.APIError:
        genres = []
    genre_labels = ["(any)", "(keep current)"] + list(genres)
    gidx = dlg.select("Genre", genre_labels)
    if gidx == 0:
        new_params.pop("genre", None)
    elif gidx >= 2:
        new_params["genre"] = genres[gidx - 2]

    # Year range
    if dlg.yesno("Filters", "Set a year range?", nolabel="Skip", yeslabel="Yes"):
        ymin = dlg.input("Year from (blank = any)", type=xbmcgui.INPUT_NUMERIC)
        ymax = dlg.input("Year to (blank = any)", type=xbmcgui.INPUT_NUMERIC)
        if ymin:
            new_params["year_min"] = ymin
        else:
            new_params.pop("year_min", None)
        if ymax:
            new_params["year_max"] = ymax
        else:
            new_params.pop("year_max", None)

    # Min rating
    if dlg.yesno("Filters", "Set a minimum IMDB rating?", nolabel="Skip", yeslabel="Yes"):
        rmin = dlg.input("Min rating (0-10, blank = any)", type=xbmcgui.INPUT_NUMERIC)
        if rmin:
            new_params["rating_min"] = rmin
        else:
            new_params.pop("rating_min", None)

    # RD only
    rd_idx = dlg.select("Real-Debrid", ["Any", "Only available", "Keep current"])
    if rd_idx == 0:
        new_params.pop("rd_available", None)
    elif rd_idx == 1:
        new_params["rd_available"] = "true"

    # page resets on filter change
    new_params.pop("page", None)
    new_params["action"] = action
    return new_params


def _add_filter_entries(handle, action, current, sort_options):
    summary = _filter_summary(current, sort_options)
    li = xbmcgui.ListItem(label="[B][Filter…][/B]  [COLOR gray](%s)[/COLOR]" % summary)
    li.setArt({"icon": "DefaultIconInfo.png"})
    edit_url = _url(action="edit_filters", target=action, **{k: v for k, v in current.items() if k != "action"})
    xbmcplugin.addDirectoryItem(handle, edit_url, li, isFolder=True)

    if any(k in current for k in ("genre", "language", "year_min", "year_max", "rating_min", "rd_available", "sort")):
        clear_li = xbmcgui.ListItem(label="[Clear filters]")
        xbmcplugin.addDirectoryItem(handle, _url(action=action), clear_li, isFolder=True)


def edit_filters(handle, target_action, current):
    sort_options = _WATCHLIST_SORTS if target_action == "watchlist" else _BROWSE_SORTS
    new_params = _prompt_filters(target_action, sort_options, current)
    if not new_params:
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return
    # Redirect: end this dir then push the new URL via Container.Update
    import xbmc
    xbmcplugin.endOfDirectory(handle, succeeded=False)
    xbmc.executebuiltin("Container.Update(%s,replace)" % _url(**new_params))


# ---------------------------------------------------------------------------
# Paged listings
# ---------------------------------------------------------------------------


def _paged_list(handle, response, items_key, get_movie, page, action_kwargs):
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

    xbmcplugin.endOfDirectory(handle)


_FILTER_KEYS = ("sort", "genre", "language", "year_min", "year_max", "rating_min", "rd_available")


def _filter_kwargs(params):
    return {k: params[k] for k in _FILTER_KEYS if params.get(k)}


def watchlist(handle, page, params):
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
    _paged_list(handle, data, "items", get_movie, page, action_kwargs)


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


def browse(handle, page, params):
    limit = _page_size()
    api_kwargs = dict(_filter_kwargs(params))
    api_kwargs.update({"page": page, "limit": limit})
    data = api.get("/browse", **api_kwargs)
    xbmcplugin.setPluginCategory(handle, params.get("genre") or "Browse")

    current = dict(_filter_kwargs(params))
    _add_filter_entries(handle, "browse", current, _BROWSE_SORTS)

    action_kwargs = {"action": "browse"}
    action_kwargs.update(current)
    _paged_list(handle, data, "movies", lambda m: m, page, action_kwargs)


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


def movie_detail(handle, movie_id):
    data = api.get("/movies/%d" % movie_id)
    movie = data.get("movie") or {}
    rating = data.get("rating")
    links = data.get("debrid_links") or []

    xbmcplugin.setPluginCategory(handle, movie.get("title") or "Movie")
    xbmcplugin.setContent(handle, "videos")

    if not links:
        li = xbmcgui.ListItem(label="[B]Resolve via Real-Debrid[/B]")
        li.setProperty("IsPlayable", "true")
        url = _url(action="resolve_and_play", movie_id=movie_id)
        xbmcplugin.addDirectoryItem(handle, url, li, isFolder=False)
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

    xbmcplugin.endOfDirectory(handle)
