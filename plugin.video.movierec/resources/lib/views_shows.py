"""Show / season / episode directory views.

Mirrors the movie views in shape: shows_browse → show_detail (lists seasons) →
season_detail (lists episodes). Picking an episode plays via the resolved RD
links if any exist, otherwise auto-resolves first.
"""
import sys
import urllib.parse

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

from . import api, views

ADDON = xbmcaddon.Addon()


def _url(**kwargs):
    base = sys.argv[0]
    return base + "?" + urllib.parse.urlencode(
        {k: v for k, v in kwargs.items() if v is not None})


def _poster_url(p):
    if not p:
        return ""
    if p.startswith("http"):
        return p
    return "https://image.tmdb.org/t/p/w500" + p


def _still_url(p):
    if not p:
        return ""
    if p.startswith("http"):
        return p
    return "https://image.tmdb.org/t/p/w300" + p


def _show_listitem(show, ratings=None, watched=False, on_watchlist=False, progress=None):
    title = show.get("title", "")
    year = show.get("year") or 0
    label = "%s (%d)" % (title, year) if year else title
    if on_watchlist:
        label = "[COLOR cyan][WL][/COLOR] " + label
    if watched:
        label = "[COLOR gray][STARTED][/COLOR] " + label
    if progress and progress.get("total"):
        w = int(progress.get("watched") or 0)
        t = int(progress.get("total") or 0)
        if w >= t:
            label = "[COLOR green][✓][/COLOR] " + label
        else:
            label = "%s  [COLOR gray]%d/%d[/COLOR]" % (label, w, t)

    li = xbmcgui.ListItem(label=label)
    poster = _poster_url(show.get("poster_path"))
    li.setArt({"poster": poster, "thumb": poster, "fanart": poster})

    info = {
        "title": title,
        "year": year,
        "plot": views._plot_with_ratings(show, ratings),
        "mediatype": "tvshow",
    }
    if show.get("imdb_id"):
        info["imdbnumber"] = show["imdb_id"]
    li.setInfo("video", info)
    views._attach_ratings(li, show, ratings or {})
    return li


_SHOW_BROWSE_KEYS = ("sort", "genre", "language", "country",
                     "year_min", "year_max", "rating_min", "watched")


def _show_browse_kwargs(params):
    return {k: params[k] for k in _SHOW_BROWSE_KEYS if params.get(k)}


def shows_browse(handle, page, params, update_listing=False):
    """Mirror of views.browse but for shows."""
    limit = views._page_size()
    api_kwargs = dict(_show_browse_kwargs(params))
    api_kwargs.update({"page": page, "limit": limit})

    data = api.get("/shows", **api_kwargs)
    xbmcplugin.setPluginCategory(handle, params.get("genre") or "Shows")
    xbmcplugin.setContent(handle, "tvshows")

    current = dict(_show_browse_kwargs(params))
    views._add_filter_entries(handle, "shows_browse", current, views._BROWSE_SORTS)

    items = data.get("shows") or []
    total = data.get("total") or 0
    ratings = data.get("ratings") or {}
    watched_map = data.get("watched") or {}
    progress_map = data.get("progress") or {}
    wl_map = data.get("watchlist") or {}

    for s in items:
        sid = s["id"]
        r = ratings.get(str(sid)) or ratings.get(sid)
        w = bool(watched_map.get(str(sid)) or watched_map.get(sid))
        wl = bool(wl_map.get(str(sid)) or wl_map.get(sid))
        prog = progress_map.get(str(sid)) or progress_map.get(sid)
        li = _show_listitem(s, ratings=r, watched=w, on_watchlist=wl, progress=prog)
        url = _url(action="show", show_id=sid)
        xbmcplugin.addDirectoryItem(handle, url, li, isFolder=True)

    if (page + 1) * limit < total:
        kwargs = dict(action="shows_browse", page=page + 1)
        kwargs.update(current)
        next_li = xbmcgui.ListItem(label="Next page →")
        xbmcplugin.addDirectoryItem(handle, _url(**kwargs), next_li, isFolder=True)

    xbmcplugin.endOfDirectory(handle, updateListing=update_listing, cacheToDisc=False)


