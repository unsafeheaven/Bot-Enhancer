"""
Chat cog — handles message events, Rin's "called" trigger, photo reactions, and random chime-ins.
"""
import random
import time
import re
import discord
from discord.ext import commands

from utils.ai import get_ai_response
from utils.history import history_manager

# Chance the bot randomly chimes in on a message (1 in N)
RANDOM_REPLY_CHANCE = 15

# Per-user cooldown in seconds
COOLDOWN_SECONDS = 4

# Track last reply times per user {user_id: timestamp}
_last_reply: dict[int, float] = {}

# Image types that trigger "photo mode"
_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")


def _on_cooldown(user_id: int) -> bool:
    now = time.time()
    last = _last_reply.get(user_id, 0)
    return (now - last) < COOLDOWN_SECONDS


def _mark_used(user_id: int):
    _last_reply[user_id] = time.time()


def _has_image(message: discord.Message) -> bool:
    for att in message.attachments:
        if att.content_type and att.content_type.startswith("image/"):
            return True
        if att.filename.lower().endswith(_IMAGE_EXTS):
            return True
    return False


class ChatCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore ourselves and any other bots/webhooks (avoid feedback loops)
        if message.author.bot:
            return

        # Ignore DMs
        if not message.guild:
            return

        content = message.content.strip()
        channel_id = message.channel.id
        user_id = message.author.id
        username = message.author.display_name

        # Resolve the referenced message once (cache first, fetch as fallback)
        # so both trigger detection and prompt-building see the same thing.
        resolved_ref: discord.Message | None = None
        if message.reference:
            if isinstance(message.reference.resolved, discord.Message):
                resolved_ref = message.reference.resolved
            elif message.reference.message_id:
                try:
                    resolved_ref = await message.channel.fetch_message(message.reference.message_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    resolved_ref = None

        # She's "called" by name, @mentioned, or replied to directly
        name_called = re.search(r"\brin\b", content, re.IGNORECASE) is not None
        mentioned = self.bot.user in message.mentions
        replied_to_her = resolved_ref is not None and resolved_ref.author == self.bot.user

        called = name_called or mentioned or replied_to_her
        photo_mode = _has_image(message)

        # Build prompt — if replying to another (non-Rin) message, include that context
        async def build_prompt(base_text: str) -> str:
            if resolved_ref is not None and resolved_ref.content and resolved_ref.author != self.bot.user:
                return f"[replying to {resolved_ref.author.display_name}: \"{resolved_ref.content}\"]\n{base_text}"
            return base_text

        if called or photo_mode:
            clean_content = re.sub(r"<@!?\d+>", "", content).strip()
            clean_content = re.sub(r"\brin\b", "", clean_content, flags=re.IGNORECASE).strip()
            if not clean_content:
                clean_content = "[posted an image]" if photo_mode else "hey"

            if _on_cooldown(user_id):
                try:
                    await message.add_reaction("👀")
                except (discord.Forbidden, discord.HTTPException):
                    pass
                return

            _mark_used(user_id)
            prompt = await build_prompt(clean_content)
            history_manager.remember(user_id, content)
            await self._reply(message, prompt, username, channel_id, user_id, photo_mode=photo_mode)
            return

        # Random chance to chime in on regular chatter — she's talkative
        if random.randint(1, RANDOM_REPLY_CHANCE) == 1:
            if _on_cooldown(user_id):
                return
            _mark_used(user_id)
            history_manager.remember(user_id, content)
            await self._reply(message, content, username, channel_id, user_id)

    async def _reply(
        self,
        message: discord.Message,
        user_text: str,
        username: str,
        channel_id: int,
        user_id: int,
        photo_mode: bool = False,
    ):
        try:
            async with message.channel.typing():
                history = history_manager.get_messages(channel_id)
                facts = history_manager.get_facts(user_id)
                response = await get_ai_response(
                    history,
                    f"{username}: {user_text}",
                    photo_mode=photo_mode,
                    user_facts=facts,
                )
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
