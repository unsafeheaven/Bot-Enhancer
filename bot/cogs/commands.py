"""
Slash commands cog.
"""
import discord
from discord import app_commands
from discord.ext import commands

from utils.history import history_manager
from utils.ai import get_ai_response
from cogs.chat import _is_admin


class CommandsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ask", description="ask the bot something directly")
    @app_commands.checks.cooldown(1, 5.0, key=lambda i: i.user.id)
    async def ask(self, interaction: discord.Interaction, prompt: str):
        """Direct slash command to ask the bot something."""
        await interaction.response.defer()
        channel_id = interaction.channel_id
        username = interaction.user.display_name

        admin = _is_admin(interaction.user)
        history = history_manager.get_messages(channel_id)
        response = await get_ai_response(history, f"{username}: {prompt}", is_admin=admin)

        history_manager.add(channel_id, "user", prompt, username)
        history_manager.add(channel_id, "assistant", response)

        await interaction.followup.send(response)

    @app_commands.command(name="roast", description="get roasted. you asked for this")
    @app_commands.checks.cooldown(1, 10.0, key=lambda i: i.user.id)
    async def roast(self, interaction: discord.Interaction, target: discord.Member | None = None):
        """Roast yourself or someone else."""
        await interaction.response.defer()
        victim = target or interaction.user
        username = victim.display_name
        channel_id = interaction.channel_id

        admin = _is_admin(interaction.user)
        prompt = f"roast {username} in one short line, gen z style, keep it playful not mean"
        history = history_manager.get_messages(channel_id)
        response = await get_ai_response(history, prompt, is_admin=admin)

        history_manager.add(channel_id, "assistant", response)
        await interaction.followup.send(response)

    @app_commands.command(name="vibe", description="vibe check — how's the chat energy rn")
    @app_commands.checks.cooldown(1, 10.0, key=lambda i: i.channel_id)
    async def vibe(self, interaction: discord.Interaction):
        """Check the vibe of recent chat."""
        await interaction.response.defer()
        channel_id = interaction.channel_id

        history = history_manager.get_messages(channel_id)
        if not history:
            await interaction.followup.send("chat is dead bro 💔")
            return

        prompt = "based on recent chat, give a 1-2 sentence vibe check of the conversation energy. be chill and honest"
        response = await get_ai_response(history, prompt)
        history_manager.add(channel_id, "assistant", response)
        await interaction.followup.send(response)

    @app_commands.command(name="reset", description="clear my memory for this channel")
    async def reset(self, interaction: discord.Interaction):
        """Clear conversation history for this channel."""
        history_manager.clear(interaction.channel_id)
        await interaction.response.send_message("memory wiped. fresh start ig 🙏", ephemeral=True)

    @app_commands.command(name="help", description="see what i can do (not much)")
    async def help_cmd(self, interaction: discord.Interaction):
        """List available commands."""
        embed = discord.Embed(
            title="commands n stuff",
            description="here's what u can do i guess",
            color=0x2b2d31,
        )
        embed.add_field(name="/ask [prompt]", value="ask me something directly", inline=False)
        embed.add_field(name="/roast [@user]", value="get roasted. u deserve it", inline=False)
        embed.add_field(name="/vibe", value="vibe check the current chat", inline=False)
        embed.add_field(name="/reset", value="wipe my memory for this channel", inline=False)
        embed.add_field(
            name="mention me",
            value="just @ me and talk. or say **servent** + your message",
            inline=False,
        )
        embed.set_footer(text="im literally just vibing here")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ask.error
    @roast.error
    @vibe.error
    async def on_cooldown_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            msg = f"chill out lil bro. wait {error.retry_after:.0f}s 💔"
        else:
            # Log unexpected errors but keep it chill for the user
            import logging
            logging.getLogger("bot").error(f"Slash command error: {error}", exc_info=error)
            msg = "something broke on my end 💀 try again"

        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(CommandsCog(bot))