_SHOW_WATCHLIST_KEYS = ("sort", "genre", "language", "country", "tag",
                        "year_min", "year_max", "rating_min", "status")


def _show_watchlist_kwargs(params):
    return {k: params[k] for k in _SHOW_WATCHLIST_KEYS if params.get(k)}


def show_watchlist_view(handle, page, params, update_listing=False):
    """Show watchlist (mirror of /watchlist for movies)."""
    limit = views._page_size()
    api_kwargs = dict(_show_watchlist_kwargs(params))
    api_kwargs.update({"page": page, "limit": limit})

    data = api.get("/show-watchlist", **api_kwargs)
    xbmcplugin.setPluginCategory(handle, "Show Watchlist")
    xbmcplugin.setContent(handle, "tvshows")

    current = dict(_show_watchlist_kwargs(params))
    views._add_filter_entries(handle, "show_watchlist", current, views._WATCHLIST_SORTS)

    items = data.get("items") or []
    total = data.get("total") or 0
    ratings = data.get("ratings") or {}
    watched_map = data.get("watched") or {}
    progress_map = data.get("progress") or {}

    for it in items:
        s = it.get("show") or {}
        sid = it["show_id"]
        s["id"] = sid
        r = ratings.get(str(sid)) or ratings.get(sid)
        w = bool(watched_map.get(str(sid)) or watched_map.get(sid))
        prog = progress_map.get(str(sid)) or progress_map.get(sid)
        li = _show_listitem(s, ratings=r, watched=w, on_watchlist=True, progress=prog)
        url = _url(action="show", show_id=sid)
        xbmcplugin.addDirectoryItem(handle, url, li, isFolder=True)

    if (page + 1) * limit < total:
        kwargs = dict(action="show_watchlist", page=page + 1)
        kwargs.update(current)
        next_li = xbmcgui.ListItem(label="Next page →")
        xbmcplugin.addDirectoryItem(handle, _url(**kwargs), next_li, isFolder=True)

    xbmcplugin.endOfDirectory(handle, updateListing=update_listing, cacheToDisc=False)


def show_detail(handle, show_id):
    """Show overview → list of seasons. Specials (season 0) are skipped."""
    data = api.get("/shows/%d" % show_id)
    show = data.get("show") or {}
    seasons = data.get("seasons") or []
    watch_state = data.get("watch_state") or {}

    xbmcplugin.setPluginCategory(handle, show.get("title") or "Show")
    xbmcplugin.setContent(handle, "seasons")

    poster = _poster_url(show.get("poster_path"))
    fanart = _poster_url(show.get("backdrop_path") or show.get("poster_path"))

    # Header line: progress + next-up summary, prepended to the plot.
    header_lines = []
    if watch_state.get("total_episodes"):
        w = int(watch_state.get("episodes_watched") or 0)
        t = int(watch_state.get("total_episodes") or 0)
        header_lines.append("[B]%d / %d episodes watched[/B]" % (w, t))
    nx = watch_state.get("next_episode")
    if nx:
        header_lines.append("[COLOR yellow]Up next:[/COLOR] S%dE%d %s" %
                            (nx.get("season_number") or 0,
                             nx.get("episode_number") or 0,
                             nx.get("name") or ""))
    if show.get("status"):
        header_lines.append("[COLOR gray]%s[/COLOR]" % show["status"])
    header = "\n".join(header_lines)
    plot = show.get("overview") or ""
    full_plot = (header + "\n\n" + plot) if header and plot else (header or plot)

    for s in seasons:
        if (s.get("season_number") or 0) <= 0:
            continue
        season_num = s.get("season_number")
        ep_count = s.get("episode_count") or 0
        label = s.get("name") or ("Season %d" % season_num)
        label = "%s  [COLOR gray](%d ep)[/COLOR]" % (label, ep_count)
        li = xbmcgui.ListItem(label=label)
        sp = _poster_url(s.get("poster_path") or show.get("poster_path"))
        li.setArt({"poster": sp, "thumb": sp, "fanart": fanart})
        info = {
            "tvshowtitle": show.get("title") or "",
            "title": s.get("name") or "Season %d" % season_num,
            "season": season_num,
            "plot": s.get("overview") or full_plot,
            "mediatype": "season",
        }
        if show.get("imdb_id"):
            info["imdbnumber"] = show["imdb_id"]
        li.setInfo("video", info)
        url = _url(action="season", show_id=show_id, season=season_num)
        xbmcplugin.addDirectoryItem(handle, url, li, isFolder=True)

    xbmcplugin.endOfDirectory(handle)


