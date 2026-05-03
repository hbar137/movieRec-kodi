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
        label = "[COLOR green]✓[/COLOR] " + label
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


def dashboard(handle):
    data = api.get("/dashboard")
    xbmcplugin.setPluginCategory(handle, "Dashboard")
    xbmcplugin.setContent(handle, "movies")

    ratings = data.get("ratings") or {}
    watched_map = data.get("watched") or {}
    rd_map = data.get("rd_available") or {}

    seen = set()

    def add_section(label):
        sep = xbmcgui.ListItem(label="── %s ──" % label)
        xbmcplugin.addDirectoryItem(handle, _url(action="root"), sep, isFolder=False)

    # Recently watched: entries reference embedded movie
    recent = data.get("recently_watched") or []
    if recent:
        add_section("Recently Watched")
        for e in recent:
            m = e.get("movie") or {"id": e["movie_id"]}
            m["id"] = e["movie_id"]
            if m["id"] in seen:
                continue
            seen.add(m["id"])
            r = ratings.get(str(m["id"])) or ratings.get(m["id"])
            _add_movie(handle, m, r, True, bool(rd_map.get(str(m["id"])) or rd_map.get(m["id"])))

    top = data.get("top_unwatched") or []
    if top:
        add_section("Top Unwatched")
        for m in top:
            if m["id"] in seen:
                continue
            seen.add(m["id"])
            r = ratings.get(str(m["id"])) or ratings.get(m["id"])
            _add_movie(handle, m, r, False, bool(rd_map.get(str(m["id"])) or rd_map.get(m["id"])))

    wl = data.get("watchlist") or []
    if wl:
        add_section("Watchlist")
        for w in wl:
            m = w.get("movie") or {}
            m["id"] = w["movie_id"]
            if m["id"] in seen:
                continue
            seen.add(m["id"])
            r = ratings.get(str(m["id"])) or ratings.get(m["id"])
            _add_movie(handle, m, r, bool(watched_map.get(str(m["id"]))),
                       bool(rd_map.get(str(m["id"])) or rd_map.get(m["id"])))

    xbmcplugin.endOfDirectory(handle)


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


def watchlist(handle, page=0):
    limit = _page_size()
    data = api.get("/watchlist", page=page, limit=limit)
    xbmcplugin.setPluginCategory(handle, "Watchlist")

    def get_movie(item):
        m = item.get("movie") or {}
        m["id"] = item["movie_id"]
        return m

    _paged_list(handle, data, "items", get_movie, page, {"action": "watchlist"})


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


def browse(handle, page=0, genre=None, language=None):
    limit = _page_size()
    data = api.get("/browse", page=page, limit=limit, genre=genre, language=language)
    xbmcplugin.setPluginCategory(handle, genre or "Browse")
    _paged_list(handle, data, "movies", lambda m: m, page,
                {"action": "browse", "genre": genre, "language": language})


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
        # Trigger resolve and offer placeholder
        li = xbmcgui.ListItem(label="[B]Resolve via Real-Debrid[/B]")
        url = _url(action="resolve_and_play", movie_id=movie_id)
        xbmcplugin.addDirectoryItem(handle, url, li, isFolder=False)
    else:
        # Sort by quality + seeders
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
