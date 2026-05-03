# movieRec — Kodi add-on

Kodi video add-on for the [movieRec](https://github.com/hbar137/movieRec) server.
Browse dashboard, watchlist, history, and library; play movies via Real-Debrid
with subtitles; scrobble to Trakt.

## Install

The recommended path is to install the **repository** add-on once — after that
Kodi auto-updates `plugin.video.movierec` whenever a new version ships.

1. Allow third-party installs: Settings → System → Add-ons → **Unknown sources** on.
2. Download the repository zip on the Kodi device:
   <https://hbar137.github.io/movieRec-kodi/repository.movierec/repository.movierec-1.0.0.zip>
3. Kodi → Add-ons → box icon → **Install from zip file** → pick the downloaded zip.
4. Add-ons → box icon → **Install from repository** → **movieRec** → **Video add-ons** → **movieRec** → Install.
5. Open the add-on settings and set your password (server URL is preset).

### One-shot install (no auto-updates)

If you don't want the repository, you can install the plugin zip directly from
GitHub Releases — but you'll have to repeat this every version:
<https://github.com/hbar137/movieRec-kodi/releases>

## Repo layout

```
plugin.video.movierec/   # the actual add-on
repository.movierec/     # the repository add-on (lists itself + the plugin)
scripts/build-repo.py    # builds the gh-pages tree (zips + addons.xml + .md5)
.github/workflows/       # builds and publishes to gh-pages on push to main
```

## Releasing a new version

1. Bump `version=` in `plugin.video.movierec/addon.xml` (and/or `repository.movierec/addon.xml`).
2. Commit + push to `main`. The GitHub Action rebuilds and publishes to `gh-pages`.
3. Optionally create a GitHub Release tag for changelog purposes.

## Development

See [KODI.md](https://github.com/hbar137/movieRec/blob/main/KODI.md) in the
movieRec server repo for architecture and endpoint details.
