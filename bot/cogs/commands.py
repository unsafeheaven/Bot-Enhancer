"""
Slash commands cog.
"""
import discord
from discord import app_commands
from discord.ext import commands

from utils.history import history_manager
from utils.ai import get_ai_response


class CommandsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ask", description="ask rin something directly")
    @app_commands.checks.cooldown(1, 5.0, key=lambda i: i.user.id)
    async def ask(self, interaction: discord.Interaction, prompt: str):
        """Direct slash command to ask Rin something."""
        await interaction.response.defer()
        channel_id = interaction.channel_id
        user_id = interaction.user.id
        username = interaction.user.display_name

        history_manager.remember(user_id, prompt)
        history = history_manager.get_messages(channel_id)
        facts = history_manager.get_facts(user_id)
        response = await get_ai_response(history, f"{username}: {prompt}", user_facts=facts)

        history_manager.add(channel_id, "user", prompt, username)
        history_manager.add(channel_id, "assistant", response)

        await interaction.followup.send(response)

    @app_commands.command(name="roast", description="get playfully roasted by rin")
    @app_commands.checks.cooldown(1, 10.0, key=lambda i: i.user.id)
    async def roast(self, interaction: discord.Interaction, target: discord.Member | None = None):
        """Roast yourself or someone else — affectionately, never mean."""
        await interaction.response.defer()
        victim = target or interaction.user
        username = victim.display_name
        channel_id = interaction.channel_id

        prompt = f"playfully roast {username} in one short line — teasing and funny, never genuinely mean or about their appearance"
        history = history_manager.get_messages(channel_id)
        response = await get_ai_response(history, prompt)

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
            await interaction.followup.send("chat is dead bro 💔 say something")
            return

        prompt = "based on recent chat, give a 1-2 sentence vibe check of the conversation energy. be honest and playful about it"
        response = await get_ai_response(history, prompt)
        history_manager.add(channel_id, "assistant", response)
        await interaction.followup.send(response)

    @app_commands.command(name="reset", description="make rin forget this channel's convo")
    async def reset(self, interaction: discord.Interaction):
        """Clear conversation history for this channel."""
        history_manager.clear(interaction.channel_id)
        await interaction.response.send_message("okay fine, fresh start ig 🙏 forgot everything", ephemeral=True)

    @app_commands.command(name="forgetme", description="make rin forget what she remembers about you")
    async def forgetme(self, interaction: discord.Interaction):
        """Clear remembered facts for the calling user."""
        history_manager.clear_facts(interaction.user.id)
        await interaction.response.send_message("okay... erased u from my brain 😔 happy now", ephemeral=True)

    @app_commands.command(name="help", description="see what rin can do")
    async def help_cmd(self, interaction: discord.Interaction):
        """List available commands."""
        embed = discord.Embed(
            title="hi it's rin 🤍",
            description="here's what i can do i guess",
            color=0xE39FC2,
        )
        embed.add_field(name="say \"rin\" or @ me", value="just talk to me, i'll answer", inline=False)
        embed.add_field(name="post a pic", value="i WILL react, no exceptions 😭", inline=False)
        embed.add_field(name="/ask [prompt]", value="ask me something directly", inline=False)
        embed.add_field(name="/roast [@user]", value="get roasted, affectionately", inline=False)
        embed.add_field(name="/vibe", value="vibe check the current chat", inline=False)
        embed.add_field(name="/reset", value="wipe my memory for this channel", inline=False)
        embed.add_field(name="/forgetme", value="make me forget stuff about u specifically", inline=False)
        embed.set_footer(text="fr just talk to me like a person")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Catches errors from every slash command in this cog, not just the ones with cooldowns."""
        if isinstance(error, app_commands.CommandOnCooldown):
            msg = f"chill out lil bro. wait {error.retry_after:.0f}s 💔"
        else:
            # Log unexpected errors but keep it in character for the user
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
