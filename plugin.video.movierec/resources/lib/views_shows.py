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


def shows_browse(handle, page, params, update_listing=False):
    """Mirror of views.browse but for shows. Uses the shared filter component
    in views — same fields, same query keys."""
    limit = views._page_size()
    api_kwargs = dict(views._filter_kwargs(params))
    api_kwargs.update({"page": page, "limit": limit})

    data = api.get("/shows", **api_kwargs)
    label = "Anime" if params.get("kind") == "anime" else "Shows"
    xbmcplugin.setPluginCategory(handle, params.get("genre") or label)
    xbmcplugin.setContent(handle, "tvshows")

    current = dict(views._filter_kwargs(params))
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


def show_watchlist_view(handle, page, params, update_listing=False):
    """Show watchlist — same shared filter component as everything else."""
    limit = views._page_size()
    api_kwargs = dict(views._filter_kwargs(params))
    api_kwargs.update({"page": page, "limit": limit})

    data = api.get("/show-watchlist", **api_kwargs)
    cat = "Anime Watchlist" if params.get("kind") == "anime" else "Show Watchlist"
    xbmcplugin.setPluginCategory(handle, cat)
    xbmcplugin.setContent(handle, "tvshows")

    current = dict(views._filter_kwargs(params))
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

        # Default click on the row → instant-play top resolved (or trigger
        # resolve if none yet).  The "Pick a release..." context-menu
        # entry (long-press / "C") fetches the full candidate list (Otaku
        # parity) and lazy-resolves the user's pick. For anime shows
        # specifically this matters: the server only pre-resolves the top
        # 1 candidate to avoid tripping RD's per-account anti-probe — so
        # the context menu is the way to access alternatives.
        ctx_items = [(
            "Pick a release...",
            "RunPlugin(%s)" % _url(action="pick_release", episode_id=eid, show_id=show_id, season=season),
        )]
        # Anime-only: no-RD fallback that hits the embed-resolver sidecar.
        # Only meaningful for anime shows we have a MAL id for.
        if show.get("is_anime") and show.get("mal_id"):
            ctx_items.append((
                "Pick embed source...",
                "RunPlugin(%s)" % _url(action="pick_embed_source", episode_id=eid, show_id=show_id, season=season),
            ))
        li.addContextMenuItems(ctx_items)

        if ep_links:
            link = _pick_link(ep_links, pref)
            li.setProperty("IsPlayable", "true")
            url = _url(action="play_episode", link_id=link["id"], episode_id=eid, show_id=show_id)
            xbmcplugin.addDirectoryItem(handle, url, li, isFolder=False)
        else:
            # No resolved links yet — resolve top, then play.
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
    show_meta = data.get("show") or {}
    is_anime = bool(show_meta.get("is_anime"))

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
        # Anime-only: also offer the embed-sources fallback for shows
        # where RD has nothing cached (e.g. "African Office Worker").
        # Backend hits the anime-resolver sidecar which vendors Otaku.
        if is_anime and show_meta.get("mal_id"):
            li = xbmcgui.ListItem(label="[B]» Pick embed source (no-RD fallback)[/B]")
            url = _url(action="pick_embed_source", episode_id=episode_id, show_id=show_id, season=season)
            xbmcplugin.addDirectoryItem(handle, url, li, isFolder=False)
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


def play_next_episode(handle, episode_id, show_id, season):
    """Auto-play entry point fired by the next-episode watcher.

    Reaches the same destination as picking the episode from the season
    view: resolves via RD if no links exist yet, then plays the best link
    by quality_pref."""
    import time
    from . import play

    pref = ADDON.getSettingString("quality_pref") or "auto"

    data = api.get("/shows/%d/seasons/%d" % (show_id, season))
    links_map = data.get("links") or {}
    ep_links = links_map.get(str(episode_id)) or links_map.get(episode_id) or []

    if not ep_links:
        api.notify("Resolving next episode…")
        try:
            api.post("/realdebrid/resolve-episode/%d" % episode_id, _timeout=120)
        except api.APIError as e:
            api.handle_error(e)
            xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
            return
        for _ in range(15):
            try:
                status = api.get("/realdebrid/resolve-episode-status/%d" % episode_id)
            except api.APIError:
                status = {}
            ep_links = status.get("links") or []
            if ep_links:
                break
            time.sleep(2)

    if not ep_links:
        api.notify("No cached releases for next episode",
                   icon=xbmcgui.NOTIFICATION_WARNING)
        xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
        return

    link = _pick_link(ep_links, pref)
    if not link:
        xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
        return
    play.play_episode(handle, int(link["id"]), int(episode_id), int(show_id))


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


