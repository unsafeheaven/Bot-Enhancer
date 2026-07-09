"""
Chat cog — handles message events, Rin's "called" trigger, photo reactions, and random chime-ins.
"""
import asyncio
import random
import time
import re
import discord
from discord.ext import commands, tasks

from utils.ai import get_ai_response
from utils.history import history_manager
from utils.mood import get_energy
from utils.server_context import get_top_messages, get_random_members

# Chance the bot randomly chimes in on a message (1 in N) — her baseline; actual chance
# also scales down a bit when her energy is high (see _current_random_reply_chance).
RANDOM_REPLY_CHANCE = 15

# Per-user cooldown in seconds
COOLDOWN_SECONDS = 4

# Track last reply times per user {user_id: timestamp}
_last_reply: dict[int, float] = {}

# Image types that trigger "photo mode"
_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")

# Her reaction emoji set — restricted to her allowed emojis only; she uses emoji rarely.
_CALLED_REACTIONS = ["😭", "💔", "😟"]
_RANDOM_REACTIONS = ["😭", "💔", "😟"]

# Chance she also drops a reaction emoji (independent of the text reply) — kept low
# since she uses emoji sparingly, usually not at all.
CALLED_REACTION_CHANCE = 0.2
RANDOM_REACTION_CHANCE = 0.1

# Emojis that, in enough numbers on someone's message, mark it as a "moment" worth
# remembering as a long-term inside joke.
_JOKE_TRIGGER_EMOJIS = {"😂", "💀", "🔥", "😭"}
_JOKE_MIN_REACTION_COUNT = 3

# Typing feels human when it scales with reply length instead of being instant.
_TYPING_CHARS_PER_SECOND = 18
_TYPING_MIN_DELAY = 0.4
_TYPING_MAX_DELAY = 3.5

# "Left on read" — if she replied to someone and they vanish for a while before
# talking to her again, she can call it out next time.
LEFT_ON_READ_MIN_SECONDS = 20 * 60
LEFT_ON_READ_CHANCE = 0.35
_last_bot_reply_to_user: dict[int, float] = {}

# Proactive check-ins — if a channel she's talked in goes quiet, she'll sometimes
# say something unprompted to restart the conversation.
_last_channel_activity: dict[int, float] = {}
_last_proactive_checkin: dict[int, float] = {}
PROACTIVE_CHECK_INTERVAL_MINUTES = 10
PROACTIVE_QUIET_MINUTES = 20
PROACTIVE_STALE_MINUTES = 120  # beyond this, don't necropost — too much time has passed
PROACTIVE_COOLDOWN_MINUTES = 90
PROACTIVE_CHANCE = 0.25


