"""Thin wrapper around the movieRec server's /aniskip proxy.

Returns intro/outro skip windows for a given show + per-show episode
number. Both fields can be None when the upstream APIs (aniskip.com
and anime-skip.com) have no data for the episode — caller should
treat that as "no skip UI for this episode".
"""
from . import api


def get_skip_times(show_id, episode_number):
    """Fetch intro/outro times in seconds.

    Returns a dict with keys 'intro' and 'outro', each either None or
    a dict {'start': float, 'end': float}.
    """
    try:
        data = api.get("/aniskip/%d/%d" % (int(show_id), int(episode_number)),
                       _timeout=10)
    except api.APIError:
        return {"intro": None, "outro": None}
    return {
        "intro": data.get("intro") if data else None,
        "outro": data.get("outro") if data else None,
    }