def _quality_rank(q):
    return {"4K": 1, "1080p": 2, "720p": 3}.get(q, 4)


def season_detail(handle, show_id, season):
    """List episodes for one season. Each episode is a single playable item; if
    no resolved RD link exists yet we'll auto-resolve when the user clicks."""
    data = api.get("/shows/%d/seasons/%d" % (show_id, season))
    season_obj = data.get("season") or {}
    episodes = data.get("episodes") or []
    watched_map = data.get("watched") or {}
    links_map = data.get("links") or {}

    # Show-level data we want to keep with each episode for InfoLabels.
    try:
        show = api.get("/shows/%d" % show_id).get("show") or {}
    except api.APIError:
        show = {}

    xbmcplugin.setPluginCategory(handle,
                                 (show.get("title") or "") + " — " + (season_obj.get("name") or "Season %d" % season))
    xbmcplugin.setContent(handle, "episodes")

    poster = _poster_url(season_obj.get("poster_path") or show.get("poster_path"))
    fanart = _poster_url(show.get("backdrop_path") or show.get("poster_path"))

    pref = ADDON.getSettingString("quality_pref") or "auto"

    for ep in episodes:
        eid = ep["id"]
        watched = bool(watched_map.get(str(eid)) or watched_map.get(eid))
        ep_links = links_map.get(str(eid)) or links_map.get(eid) or []

        title = ep.get("name") or ""
        prefix = "S%02dE%02d" % (ep.get("season_number") or 0, ep.get("episode_number") or 0)
        label = "%s  %s" % (prefix, title) if title else prefix
        if watched:
            label = "[COLOR gray][✓][/COLOR] " + label
        if ep_links:
            label = "[COLOR green][RD %d][/COLOR] %s" % (len(ep_links), label)

        li = xbmcgui.ListItem(label=label)
        still = _still_url(ep.get("still_path") or season_obj.get("poster_path") or show.get("poster_path"))
        li.setArt({"thumb": still, "poster": poster, "fanart": fanart})
        info = {
            "tvshowtitle": show.get("title") or "",
            "title": title,
            "season": ep.get("season_number") or 0,
            "episode": ep.get("episode_number") or 0,
            "aired": ep.get("air_date") or "",
            "plot": ep.get("overview") or "",
            "duration": int(ep.get("runtime") or 0) * 60,
            "mediatype": "episode",
        }
        if ep.get("imdb_id"):
            info["imdbnumber"] = ep["imdb_id"]
        elif show.get("imdb_id"):
            info["imdbnumber"] = show["imdb_id"]
        if ep.get("tmdb_vote_average"):
            try:
                li.setRating("tmdb", float(ep["tmdb_vote_average"]),
                             int(ep.get("tmdb_vote_count") or 0), True)
            except (TypeError, ValueError):
                pass
        li.setInfo("video", info)

        if ep_links:
            # Pick best link by user preference and play it directly. The detail
            # page is already a 10-foot UI; making the user pick again is noise.
            link = _pick_link(ep_links, pref)
            li.setProperty("IsPlayable", "true")
            url = _url(action="play_episode", link_id=link["id"], episode_id=eid, show_id=show_id)
            xbmcplugin.addDirectoryItem(handle, url, li, isFolder=False)
        else:
            # No resolved links yet — resolve, then play.
            url = _url(action="resolve_episode", episode_id=eid, show_id=show_id, season=season)
            xbmcplugin.addDirectoryItem(handle, url, li, isFolder=True)

    xbmcplugin.endOfDirectory(handle)


