"""
Main entry point for the Discord bot.
"""
import asyncio
import os
import random
import sys
import logging

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

# Load .env if present (local dev)
load_dotenv()

# Logging — Discord.py and bot logs
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
intents.message_content = True  # required to read message text
intents.members = True  # required to see the full member roster (for "rate N people")

bot = commands.Bot(
    command_prefix="!",   # unused but required by discord.py
    intents=intents,
    help_command=None,    # we have our own /help
)

# Rotating presence so she looks "alive" even when no one's actively talking to her —
# a mix of listening/playing/watching statuses that match her music-obsessed identity.
_PRESENCES = [
    discord.Activity(type=discord.ActivityType.listening, name="a new playlist"),
    discord.Activity(type=discord.ActivityType.listening, name="indie music"),
    discord.Activity(type=discord.ActivityType.listening, name="a song on repeat"),
    discord.Activity(type=discord.ActivityType.playing, name="roblox"),
    discord.Activity(type=discord.ActivityType.watching, name="for good music recs"),
    discord.CustomActivity(name="making a playlist"),
    discord.CustomActivity(name="overthinking a text"),
    discord.CustomActivity(name="vibing"),
]


@tasks.loop(minutes=15)
async def rotate_presence():
    try:
        await bot.change_presence(activity=random.choice(_PRESENCES))
    except Exception as e:
        log.warning(f"Failed to rotate presence: {e}")


@bot.event
async def on_ready():
    log.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    log.info("Syncing slash commands to all guilds...")
    try:
        # Sync to every guild the bot is in for instant availability
        for guild in bot.guilds:
            try:
                bot.tree.copy_global_to(guild=guild)
                synced = await bot.tree.sync(guild=guild)
                log.info(f"Synced {len(synced)} command(s) to guild {guild.name} ({guild.id})")
            except Exception as e:
                log.warning(f"Failed to sync to guild {guild.id}: {e}")
        # Also do a global sync
        await bot.tree.sync()
    except Exception as e:
        log.error(f"Failed to sync commands: {e}")
    if not rotate_presence.is_running():
        rotate_presence.start()
    log.info("Bot is ready. vibing 😎")


@bot.event
async def on_guild_join(guild: discord.Guild):
    """Instantly sync slash commands when the bot joins a new server."""
    log.info(f"Joined guild: {guild.name} ({guild.id})")
    try:
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        log.info(f"Synced {len(synced)} command(s) to new guild {guild.name}")
    except Exception as e:
        log.error(f"Failed to sync commands to new guild {guild.id}: {e}")


@bot.event
async def on_command_error(ctx: commands.Context, error):
    # Suppress unknown command errors (we use slash commands)
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
