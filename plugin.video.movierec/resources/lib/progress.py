"""Playback position reporter — POSTs current position to /api/kodi/progress
every ~10s and on stop, so the server can offer a Resume prompt next time."""
import xbmc

from . import api


def _send(movie_id, link_id, position, duration):
    try:
        api.post("/progress", body={
            "movie_id": int(movie_id),
            "link_id": int(link_id),
            "position": float(position),
            "duration": float(duration),
        })
    except api.APIError as e:
        xbmc.log("[movieRec] progress save failed: %s" % e, xbmc.LOGWARNING)


def watch(movie_id, link_id):
    """Block until playback ends, snapshotting position every ~10s.

    Mirrors scrobble.watch's polling shape (no Player subclass — those get
    GC'd when the plugin handler returns)."""
    player = xbmc.Player()

    for _ in range(20):
        if player.isPlaying():
            break
        xbmc.sleep(500)
    else:
        return

    monitor = xbmc.Monitor()
    last_pos = 0.0
    duration = 0.0

    while not monitor.abortRequested() and player.isPlaying():
        try:
            cur = player.getTime()
            if duration <= 0:
                duration = player.getTotalTime() or 0.0
        except RuntimeError:
            break

        last_pos = cur
        _send(movie_id, link_id, cur, duration)

        if monitor.waitForAbort(10):
            break

    # Final flush on stop. Server treats >=95% as finished and clears position.
    _send(movie_id, link_id, last_pos, duration)


def _send_episode(episode_id, show_id, link_id, position, duration):
    try:
        api.post("/progress-episode", body={
            "episode_id": int(episode_id),
            "show_id": int(show_id),
            "link_id": int(link_id),
            "position": float(position),
            "duration": float(duration),
        })
    except api.APIError as e:
        xbmc.log("[movieRec] episode progress save failed: %s" % e, xbmc.LOGWARNING)


def watch_episode(episode_id, show_id, link_id):
    player = xbmc.Player()

    for _ in range(20):
        if player.isPlaying():
            break
        xbmc.sleep(500)
    else:
        return

    monitor = xbmc.Monitor()
    last_pos = 0.0
    duration = 0.0

    while not monitor.abortRequested() and player.isPlaying():
        try:
            cur = player.getTime()
            if duration <= 0:
                duration = player.getTotalTime() or 0.0
        except RuntimeError:
            break

        last_pos = cur
        _send_episode(episode_id, show_id, link_id, cur, duration)

        if monitor.waitForAbort(10):
            break

    _send_episode(episode_id, show_id, link_id, last_pos, duration)
