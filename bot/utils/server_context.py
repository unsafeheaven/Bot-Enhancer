"""
Helpers for pulling live server context — recent top messages and member rosters —
so Rin can talk about what's actually happening in the server, not just the chat log.
"""
import random
from typing import List, Tuple

import discord


async def get_top_messages(
    channel: discord.abc.Messageable,
    scan_limit: int = 200,
    top_n: int = 5,
) -> List[Tuple[discord.Message, int]]:
    """Scan recent channel history and return the top_n messages by total reaction count."""
    scored: List[Tuple[discord.Message, int]] = []
    async for msg in channel.history(limit=scan_limit):
        if msg.author.bot or not msg.content:
            continue
        reaction_count = sum(r.count for r in msg.reactions)
        if reaction_count > 0:
            scored.append((msg, reaction_count))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:top_n]


async def get_members(guild: discord.Guild, exclude_bots: bool = True) -> List[discord.Member]:
    """Return the server's full member roster.

    Always does a fresh HTTP fetch rather than trusting the gateway cache, since the
    cache can be partially populated (present but incomplete) even with the Members
    intent enabled, and older/interrupted sessions can leave it stale. Falls back to
    the cache only if the fetch itself fails (e.g. Members intent isn't enabled).
    """
    try:
        members = [m async for m in guild.fetch_members(limit=None)]
    except discord.HTTPException:
        members = list(guild.members)
    if exclude_bots:
        members = [m for m in members if not m.bot]
    return members


async def get_random_members(guild: discord.Guild, n: int) -> List[discord.Member]:
    members = await get_members(guild)
    if not members:
        return []
    n = max(1, min(n, len(members)))
    return random.sample(members, n)
