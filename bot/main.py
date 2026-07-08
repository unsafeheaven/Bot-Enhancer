"""
Main entry point for the Discord bot.
"""
import asyncio
import os
import sys
import logging

import discord
from discord.ext import commands
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
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

if not DISCORD_TOKEN:
    log.error("DISCORD_TOKEN is not set. Add it to your Replit Secrets.")
    sys.exit(1)

if not OPENROUTER_API_KEY:
    log.error("OPENROUTER_API_KEY is not set. Add it to your Replit Secrets.")
    sys.exit(1)


# ── Bot setup ──────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True  # required to read message text

bot = commands.Bot(
    command_prefix="!",   # unused but required by discord.py
    intents=intents,
    help_command=None,    # we have our own /help
)


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
