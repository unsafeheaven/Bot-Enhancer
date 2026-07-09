"""
Fetch real album art from the iTunes Search API (no API key required).
Used for song drop embeds and daily banner/avatar rotation.
"""
import logging
from typing import Optional

import aiohttp

log = logging.getLogger("bot")

_ITUNES_SEARCH = "https://itunes.apple.com/search"


async def fetch_art_url(artist: str, song: str = "", size: int = 600) -> Optional[str]:
    """
    Return a direct image URL for the given artist/song from the iTunes API.
    size can be 100, 300, or 600 (iTunes only provides those three).
    Returns None if nothing is found or the request fails.
    """
    query = f"{artist} {song}".strip()
    params = {"term": query, "media": "music", "limit": "1"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                _ITUNES_SEARCH, params=params, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
                results = data.get("results")
                if not results:
                    return None
                raw = results[0].get("artworkUrl100", "")
                if not raw:
                    return None
                return raw.replace("100x100bb", f"{size}x{size}bb")
    except Exception as e:
        log.debug(f"iTunes art lookup failed for '{query}': {e}")
        return None


async def fetch_image_bytes(url: str) -> Optional[bytes]:
    """Download raw image bytes from a URL. Returns None on failure."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return None
                return await resp.read()
    except Exception as e:
        log.debug(f"Image fetch failed for '{url}': {e}")
        return None
