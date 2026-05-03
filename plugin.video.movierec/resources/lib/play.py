"""Resolve a debrid link, hand the stream URL to Kodi, attach subtitles, and scrobble."""
import threading
import time

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

from . import api, scrobble

ADDON = xbmcaddon.Addon()


def _quality_rank(q):
    return {"4K": 1, "1080p": 2, "720p": 3}.get(q, 4)


def _pick_link(links, pref):
    if not links:
        return None
    if pref and pref != "auto":
        for l in links:
            if l.get("quality") == pref:
                return l
    # auto: best quality available, by seeders
    return sorted(links, key=lambda l: (_quality_rank(l.get("quality", "")),
                                        -int(l.get("seeders") or 0)))[0]


def _fetch_subtitle_urls(movie_id):
    langs = ADDON.getSettingString("subtitle_languages") or "en"
    try:
        results = api.get("/subtitles/%d" % movie_id, languages=langs)
    except api.APIError:
        return []
    urls = []
    for s in results or []:
        source = s.get("source") or "opensubtitles"
        file_id = s.get("file_id") or s.get("id")
        if not file_id:
            continue
        # Subtitle URL must be fetchable without custom headers, so embed password
        url = api.signed_url("/subtitle-file/%s/%s" % (source, file_id))
        urls.append(url)
    return urls[:5]  # cap to keep things sane


def play_link(handle, link_id, movie_id):
    info = api.get("/play/%d" % link_id)
    stream_url = info.get("stream_url")
    if not stream_url:
        api.notify("No stream URL available", icon=xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
        return

    li = xbmcgui.ListItem(path=stream_url)
    title = info.get("title") or info.get("filename") or "movieRec"
    vinfo = {"title": title, "mediatype": "movie"}
    if info.get("year"):
        vinfo["year"] = int(info["year"])
    if info.get("imdb_id"):
        vinfo["imdbnumber"] = info["imdb_id"]
    if info.get("overview"):
        vinfo["plot"] = info["overview"]
    li.setInfo("video", vinfo)

    sub_urls = _fetch_subtitle_urls(movie_id) if movie_id else []
    if sub_urls:
        li.setSubtitles(sub_urls)

    xbmcplugin.setResolvedUrl(handle, True, li)

    # Start scrobble watcher in a daemon thread; it lives until playback ends.
    if ADDON.getSettingBool("scrobble_enabled") and info.get("imdb_id"):
        threading.Thread(
            target=scrobble.watch,
            args=(info["imdb_id"], title),
            daemon=True,
        ).start()


def resolve_and_play(handle, movie_id):
    api.notify("Resolving via Real-Debrid…")
    try:
        api.post("/realdebrid/resolve/%d" % movie_id)
    except api.APIError as e:
        api.handle_error(e)
        xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
        return

    # Poll resolve-status for up to ~30s waiting for at least one link
    pref = ADDON.getSettingString("quality_pref") or "auto"
    link = None
    for _ in range(15):
        status = api.get("/realdebrid/resolve-status/%d" % movie_id)
        links = status.get("links") or []
        if links:
            link = _pick_link(links, pref)
            if link:
                break
        time.sleep(2)

    if not link:
        api.notify("No cached releases found", icon=xbmcgui.NOTIFICATION_WARNING)
        xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
        return

    play_link(handle, link["id"], movie_id)