# ---------------------------------------------------------------------------
# Pick a release (context-menu) — anime hybrid lazy-resolve
# ---------------------------------------------------------------------------


def _format_size_gb(b):
    try:
        n = int(b or 0)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    gb = n / (1024 ** 3)
    if gb >= 1:
        return "%.1f GB" % gb
    return "%d MB" % (n // (1024 * 1024))


def pick_release(handle, episode_id, show_id, season):
    """Fetch the full candidate list (server runs Otaku-style pipeline:
    scrape Nyaa + AT + Torrentio prefilter + DMM cache check + file-match
    filter), show a select dialog, and on pick call /resolve-magnet to
    addMagnet that ONE hash. Avoids RD's burst anti-probe by never
    bursting addMagnet calls."""
    progress = xbmcgui.DialogProgressBG()
    progress.create("movieRec", "Fetching cached releases…")
    try:
        data = api.get("/realdebrid/episode-candidates/%d" % episode_id, _timeout=30)
    except api.APIError as e:
        progress.close()
        api.handle_error(e)
        return
    progress.close()
    candidates = (data or {}).get("candidates") or []
    if not candidates:
        # If this is anime, give the user a one-tap escape into the
        # embed-source picker (no-RD fallback). We have to look up the
        # show's anime flag separately — pick_release was traditionally
        # episode-only.
        try:
            show_meta = (api.get("/shows/%d" % show_id).get("show") or {})
        except api.APIError:
            show_meta = {}
        if show_meta.get("is_anime") and show_meta.get("mal_id"):
            ask = xbmcgui.Dialog().yesno(
                "movieRec",
                "No cached releases. Try embed sources instead?",
                yeslabel="Embed sources", nolabel="Cancel")
            if ask:
                xbmc.executebuiltin("RunPlugin(%s)" % _url(
                    action="pick_embed_source", episode_id=episode_id,
                    show_id=show_id, season=season))
            return
        xbmcgui.Dialog().notification("movieRec", "No cached releases found",
                                       xbmcgui.NOTIFICATION_WARNING, 3500)
        return

    # Build human-readable labels — quality, size, source, title.
    labels = []
    for c in candidates:
        q = c.get("quality") or "?"
        src = (c.get("source_site") or "")[:11]
        size = _format_size_gb(c.get("size_bytes"))
        seeders = c.get("seeders") or 0
        title = (c.get("title") or "").split("\n", 1)[0][:75]
        tag = "[COLOR green]●[/COLOR] " if c.get("already_resolved") else ""
        parts = ["[%s]" % q]
        if size:
            parts.append(size)
        if src:
            parts.append("(%s)" % src)
        if seeders > 0:
            parts.append("👤%d" % seeders)
        labels.append("%s%s %s" % (tag, " ".join(parts), title))

    idx = xbmcgui.Dialog().select("Pick a release", labels)
    if idx < 0:
        return
    chosen = candidates[idx]
    hash_ = chosen.get("hash") or ""
    if not hash_:
        return

    # If already resolved, jump straight to play — no addMagnet round-trip.
    if chosen.get("already_resolved"):
        # The existing /season endpoint embeds resolved links keyed by
        # episode id; refresh the season view + auto-play not trivial
        # here, so instead call the existing play action by fetching the
        # link id. Simplest: re-fetch season detail to find the link id.
        try:
            sdata = api.get("/shows/%d/seasons/%d" % (show_id, season))
            links_map = sdata.get("links") or {}
            ep_links = links_map.get(str(episode_id)) or links_map.get(episode_id) or []
            for l in ep_links:
                if (l.get("magnet_hash") or "") == hash_:
                    xbmc.executebuiltin("PlayMedia(%s)" % _url(
                        action="play_episode", link_id=l["id"],
                        episode_id=episode_id, show_id=show_id))
                    return
        except api.APIError:
            pass
        # Fall through to resolve-magnet path if we couldn't find the
        # link id (cache may be stale).

    progress = xbmcgui.DialogProgressBG()
    progress.create("movieRec", "Resolving %s..." % ((chosen.get("title") or "")[:40]))
    body = {
        "hash":        hash_,
        "title":       chosen.get("title") or "",
        "quality":     chosen.get("quality") or "",
        "size_bytes":  int(chosen.get("size_bytes") or 0),
        "seeders":     int(chosen.get("seeders") or 0),
        "source_site": chosen.get("source_site") or "",
    }
    try:
        resp = api.post("/realdebrid/resolve-magnet/%d" % episode_id,
                         body=body, _timeout=60)
    except api.APIError as e:
        progress.close()
        api.notify("Resolve failed: %s" % str(e)[:80],
                   icon=xbmcgui.NOTIFICATION_ERROR)
        return
    progress.close()
    link = (resp or {}).get("link") or {}
    if not link.get("id"):
        api.notify("RD returned no playable link",
                   icon=xbmcgui.NOTIFICATION_WARNING)
        return
    # Hand off to the existing play_episode action.
    xbmc.executebuiltin("PlayMedia(%s)" % _url(
        action="play_episode", link_id=link["id"],
        episode_id=episode_id, show_id=show_id))


def pick_embed_source(handle, episode_id, show_id, season):
    """Anime no-RD fallback: fetch embed sources from the server's
    anime-resolver sidecar (vendored Otaku scrapers + JS decryption),
    show a picker, and play the selected HLS URL directly. The URL +
    Referer/Origin/User-Agent headers come from the sidecar; we stitch
    them back into Kodi's `URL|k=v&k=v` stream-header form for playback.
    """
    progress = xbmcgui.DialogProgressBG()
    progress.create("movieRec", "Fetching embed sources…")
    try:
        data = api.get("/anime/embed-sources/%d" % episode_id, _timeout=90)
    except api.APIError as e:
        progress.close()
        api.handle_error(e)
        return
    progress.close()
    sources = (data or {}).get("sources") or []
    if not sources:
        xbmcgui.Dialog().notification("movieRec", "No embed sources found",
                                       xbmcgui.NOTIFICATION_WARNING, 3500)
        return

    # Labels: "[provider] [Server X] [sub/dub] [quality]"
    labels = []
    for s in sources:
        parts = ["[%s]" % (s.get("provider") or "?")]
        if s.get("server"):
            parts.append(s["server"])
        lang = s.get("lang") or ""
        if lang:
            parts.append(lang.upper())
        if s.get("quality"):
            parts.append(s["quality"])
        if (s.get("subs") or []):
            parts.append("(+subs)")
        labels.append(" ".join(parts))

    idx = xbmcgui.Dialog().select("Pick embed source", labels)
    if idx < 0:
        return
    chosen = sources[idx]
    url = chosen.get("url")
    if not url:
        api.notify("Empty stream URL", icon=xbmcgui.NOTIFICATION_ERROR)
        return

    # Kodi accepts custom HTTP headers on stream URLs as `|k=v&k=v...`
    # — encoded so the player forwards them on the manifest + segment
    # requests. Without these, the CDN returns 403/404 (embed providers
    # check Referer/Origin/User-Agent strictly).
    headers = chosen.get("headers") or {}
    if headers:
        pairs = "&".join("%s=%s" % (k, urllib.parse.quote(v, safe=""))
                         for k, v in headers.items())
        play_url = url + "|" + pairs
    else:
        play_url = url

    ep_data = api.get("/shows/%d/seasons/%d" % (show_id, season))
    ep = next((e for e in (ep_data.get("episodes") or [])
               if e.get("id") == episode_id), {}) or {}
    show_meta = ep_data.get("show") or {}

    li = xbmcgui.ListItem(path=play_url)
    vinfo = {
        "tvshowtitle": show_meta.get("title") or "",
        "title": ep.get("name") or "",
        "season": int(ep.get("season_number") or season),
        "episode": int(ep.get("episode_number") or 0),
        "mediatype": "episode",
    }
    if ep.get("overview"):
        vinfo["plot"] = ep["overview"]
    if ep.get("air_date"):
        vinfo["aired"] = ep["air_date"]
    li.setInfo("video", vinfo)
    # Most embed M3U8s are HLS — set the right mimetype so InputStream
    # Adaptive picks them up cleanly (auto-bitrate, subtitle tracks).
    li.setProperty("inputstream", "inputstream.adaptive")
    li.setProperty("inputstream.adaptive.manifest_type", "hls")
    if headers:
        li.setProperty("inputstream.adaptive.stream_headers", pairs)
    subs = chosen.get("subs") or []
    if subs:
        li.setSubtitles([s["url"] for s in subs if s.get("url")])

    # We're invoked via RunPlugin from a context menu (handle == -1), so
    # setResolvedUrl is a no-op. Start playback directly through the
    # Kodi player API instead.
    xbmc.Player().play(play_url, li)