def _pick_link(links, pref):
    if not links:
        return None
    if pref and pref != "auto":
        for l in links:
            if l.get("quality") == pref:
                return l
    return sorted(links, key=lambda l: (_quality_rank(l.get("quality", "")),
                                        -int(l.get("seeders") or 0)))[0]


def episode_detail(handle, episode_id, show_id, season):
    """Picker: list every resolved link for the episode so the user can choose
    a different release than the auto-pick. Reachable from the season view via
    a context menu (TODO) or from a 'Pick a release' fallback path."""
    data = api.get("/shows/%d/seasons/%d" % (show_id, season))
    episodes = {ep["id"]: ep for ep in (data.get("episodes") or [])}
    links_map = data.get("links") or {}
    ep = episodes.get(episode_id) or {}
    links = links_map.get(str(episode_id)) or links_map.get(episode_id) or []

    xbmcplugin.setPluginCategory(handle, "S%02dE%02d %s" %
                                 (ep.get("season_number") or 0,
                                  ep.get("episode_number") or 0,
                                  ep.get("name") or ""))
    xbmcplugin.setContent(handle, "videos")

    if not links:
        li = xbmcgui.ListItem(label="[B]» Resolve via Real-Debrid[/B]")
        li.setProperty("SpecialSort", "top")
        url = _url(action="resolve_episode", episode_id=episode_id, show_id=show_id, season=season)
        xbmcplugin.addDirectoryItem(handle, url, li, isFolder=True)
        xbmcplugin.endOfDirectory(handle)
        return

    sorted_links = sorted(links, key=lambda l: (_quality_rank(l.get("quality", "")),
                                                -int(l.get("seeders") or 0)))
    for link in sorted_links:
        qual = link.get("quality") or "?"
        size_gb = (link.get("file_size") or 0) / (1024 ** 3)
        is_pack = "  [COLOR cyan][PACK][/COLOR]" if link.get("is_pack") else ""
        label = "[%s]%s %s  (%.1f GB, %d seeders)" % (
            qual, is_pack, link.get("filename") or link.get("torrent_title") or "",
            size_gb, link.get("seeders") or 0)
        li = xbmcgui.ListItem(label=label)
        li.setInfo("video", {
            "title": ep.get("name") or "",
            "season": ep.get("season_number") or 0,
            "episode": ep.get("episode_number") or 0,
            "mediatype": "episode",
        })
        li.setProperty("IsPlayable", "true")
        url = _url(action="play_episode", link_id=link["id"], episode_id=episode_id, show_id=show_id)
        xbmcplugin.addDirectoryItem(handle, url, li, isFolder=False)

    xbmcplugin.endOfDirectory(handle)


