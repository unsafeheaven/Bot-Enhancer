"""
Main entry point for the Discord bot.
"""
import asyncio
import os
import sys
import logging
from datetime import datetime

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

from utils.music_art import fetch_art_url, fetch_image_bytes

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("bot")

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN", "")
CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY", "")

if not DISCORD_TOKEN:
    log.error("DISCORD_TOKEN is not set. Add it to your Replit Secrets.")
    sys.exit(1)

if not CEREBRAS_API_KEY:
    log.error("CEREBRAS_API_KEY is not set. Add it to your Replit Secrets.")
    sys.exit(1)

log.info("Rin is waking up 🤍")

# ── Bot setup ──────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None,
)

# ── 7-day schedule ─────────────────────────────────────────────────────────────
# One status + one featured artist/song per day of the week (0=Mon … 6=Sun).
# The status shows under her name in the member list / profile.
# The featured artist is fetched from iTunes each day to set her banner + avatar.

_DAILY_STATUSES = [
    discord.Activity(type=discord.ActivityType.listening, name="monday morning playlists"),   # Mon
    discord.CustomActivity(name="recovering from the weekend"),                                # Tue
    discord.Activity(type=discord.ActivityType.listening, name="sad girl hours"),             # Wed
    discord.CustomActivity(name="it's almost friday..."),                                      # Thu
    discord.Activity(type=discord.ActivityType.listening, name="it's giving friday"),         # Fri
    discord.Activity(type=discord.ActivityType.listening, name="music all day"),              # Sat
    discord.Activity(type=discord.ActivityType.listening, name="sunday morning indie"),       # Sun
]

# (artist, song) pairs — one per day. iTunes API will fetch real album art.
_DAILY_FEATURED: list[tuple[str, str]] = [
    ("Mitski", "Nobody"),                        # Mon
    ("Lana Del Rey", "Video Games"),             # Tue
    ("Olivia Rodrigo", "drivers license"),       # Wed
    ("The 1975", "Chocolate"),                   # Thu
    ("Arctic Monkeys", "Do I Wanna Know"),       # Fri
    ("Taylor Swift", "All Too Well"),            # Sat
    ("Phoebe Bridgers", "Moon Song"),            # Sun
]

_last_updated_weekday: int = -1   # track which day we last applied


async def _apply_daily(weekday: int):
    """Set status, banner, and avatar for the given weekday (0=Mon)."""
    # Status
    try:
        await bot.change_presence(activity=_DAILY_STATUSES[weekday])
        log.info(f"Daily status set for weekday {weekday}")
    except Exception as e:
        log.warning(f"Failed to set daily status: {e}")

    # Fetch album art for banner + avatar
    artist, song = _DAILY_FEATURED[weekday]
    art_url = await fetch_art_url(artist, song, size=600)
    if not art_url:
        log.warning(f"No art found for {artist} — {song}, skipping banner/avatar update")
        return

    img_bytes = await fetch_image_bytes(art_url)
    if not img_bytes:
        log.warning(f"Could not download art from {art_url}")
        return

    # Avatar (supported for all bots)
    try:
        await bot.user.edit(avatar=img_bytes)
        log.info(f"Daily avatar set: {artist} — {song}")
    except discord.HTTPException as e:
        log.warning(f"Avatar update failed (rate limited or unsupported): {e}")
    except Exception as e:
        log.warning(f"Avatar update error: {e}")

    # Banner (requires bot to have a banner slot — fails gracefully if not available)
    try:
        await bot.user.edit(banner=img_bytes)
        log.info(f"Daily banner set: {artist} — {song}")
    except discord.HTTPException as e:
        log.warning(f"Banner update failed (may not be supported for this bot): {e}")
    except Exception as e:
        log.warning(f"Banner update error: {e}")


@tasks.loop(minutes=30)
async def daily_update():
    """Check every 30 min whether the day has changed; apply schedule if so."""
    global _last_updated_weekday
    today = datetime.now().weekday()
    if today == _last_updated_weekday:
        return
    _last_updated_weekday = today
    await _apply_daily(today)


@daily_update.before_loop
async def _before_daily_update():
    await bot.wait_until_ready()


# ── Events ─────────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    global _last_updated_weekday
    log.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    log.info("Syncing slash commands to all guilds...")
    try:
        for guild in bot.guilds:
            try:
                bot.tree.copy_global_to(guild=guild)
                synced = await bot.tree.sync(guild=guild)
                log.info(f"Synced {len(synced)} command(s) to guild {guild.name} ({guild.id})")
            except Exception as e:
                log.warning(f"Failed to sync to guild {guild.id}: {e}")
        await bot.tree.sync()
    except Exception as e:
        log.error(f"Failed to sync commands: {e}")

    # Apply today's schedule immediately on startup
    today = datetime.now().weekday()
    _last_updated_weekday = today
    await _apply_daily(today)

    if not daily_update.is_running():
        daily_update.start()

    log.info("Bot is ready. vibing 😎")


@bot.event
async def on_guild_join(guild: discord.Guild):
    log.info(f"Joined guild: {guild.name} ({guild.id})")
    try:
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        log.info(f"Synced {len(synced)} command(s) to new guild {guild.name}")
    except Exception as e:
        log.error(f"Failed to sync commands to new guild {guild.id}: {e}")


@bot.event
async def on_command_error(ctx: commands.Context, error):
    if isinstance(error, commands.CommandNotFound):
        return
    raise error


async def load_cogs():
    await bot.load_extension("cogs.chat")
    await bot.load_extension("cogs.commands")
    log.info("All cogs loaded.")


async def main():
    async with bot:
        await load_cogs()
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
