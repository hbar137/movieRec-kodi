# Vendored from https://github.com/Goldenfreddy0703/Otaku.git @ b8a38cdb4070
#   plugin.video.otaku/resources/lib/endpoints/malsync.py
# Regenerate via scripts/update-otaku-scrapers.py
# License: GPL-3.0 (Otaku).
from ..ui import client

baseUrl = 'https://api.malsync.moe'


def get_slugs(mal_id, site=''):
    slugs = []
    if site in ['Gogoanime', 'Zoro', 'animepahe']:
        response = client.get(f'{baseUrl}/mal/anime/{mal_id}')
        if response:
            resp = response.json().get('Sites', {}).get(site)
            if resp:
                for key in resp.keys():
                    slugs.append(resp[key].get('url'))
    return slugs


def get_title(mal_id, site=''):
    if site in ['Gogoanime', 'Zoro', 'animepahe']:
        response = client.get(f'{baseUrl}/mal/anime/{mal_id}')
        if response:
            resp = response.json().get('Sites', {}).get(site)
            if resp:
                for key in resp.keys():
                    title = resp[key].get('title')
                    if title:
                        return title
    return None
