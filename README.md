# movieRec — Kodi add-on

A Kodi video add-on for the [movieRec](https://github.com/hbar137/movieRec)
server. Browse your dashboard, watchlist, history, and library; play movies via
Real-Debrid with subtitles; scrobble to Trakt.

## Install

1. Download `plugin.video.movierec-x.y.z.zip` from the [Releases](../../releases)
   page.
2. Kodi → Add-ons → "Install from zip file" → pick the zip.
3. Open the add-on and configure:
   - **Server URL** — e.g. `http://192.168.1.100:3032`
   - **Password** — must match `kodi_password` in the movieRec server settings.

## Server requirements

Server must expose `/api/kodi/*` (movieRec ≥ the commit that added Kodi
support) and have `kodi_password` set in Settings.

## Features

- Dashboard, Watchlist, History, Browse (with genre filter), Search.
- Movie detail shows resolved Real-Debrid links sorted by quality + seeders.
- Direct streaming from Real-Debrid (server is not in the data path).
- Subtitle search/download (OpenSubtitles + SubDL via the server).
- Trakt scrobble (start/stop) when enabled.

## Development

See [KODI.md](https://github.com/hbar137/movieRec/blob/main/KODI.md) in the
movieRec server repo for architecture, endpoints, and release process.
