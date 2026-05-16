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
        if xbmcgui.Dialog().yesno("movieRec", msg,
                                   yeslabel="Resume", nolabel="Start over",
                                   defaultbutton=xbmcgui.DLG_YESNO_YES_BTN):
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


def _fetch_episode_subtitle_urls(episode_id, show_title=None, season=None, episode=None):
    import urllib.parse as _ulp
    langs = ADDON.getSettingString("subtitle_languages") or "en"
    try:
        results = api.get("/episode-subtitles/%d" % episode_id, languages=langs)
    except api.APIError:
        return []
    urls = []
    base = _sanitize_label(show_title or "show")
    if season and episode:
        base += ".S%02dE%02d" % (int(season), int(episode))
    for s in results or []:
        source = s.get("source") or "opensubtitles"
        file_id = s.get("file_id") or s.get("id")
        if not file_id:
            continue
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


def play_episode(handle, link_id, episode_id, show_id):
    """Resolve an episode link, hand stream to Kodi with episode InfoLabels +
    subtitles, then spawn scrobble + progress watchers."""
    info = api.get("/play-episode/%d" % link_id)
    stream_url = info.get("stream_url")
    if not stream_url:
        api.notify("No stream URL available", icon=xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
        return

    pos = int(info.get("position_seconds") or 0)
    dur = int(info.get("duration_seconds") or 0)
    resume_offset = 0
    if pos > 60 and (dur <= 0 or pos < int(0.9 * dur)):
        msg = "Resume from %s?" % _format_hms(pos)
        if dur > 0:
            msg += "  (of %s)" % _format_hms(dur)
        if xbmcgui.Dialog().yesno("movieRec", msg,
                                   yeslabel="Resume", nolabel="Start over",
                                   defaultbutton=xbmcgui.DLG_YESNO_YES_BTN):
            resume_offset = pos

    li = xbmcgui.ListItem(path=stream_url)
    show_title = info.get("show_title") or "movieRec"
    ep_title = info.get("episode_title") or info.get("filename") or ""
    season_num = int(info.get("season_number") or 0)
    ep_num = int(info.get("episode_number") or 0)

    vinfo = {
        "tvshowtitle": show_title,
        "title": ep_title,
        "season": season_num,
        "episode": ep_num,
        "mediatype": "episode",
    }
    if info.get("show_year"):
        try:
            vinfo["year"] = int(info["show_year"])
        except (TypeError, ValueError):
            pass
    if info.get("episode_imdb_id"):
        vinfo["imdbnumber"] = info["episode_imdb_id"]
    elif info.get("show_imdb_id"):
        vinfo["imdbnumber"] = info["show_imdb_id"]
    if info.get("episode_overview"):
        vinfo["plot"] = info["episode_overview"]
    if info.get("air_date"):
        vinfo["aired"] = info["air_date"]
    li.setInfo("video", vinfo)
    if resume_offset:
        li.setProperty("StartOffset", str(resume_offset))
        li.setProperty("ResumeTime", str(resume_offset))
        if dur > 0:
            li.setProperty("TotalTime", str(dur))

    sub_urls = _fetch_episode_subtitle_urls(
        episode_id, show_title, season_num, ep_num)
    if sub_urls:
        li.setSubtitles(sub_urls)

    xbmcplugin.setResolvedUrl(handle, True, li)

    # Trakt scrobble — episode form needs (show_imdb, S, E).
    if (ADDON.getSettingBool("scrobble_enabled")
            and info.get("show_imdb_id") and season_num and ep_num):
        threading.Thread(
            target=scrobble.watch_episode,
            args=(info["show_imdb_id"], season_num, ep_num,
                  "%s S%02dE%02d" % (show_title, season_num, ep_num)),
            daemon=True,
        ).start()

    # Progress / resume reporter.
    threading.Thread(
        target=progress_mod.watch_episode,
        args=(int(episode_id), int(show_id), int(link_id)),
        daemon=True,
    ).start()

    # Auto-play next episode watcher — fires PlayMedia(...) when this episode
    # ends with progress ≥ 85% (i.e. natural end, not user stop).
    if ADDON.getSettingBool("autoplay_next_episode") and show_id and season_num and ep_num:
        threading.Thread(
            target=_autoplay_next_watcher,
            args=(int(show_id), int(season_num), int(ep_num)),
            daemon=True,
        ).start()


def _autoplay_next_watcher(show_id, season_num, episode_num):
    """Block until playback ends. If ≥85% watched, look up the next episode
    and trigger PlayMedia. Kodi routes that back through default.py with a
    fresh handle, so resolve+play happens cleanly."""
    import sys
    import urllib.parse as _ulp

    player = xbmc.Player()
    for _ in range(20):
        if player.isPlaying():
            break
        xbmc.sleep(500)
    else:
        return

    duration = 0.0
    try:
        duration = player.getTotalTime()
    except RuntimeError:
        return

    last_progress = 0.0
    monitor = xbmc.Monitor()
    while not monitor.abortRequested() and player.isPlaying():
        try:
            cur = player.getTime()
            if duration <= 0:
                duration = player.getTotalTime() or 0.0
        except RuntimeError:
            break
        if duration > 0:
            last_progress = cur / duration * 100.0
        if monitor.waitForAbort(5):
            return

    # Playback ended. Only auto-advance on a natural finish.
    if last_progress < 85.0:
        return

    nxt = _find_next_episode(show_id, season_num, episode_num)
    if not nxt:
        return

    base = sys.argv[0] if sys.argv else "plugin://plugin.video.movierec/"
    qs = _ulp.urlencode({
        "action": "play_next_episode",
        "episode_id": nxt["id"],
        "show_id": show_id,
        "season": nxt["season_number"],
    })
    url = "%s?%s" % (base, qs)
    api.notify("Up next: S%02dE%02d %s" % (
        int(nxt.get("season_number") or 0),
        int(nxt.get("episode_number") or 0),
        nxt.get("name") or ""))
    xbmc.executebuiltin('PlayMedia(%s)' % url)


def _find_next_episode(show_id, current_season, current_episode_num):
    """Return the dict for the next episode in viewing order, or None.

    Tries the current season first; falls back to episode 1 of the next
    season that has any episodes. Skips specials (season 0)."""
    try:
        data = api.get("/shows/%d/seasons/%d" % (show_id, current_season))
    except api.APIError:
        data = None
    if data:
        for ep in (data.get("episodes") or []):
            if (ep.get("episode_number") or 0) == current_episode_num + 1:
                return ep

    # No next episode in this season — try the next non-special season.
    try:
        show_data = api.get("/shows/%d" % show_id)
    except api.APIError:
        return None
    seasons = sorted(
        (s for s in (show_data.get("seasons") or [])
         if (s.get("season_number") or 0) > current_season
         and (s.get("episode_count") or 0) > 0),
        key=lambda s: s.get("season_number") or 0,
    )
    for s in seasons:
        try:
            sd = api.get("/shows/%d/seasons/%d" % (show_id, s["season_number"]))
        except api.APIError:
            continue
        eps = sd.get("episodes") or []
        if eps:
            # Pick the lowest episode number (usually 1).
            return sorted(eps, key=lambda e: e.get("episode_number") or 0)[0]
    return None


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
