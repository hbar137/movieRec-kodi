"""Plugin URL dispatch."""
import urllib.parse

import xbmcplugin

from . import api, views, play


def _parse(argv):
    handle = int(argv[1])
    qs = argv[2][1:] if argv[2].startswith("?") else argv[2]
    params = dict(urllib.parse.parse_qsl(qs))
    return handle, params


def dispatch(argv):
    handle, params = _parse(argv)
    action = params.get("action", "root")

    try:
        if action == "root":
            views.root(handle)
        elif action == "dashboard":
            views.dashboard(handle)
        elif action == "watchlist":
            views.watchlist(handle, page=int(params.get("page", "0")), params=params)
        elif action == "history":
            views.history(handle, page=int(params.get("page", "0")))
        elif action == "browse":
            views.browse(handle, page=int(params.get("page", "0")), params=params)
        elif action == "browse_menu":
            views.browse_menu(handle)
        elif action == "genres":
            views.genres(handle)
        elif action == "set_filter":
            target = params.pop("target", "browse")
            field = params.pop("field", "")
            params.pop("action", None)
            views.set_filter(handle, target, field, params)
        elif action == "search":
            views.search(handle)
        elif action == "search_new":
            views.search_new(handle)
        elif action == "search_clear":
            views.search_clear(handle)
        elif action == "search_results":
            views.search_results(handle, params.get("q", ""))
        elif action == "import_movie":
            views.import_movie(handle, int(params["movie_id"]))
        elif action == "movie":
            views.movie_detail(handle, int(params["movie_id"]))
        elif action == "play":
            play.play_link(handle, int(params["link_id"]),
                           int(params.get("movie_id", "0")))
        elif action == "resolve_links":
            views.resolve_links(handle, int(params["movie_id"]))
        else:
            views.root(handle)
    except api.APIError as e:
        api.handle_error(e)
        xbmcplugin.endOfDirectory(handle, succeeded=False)
