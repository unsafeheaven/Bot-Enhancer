"""
Chat cog — handles message events, random replies, and 'servent' trigger.
"""
import random
import time
import re
import discord
from discord.ext import commands

from utils.ai import get_ai_response
from utils.history import history_manager


def _is_admin(user) -> bool:
    if not isinstance(user, discord.Member):
        return False
    return user.guild_permissions.administrator or user.guild_permissions.manage_guild

# Chance the bot randomly chimes in on a message (1 in N)
RANDOM_REPLY_CHANCE = 15

# Per-user cooldown in seconds
COOLDOWN_SECONDS = 4

# Track last reply times per user {user_id: timestamp}
_last_reply: dict[int, float] = {}


def _on_cooldown(user_id: int) -> bool:
    now = time.time()
    last = _last_reply.get(user_id, 0)
    return (now - last) < COOLDOWN_SECONDS


def _mark_used(user_id: int):
    _last_reply[user_id] = time.time()


class ChatCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore own messages
        if message.author == self.bot.user:
            return

        # Ignore DMs
        if not message.guild:
            return

        content = message.content.strip()
        channel_id = message.channel.id
        user_id = message.author.id
        username = message.author.display_name

        admin = _is_admin(message.author)

        # Check for trigger words: serv, servent, servant
        trigger_match = re.search(r'\b(serv|servan?t)\b', content, re.IGNORECASE)

        # Check if the bot was mentioned
        mentioned = self.bot.user in message.mentions

        # Build prompt — if replying to another message, include that context
        async def build_prompt(base_text: str) -> str:
            if message.reference and message.reference.resolved:
                ref = message.reference.resolved
                if isinstance(ref, discord.Message) and ref.content:
                    return f"[replying to {ref.author.display_name}: \"{ref.content}\"]\n{base_text}"
            elif message.reference:
                try:
                    ref = await message.channel.fetch_message(message.reference.message_id)
                    if ref.content:
                        return f"[replying to {ref.author.display_name}: \"{ref.content}\"]\n{base_text}"
                except Exception:
                    pass
            return base_text

        if trigger_match:
            prompt = await build_prompt(content)
            if _on_cooldown(user_id):
                return
            _mark_used(user_id)
            await self._reply(message, prompt, username, channel_id, is_admin=admin, force=True)
            return

        clean_content = re.sub(r'<@!?\d+>', '', content).strip() if mentioned else content
        if mentioned:
            if not clean_content:
                clean_content = "hey"
            prompt = await build_prompt(clean_content)
            if _on_cooldown(user_id):
                try:
                    await message.add_reaction("⏳")
                except (discord.Forbidden, discord.HTTPException):
                    pass
                return
            _mark_used(user_id)
            await self._reply(message, prompt, username, channel_id, is_admin=admin)
            return

        # Random chance to chime in on non-mention messages
        if random.randint(1, RANDOM_REPLY_CHANCE) == 1:
            if _on_cooldown(user_id):
                return
            _mark_used(user_id)
            await self._reply(message, content, username, channel_id, is_admin=admin)

    async def _reply(
        self,
        message: discord.Message,
        user_text: str,
        username: str,
        channel_id: int,
        is_admin: bool = False,
        force: bool = False,
    ):
        try:
            async with message.channel.typing():
                history = history_manager.get_messages(channel_id)
                response = await get_ai_response(history, f"{username}: {user_text}", is_admin=is_admin)
        except (discord.Forbidden, discord.HTTPException) as e:
            import logging
            logging.getLogger("bot").warning(f"Missing permission to type/reply in channel {channel_id}: {e}")
            return

        # Save to history
        history_manager.add(channel_id, "user", user_text, username)
        history_manager.add(channel_id, "assistant", response)

        try:
            await message.reply(response, mention_author=False)
        except (discord.Forbidden, discord.HTTPException) as e:
            import logging
            logging.getLogger("bot").warning(f"Failed to send reply in channel {channel_id}: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(ChatCog(bot))