def resolve_episode(handle, episode_id, show_id, season):
    """Trigger RD resolve for one episode, poll until at least one link
    appears, then re-render the season view (now populated)."""
    import time
    progress = xbmcgui.DialogProgressBG()
    progress.create("movieRec", "Resolving via Real-Debrid…")
    found = False
    try:
        try:
            api.post("/realdebrid/resolve-episode/%d" % episode_id, _timeout=120)
        except api.APIError as e:
            api.handle_error(e)
            progress.close()
            season_detail(handle, show_id, season)
            return

        for i in range(30):
            progress.update(int(100 * (i + 1) / 30))
            status = api.get("/realdebrid/resolve-episode-status/%d" % episode_id)
            if status.get("links"):
                found = True
                break
            time.sleep(2)
    finally:
        progress.close()

    if not found:
        api.notify("No cached releases found", icon=xbmcgui.NOTIFICATION_WARNING)

    # Re-render the season into the current container so the user sees the
    # new RD links inline. Container.Update with `replace` so back doesn't
    # re-trigger this resolver.
    target = _url(action="season", show_id=show_id, season=season)
    xbmc.executebuiltin("Container.Update(%s,replace)" % target)
    xbmcplugin.endOfDirectory(handle, succeeded=False)


# ---------------------------------------------------------------------------
# Search (shows)
# ---------------------------------------------------------------------------


def search_shows(handle):
    """Show search root: 'New search…' + past show searches."""
    xbmcplugin.setPluginCategory(handle, "Show Search")
    xbmcplugin.setContent(handle, "files")

    new_li = xbmcgui.ListItem(label="[B]» New search…[/B]")
    new_li.setArt({"icon": "DefaultAddonsSearch.png"})
    new_li.setProperty("SpecialSort", "top")
    xbmcplugin.addDirectoryItem(handle, _url(action="search_shows_new"), new_li, isFolder=True)

    history = views._load_search_history("shows")
    if history:
        sep = xbmcgui.ListItem(label="[B]── Past searches ──[/B]")
        sep.setProperty("SpecialSort", "top")
        xbmcplugin.addDirectoryItem(handle, _url(action="search_shows"), sep, isFolder=False)

        for q in history:
            li = xbmcgui.ListItem(label=q)
            li.setArt({"icon": "DefaultAddonsSearch.png"})
            xbmcplugin.addDirectoryItem(handle,
                                        _url(action="search_shows_results", q=q),
                                        li, isFolder=True)

        clear_li = xbmcgui.ListItem(label="[COLOR red]» Clear search history[/COLOR]")
        clear_li.setArt({"icon": "DefaultAddonsSearch.png"})
        xbmcplugin.addDirectoryItem(handle, _url(action="search_shows_clear"), clear_li, isFolder=True)

    xbmcplugin.endOfDirectory(handle)


def search_shows_new(handle):
    kb = xbmcgui.Dialog().input("Search shows", type=xbmcgui.INPUT_ALPHANUM)
    if not kb:
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return
    views._record_search("shows", kb)
    search_shows_results(handle, kb)


def search_shows_clear(handle):
    if xbmcgui.Dialog().yesno("Search history",
                              "Clear all saved show searches?",
                              nolabel="Cancel", yeslabel="Clear"):
        views._clear_search_history("shows")
    xbmc.executebuiltin("Container.Update(%s,replace)" % _url(action="search_shows"))
    xbmcplugin.endOfDirectory(handle, succeeded=False)


def search_shows_results(handle, query):
    """Show-only search results. Local hits render first; TMDB-only hits sit
    below a separator and trigger import-then-open via `import_show`."""
    if not query:
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return
    views._record_search("shows", query)

    try:
        data = api.get("/search", q=query) or {}
    except api.APIError as e:
        api.handle_error(e)
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return

    local = data.get("local_shows") or []
    tmdb_only = data.get("tmdb_shows") or []

    xbmcplugin.setPluginCategory(handle, "Show Search: %s" % query)
    xbmcplugin.setContent(handle, "tvshows")

    if not local and not tmdb_only:
        li = xbmcgui.ListItem(label="(No matches)")
        xbmcplugin.addDirectoryItem(handle, _url(action="search_shows"), li, isFolder=False)
        xbmcplugin.endOfDirectory(handle)
        return

    for s in local:
        ratings = s.get("ratings")
        watched = bool(s.get("watched"))
        on_wl = bool(s.get("on_watchlist"))
        li = _show_listitem(s, ratings=ratings, watched=watched, on_watchlist=on_wl)
        url = _url(action="show", show_id=s["id"])
        xbmcplugin.addDirectoryItem(handle, url, li, isFolder=True)

    if tmdb_only:
        sep = xbmcgui.ListItem(label="[B]── More on TMDB ──[/B]")
        xbmcplugin.addDirectoryItem(handle, _url(action="search_shows"), sep, isFolder=False)
        for s in tmdb_only:
            li = _show_listitem(s)
            li.setLabel("[COLOR cyan][+TMDB][/COLOR] " + li.getLabel())
            url = _url(action="import_show", show_id=s["id"])
            xbmcplugin.addDirectoryItem(handle, url, li, isFolder=True)

    xbmcplugin.endOfDirectory(handle)