def _current_random_reply_chance() -> int:
    """Higher energy = a bit more talkative (lower denominator = more likely)."""
    energy = get_energy()
    return max(6, RANDOM_REPLY_CHANCE - energy // 15)


def _check_left_on_read(user_id: int) -> bool:
    last = _last_bot_reply_to_user.get(user_id)
    if last is None:
        return False
    gap = time.time() - last
    return gap >= LEFT_ON_READ_MIN_SECONDS and random.random() < LEFT_ON_READ_CHANCE


async def _maybe_react(message: discord.Message, pool: list[str], chance: float):
    if random.random() > chance:
        return
    try:
        await message.add_reaction(random.choice(pool))
    except (discord.Forbidden, discord.HTTPException):
        pass


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
        self._proactive_checkin_loop.start()

    def cog_unload(self):
        self._proactive_checkin_loop.cancel()

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.abc.User):
        """Capture messages that blow up with reactions as long-term inside jokes."""
        if str(reaction.emoji) not in _JOKE_TRIGGER_EMOJIS:
            return
        if reaction.count < _JOKE_MIN_REACTION_COUNT:
            return
        target = reaction.message
        if target.author.bot or not target.content:
            return
        history_manager.remember_joke(target.channel.id, target.content, target.author.display_name)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore ourselves and any other bots/webhooks (avoid feedback loops)
        if message.author.bot:
            return

        # Ignore DMs
        if not message.guild:
            return

        _last_channel_activity[message.channel.id] = time.time()

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

        # Strip the mention/name so command phrasing can be matched cleanly
        # regardless of whether she was @mentioned or called by name.
        stripped_content = re.sub(r"<@!?\d+>", "", content).strip()
        stripped_content = re.sub(r"\brin\b", "", stripped_content, flags=re.IGNORECASE).strip()

        # Special requests only fire when she's actually being talked to, and only
        # when phrased as an actual command (not casual conversation that happens
        # to mention "rate" or "top messages").
        rate_match = re.search(
            r"^\s*rate\s+(\d{1,2})\s*(?:people|guys|folks|members|friends)\s*$",
            stripped_content, re.IGNORECASE,
        ) if called else None
        top_match = re.search(
            r"^\s*(?:show|give|what(?:'?s| is)|send)?\s*(?:me\s+)?(?:the\s+)?top\s*(\d{1,2})?\s*messages?\s*$",
            stripped_content, re.IGNORECASE,
        ) if called else None

        if rate_match and _on_cooldown(user_id):
            return
        if rate_match:
            _mark_used(user_id)
            history_manager.remember(user_id, content)
            await self._rate_people(message, int(rate_match.group(1)))
            return

        if top_match and _on_cooldown(user_id):
            return
        if top_match:
            _mark_used(user_id)
            history_manager.remember(user_id, content)
            count = int(top_match.group(1)) if top_match.group(1) else 5
            await self._talk_top_messages(message, count)
            return

        # Build prompt — if replying to another (non-Rin) message, include that context
        async def build_prompt(base_text: str) -> str:
            if resolved_ref is not None and resolved_ref.content and resolved_ref.author != self.bot.user:
                return f"[replying to {resolved_ref.author.display_name}: \"{resolved_ref.content}\"]\n{base_text}"
            return base_text

        if called or photo_mode:
            clean_content = stripped_content
            if not clean_content:
                clean_content = "[posted an image]" if photo_mode else ""

            # If she was just called with little/no content (e.g. "rin" after "hey"),
            # look back one message from the same user and stitch it in so she has context.
            if called and not photo_mode and len(clean_content) < 3:
                try:
                    prev_msgs = [m async for m in message.channel.history(limit=2, before=message)]
                    if prev_msgs:
                        prev = prev_msgs[0]
                        age = (message.created_at - prev.created_at).total_seconds()
                        if (
                            prev.author.id == user_id
                            and not prev.author.bot
                            and age < 180
                            and prev.content
                        ):
                            clean_content = (prev.content + (" " + clean_content if clean_content else "")).strip()
                except (discord.Forbidden, discord.HTTPException):
                    pass

            if not clean_content:
                clean_content = "hey"

            if _on_cooldown(user_id):
                try:
                    await message.add_reaction("😭")
                except (discord.Forbidden, discord.HTTPException):
                    pass
                return

            left_on_read = _check_left_on_read(user_id) if called else False
            _mark_used(user_id)
            _last_bot_reply_to_user[user_id] = time.time()
            await _maybe_react(message, _CALLED_REACTIONS, CALLED_REACTION_CHANCE)
            prompt = await build_prompt(clean_content)
            history_manager.remember(user_id, content)
            joke = history_manager.get_random_joke(channel_id) if random.random() < 0.15 else None
            await self._reply(
                message, prompt, username, channel_id, user_id,
                photo_mode=photo_mode, joke=joke, left_on_read=left_on_read,
            )
            return

        # Random chance to chime in on regular chatter — she's talkative
        # (a bit more so when her energy is high today)
        if random.randint(1, _current_random_reply_chance()) == 1:
            if _on_cooldown(user_id):
                return
            _mark_used(user_id)
            await _maybe_react(message, _RANDOM_REACTIONS, RANDOM_REACTION_CHANCE)
            history_manager.remember(user_id, content)
            await self._reply(message, content, username, channel_id, user_id)

    async def _rate_people(self, message: discord.Message, count: int):
        count = max(1, min(count, 10))
        try:
            members = await get_random_members(message.guild, count)
        except discord.Forbidden:
            # Members intent likely isn't enabled in the dev portal — degrade gracefully.
            try:
                await message.reply(
                    "can't see everyone in here yet, someone needs to flip on the members intent for me 😟",
                    mention_author=False,
                )
            except (discord.Forbidden, discord.HTTPException):
                pass
            return

        if not members:
            try:
                await message.reply("bro there's literally no one else here to rate 😭", mention_author=False)
            except (discord.Forbidden, discord.HTTPException):
                pass
            return

        names = ", ".join(m.display_name for m in members)
        prompt = (
            f"rate these {len(members)} server members 1-10 each, one short savage-but-playful line per "
            f"person, never about appearance, keep it teasing not genuinely mean: {names}"
        )
        await self._reply(message, prompt, message.author.display_name, message.channel.id, message.author.id)

    async def _talk_top_messages(self, message: discord.Message, count: int):
        count = max(1, min(count, 5))
        try:
            top = await get_top_messages(message.channel, top_n=count)
        except (discord.Forbidden, discord.HTTPException):
            top = []

        if not top:
            try:
                await message.reply("nothing's popping off in here rn 💔 chat is mid", mention_author=False)
            except (discord.Forbidden, discord.HTTPException):
                pass
            return

        lines = [
            f'{msg.author.display_name}: "{msg.content}" ({reactions} reactions)'
            for msg, reactions in top
        ]
        prompt = (
            "here are the top messages in this channel right now by reaction count — react to them "
            "and call out your favorite:\n" + "\n".join(lines)
        )
        await self._reply(message, prompt, message.author.display_name, message.channel.id, message.author.id)

    async def _reply(
        self,
        message: discord.Message,
        user_text: str,
        username: str,
        channel_id: int,
        user_id: int,
        photo_mode: bool = False,
        joke: tuple[str, str] | None = None,
        left_on_read: bool = False,
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
                    joke=joke,
                    left_on_read=left_on_read,
                )
                # Scale the typing delay to reply length so it feels like a real
                # person typing rather than an instant bot response.
                delay = min(_TYPING_MAX_DELAY, max(_TYPING_MIN_DELAY, len(response) / _TYPING_CHARS_PER_SECOND))
                await asyncio.sleep(delay)
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

    @tasks.loop(minutes=PROACTIVE_CHECK_INTERVAL_MINUTES)
    async def _proactive_checkin_loop(self):
        now = time.time()
        for channel_id, last_active in list(_last_channel_activity.items()):
            quiet_for = now - last_active
            if quiet_for < PROACTIVE_QUIET_MINUTES * 60 or quiet_for > PROACTIVE_STALE_MINUTES * 60:
                continue
            if now - _last_proactive_checkin.get(channel_id, 0) < PROACTIVE_COOLDOWN_MINUTES * 60:
                continue
            if random.random() > PROACTIVE_CHANCE:
                continue
            history = history_manager.get_messages(channel_id)
            if not history:
                continue  # she's never actually talked here — don't start randomly
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                continue

            _last_proactive_checkin[channel_id] = now
            try:
                async with channel.typing():
                    prompt = (
                        "it's been quiet in here for a while — say something short and casual, in "
                        "character, to restart the conversation. don't mention that it's been quiet "
                        "in a robotic/meta way."
                    )
                    response = await get_ai_response(history, prompt)
                    await asyncio.sleep(min(_TYPING_MAX_DELAY, max(_TYPING_MIN_DELAY, len(response) / _TYPING_CHARS_PER_SECOND)))
                history_manager.add(channel_id, "assistant", response)
                await channel.send(response)
                _last_channel_activity[channel_id] = time.time()
            except (discord.Forbidden, discord.HTTPException):
                pass

    @_proactive_checkin_loop.before_loop
    async def _before_proactive_checkin(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(ChatCog(bot))
