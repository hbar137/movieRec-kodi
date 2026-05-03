"""Resolve a debrid link, hand the stream URL to Kodi, attach subtitles, and scrobble."""
import threading
import time

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

from . import api, scrobble, progress as progress_mod

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


def _sanitize_label(s):
    out = []
    for ch in (s or ""):
        if ch.isalnum() or ch in ("-", "_", ".", "(", ")"):
            out.append(ch)
        elif ch in (" ", "/", "\\", ":"):
            out.append(".")
    cleaned = "".join(out).strip(".")
    while ".." in cleaned:
        cleaned = cleaned.replace("..", ".")
    return cleaned or "subtitle"


def _fetch_subtitle_urls(movie_id, movie_title=None, year=None):
    import urllib.parse as _ulp
    langs = ADDON.getSettingString("subtitle_languages") or "en"
    try:
        results = api.get("/subtitles/%d" % movie_id, languages=langs)
    except api.APIError:
        return []
    urls = []
    base = _sanitize_label(movie_title or "movie")
    if year:
        base += ".%s" % year
    for s in results or []:
        source = s.get("source") or "opensubtitles"
        file_id = s.get("file_id") or s.get("id")
        if not file_id:
            continue
        # Build a friendly basename Kodi will display in the subtitle picker.
        # Prefer the provider-supplied release/file name if present.
        provider_name = s.get("file_name") or s.get("release") or ""
        lang = (s.get("language") or "").lower() or langs.split(",")[0]
        if provider_name:
            label = _sanitize_label(provider_name)
            if not label.lower().endswith(".srt"):
                label += ".srt"
        else:
            label = "%s.%s.srt" % (base, lang)
        encoded_id = _ulp.quote(str(file_id), safe="")
        url = api.signed_url("/subtitle-file/%s/%s/%s" % (source, encoded_id, label))
        urls.append(url)
    return urls[:5]


def _format_hms(seconds):
    s = int(seconds or 0)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return "%d:%02d:%02d" % (h, m, sec)
    return "%d:%02d" % (m, sec)


def play_link(handle, link_id, movie_id):
    info = api.get("/play/%d" % link_id)
    stream_url = info.get("stream_url")
    if not stream_url:
        api.notify("No stream URL available", icon=xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
        return

    # Resume offer: only if we have a saved position deep enough to matter and
    # not so close to the end that "resume" would just credits-roll.
    pos = int(info.get("position_seconds") or 0)
    dur = int(info.get("duration_seconds") or 0)
    resume_offset = 0
    if pos > 60 and (dur <= 0 or pos < int(0.9 * dur)):
        msg = "Resume from %s?" % _format_hms(pos)
        if dur > 0:
            msg += "  (of %s)" % _format_hms(dur)
        if xbmcgui.Dialog().yesno("movieRec", msg, yeslabel="Resume", nolabel="Start over"):
            resume_offset = pos

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
    if resume_offset:
        li.setProperty("StartOffset", str(resume_offset))
        li.setProperty("ResumeTime", str(resume_offset))
        if dur > 0:
            li.setProperty("TotalTime", str(dur))

    sub_urls = _fetch_subtitle_urls(movie_id, info.get("title"), info.get("year")) if movie_id else []
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

    # Progress reporter — saves resume position to the server every ~10s + on stop.
    if movie_id:
        threading.Thread(
            target=progress_mod.watch,
            args=(int(movie_id), int(link_id)),
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