def import_show(handle, show_id):
    """Import a TMDB-only show into the local DB, then jump to its detail
    page. Used by search_shows_results' TMDB-only rows."""
    progress = xbmcgui.DialogProgressBG()
    progress.create("movieRec", "Importing from TMDB…")
    try:
        try:
            api.post("/shows/import/%d" % show_id, _timeout=120)
        except api.APIError as e:
            api.handle_error(e)
            xbmcplugin.endOfDirectory(handle, succeeded=False)
            return
    finally:
        progress.close()
    show_detail(handle, show_id)


# ---------------------------------------------------------------------------
# Episode history
# ---------------------------------------------------------------------------


def show_history(handle, page=0):
    """Episode-level history (mirror of /history for movies). Each row is one
    episode watch; clicking opens that show's detail page."""
    limit = views._page_size()
    data = api.get("/show-history", page=page, limit=limit)
    xbmcplugin.setPluginCategory(handle, "Show History")
    xbmcplugin.setContent(handle, "episodes")

    entries = data.get("entries") or []
    total = data.get("total") or 0
    ratings = data.get("ratings") or {}

    for e in entries:
        ep = e.get("episode") or {}
        sh = e.get("show") or {}
        sid = e.get("show_id") or sh.get("id")
        s_num = ep.get("season_number") or 0
        e_num = ep.get("episode_number") or 0
        ep_title = ep.get("name") or ""
        watched_at = (e.get("watched_at") or "")[:10]
        prefix = "S%02dE%02d" % (s_num, e_num)
        label = "%s — %s %s" % (sh.get("title") or "?", prefix, ep_title)
        if watched_at:
            label = "[COLOR gray]%s[/COLOR]  %s" % (watched_at, label)

        li = xbmcgui.ListItem(label=label)
        still = _still_url(ep.get("still_path") or sh.get("poster_path"))
        poster = _poster_url(sh.get("poster_path"))
        fanart = _poster_url(sh.get("backdrop_path") or sh.get("poster_path"))
        li.setArt({"thumb": still, "poster": poster, "fanart": fanart})
        info = {
            "tvshowtitle": sh.get("title") or "",
            "title": ep_title,
            "season": s_num,
            "episode": e_num,
            "aired": ep.get("air_date") or "",
            "plot": ep.get("overview") or "",
            "mediatype": "episode",
        }
        if sh.get("imdb_id"):
            info["imdbnumber"] = sh["imdb_id"]
        li.setInfo("video", info)
        # Attach show-level ratings to keep parity with the movie history view.
        r = ratings.get(str(sid)) or ratings.get(sid)
        if r:
            views._attach_ratings(li, sh, r)

        url = _url(action="show", show_id=sid) if sid else _url(action="show_history")
        xbmcplugin.addDirectoryItem(handle, url, li, isFolder=True)

    if (page + 1) * limit < total:
        next_li = xbmcgui.ListItem(label="Next page →")
        xbmcplugin.addDirectoryItem(handle,
                                    _url(action="show_history", page=page + 1),
                                    next_li, isFolder=True)

    xbmcplugin.endOfDirectory(handle)
