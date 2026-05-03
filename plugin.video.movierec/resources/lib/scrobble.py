"""Trakt scrobble watcher — polls the active xbmc.Player and POSTs to /api/kodi/scrobble."""
import xbmc

from . import api


def _send(action, imdb_id, progress):
    try:
        api.post("/scrobble", body={
            "action": action,
            "imdb_id": imdb_id,
            "progress": float(progress),
        })
    except api.APIError as e:
        xbmc.log("[movieRec] scrobble %s failed: %s" % (action, e), xbmc.LOGWARNING)


def watch(imdb_id, title):
    """Block until playback ends, sending start/pause/stop scrobbles to the server.

    Runs in a background thread spawned from play_link. We rely on xbmc.Player
    polling rather than subclassing because subclasses created from a plugin
    handler get garbage-collected when the handler returns.
    """
    player = xbmc.Player()

    # Wait up to 10s for playback to actually begin.
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

    started = False
    last_progress = 0.0
    last_paused = None  # tri-state: None unknown, True paused, False playing
    monitor = xbmc.Monitor()

    while not monitor.abortRequested() and player.isPlaying():
        try:
            cur = player.getTime()
            if duration <= 0:
                duration = player.getTotalTime() or 0.0
        except RuntimeError:
            break

        progress = (cur / duration * 100.0) if duration > 0 else 0.0
        last_progress = progress

        if not started:
            _send("start", imdb_id, progress)
            started = True
            last_paused = False

        # Pause detection: Kodi exposes playback speed via JSON-RPC; cheap
        # heuristic — if time hasn't moved across two ticks, treat as paused.
        # Simpler: skip pause scrobbles in v1; start+stop is enough for Trakt
        # to record the watch.

        if monitor.waitForAbort(5):
            break

    # Playback ended — send stop with final progress.
    if started:
        _send("stop", imdb_id, last_progress)
