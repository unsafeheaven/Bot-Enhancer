"""
Chat cog — message events, triggers, photo reactions, random chime-ins,
proactive check-ins, song drops, and member welcome.
"""
import asyncio
import random
import time
import re
import discord
from discord.ext import commands, tasks

from utils.ai import get_ai_response, get_random_song_drop
from utils.history import history_manager
from utils.mood import get_energy
from utils.server_context import get_top_messages, get_random_members

# Chance the bot randomly chimes in on a message (1 in N)
RANDOM_REPLY_CHANCE = 15

# Per-user cooldown in seconds
COOLDOWN_SECONDS = 4

_last_reply: dict[int, float] = {}

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")

_CALLED_REACTIONS = ["😭", "💔", "😟"]
_RANDOM_REACTIONS = ["😭", "💔", "😟"]

CALLED_REACTION_CHANCE = 0.2
RANDOM_REACTION_CHANCE = 0.1

_JOKE_TRIGGER_EMOJIS = {"😂", "💀", "🔥", "😭"}
_JOKE_MIN_REACTION_COUNT = 3

_TYPING_CHARS_PER_SECOND = 18
_TYPING_MIN_DELAY = 0.4
_TYPING_MAX_DELAY = 3.5

LEFT_ON_READ_MIN_SECONDS = 20 * 60
LEFT_ON_READ_CHANCE = 0.35
_last_bot_reply_to_user: dict[int, float] = {}

_last_channel_activity: dict[int, float] = {}
_last_proactive_checkin: dict[int, float] = {}
PROACTIVE_CHECK_INTERVAL_MINUTES = 10
PROACTIVE_QUIET_MINUTES = 20
PROACTIVE_STALE_MINUTES = 120
PROACTIVE_COOLDOWN_MINUTES = 90
PROACTIVE_CHANCE = 0.25

# Song drop — she randomly shares a song she's "listening to"
SONG_DROP_INTERVAL_MINUTES = 45
SONG_DROP_CHANCE = 0.18


def _current_random_reply_chance() -> int:
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
    return (time.time() - _last_reply.get(user_id, 0)) < COOLDOWN_SECONDS


def _mark_used(user_id: int):
    _last_reply[user_id] = time.time()


def _has_image(message: discord.Message) -> bool:
    for att in message.attachments:
        if att.content_type and att.content_type.startswith("image/"):
            return True
        if att.filename.lower().endswith(_IMAGE_EXTS):
            return True
    return False


def _try_split(text: str) -> list[str]:
    """
    Attempt to split a reply into 2 natural parts.
    Only applies to longer replies and only sometimes.
    Returns a single-element list if not splitting.
    """
    if len(text) < 90 or random.random() > 0.30:
        return [text]

    search_start = len(text) // 5
    search_end = 4 * len(text) // 5
    mid = len(text) // 2

    best_pos = -1
    # Try separators in priority order
    for sep in (". ", "! ", "? ", "... ", " — ", ".. "):
        pos = text.find(sep, search_start, search_end)
        if pos != -1:
            candidate = pos + len(sep.rstrip())
            if best_pos == -1 or abs(candidate - mid) < abs(best_pos - mid):
                best_pos = candidate

    if best_pos == -1:
        return [text]

    part1 = text[:best_pos].strip()
    part2 = text[best_pos:].strip()
    if not part1 or not part2:
        return [text]
    return [part1, part2]


class ChatCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._proactive_checkin_loop.start()
        self._song_drop_loop.start()

    def cog_unload(self):
        self._proactive_checkin_loop.cancel()
        self._song_drop_loop.cancel()

    # ── listeners ─────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Welcome new members in-character."""
        if member.bot:
            return
        channel = member.guild.system_channel
        if channel is None:
            # Fall back to first text channel she can send in
            for ch in member.guild.text_channels:
                perms = ch.permissions_for(member.guild.me)
                if perms.send_messages:
                    channel = ch
                    break
        if channel is None:
            return

        greetings = [
            f"oh wait {member.display_name} actually joined lol, hey",
            f"wait {member.display_name} is here now? hi 👀 jk no emojis, but hi",
            f"oh {member.display_name} showed up, wsg",
            f"hey {member.display_name}, took u long enough",
            f"{member.display_name} just joined.. say hi to them or smth",
            f"okay {member.display_name} is here, we can start",
        ]
        try:
            await channel.send(random.choice(greetings).replace("👀", ""))
        except (discord.Forbidden, discord.HTTPException):
            pass

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.abc.User):
        """Capture messages that blow up with reactions as long-term inside jokes."""
        if user.bot:
            return
        if str(reaction.emoji) not in _JOKE_TRIGGER_EMOJIS:
            return
        # Count only non-bot reactions to avoid threshold skew from the bot itself
        non_bot_count = sum(
            1 async for u in reaction.users() if not u.bot
        ) if reaction.count >= _JOKE_MIN_REACTION_COUNT else 0
        if non_bot_count < _JOKE_MIN_REACTION_COUNT:
            return
        target = reaction.message
        if target.author.bot or not target.content:
            return
        history_manager.remember_joke(target.channel.id, target.content, target.author.display_name)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild:
            return

        _last_channel_activity[message.channel.id] = time.time()

        content = message.content.strip()
        channel_id = message.channel.id
        user_id = message.author.id
        username = message.author.display_name

        # Resolve the referenced message
        resolved_ref: discord.Message | None = None
        if message.reference:
            if isinstance(message.reference.resolved, discord.Message):
                resolved_ref = message.reference.resolved
            elif message.reference.message_id:
                try:
                    resolved_ref = await message.channel.fetch_message(message.reference.message_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    resolved_ref = None

        name_called = re.search(r"\brin\b", content, re.IGNORECASE) is not None
        mentioned = self.bot.user in message.mentions
        replied_to_her = resolved_ref is not None and resolved_ref.author == self.bot.user

        called = name_called or mentioned or replied_to_her
        photo_mode = _has_image(message)

        stripped_content = re.sub(r"<@!?\d+>", "", content).strip()
        stripped_content = re.sub(r"\brin\b", "", stripped_content, flags=re.IGNORECASE).strip()

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

        async def build_prompt(base_text: str) -> str:
            if resolved_ref is not None and resolved_ref.content and resolved_ref.author != self.bot.user:
                return f"[replying to {resolved_ref.author.display_name}: \"{resolved_ref.content}\"]\n{base_text}"
            return base_text

        if called or photo_mode:
            clean_content = stripped_content
            if not clean_content:
                clean_content = "[posted an image]" if photo_mode else ""

            # If she was just called with little/no content (e.g. "rin" after "hey"),
            # look back one message from the same user and stitch it in.
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

            # Interaction tracking — bump and get relationship context
            is_first_today, streak = history_manager.bump_interaction(user_id)
            interaction_count = history_manager.get_interaction_count(user_id)

            left_on_read = _check_left_on_read(user_id) if called else False
            _mark_used(user_id)
            _last_bot_reply_to_user[user_id] = time.time()
            await _maybe_react(message, _CALLED_REACTIONS, CALLED_REACTION_CHANCE)
            prompt = await build_prompt(clean_content)
            history_manager.remember(user_id, content)
            joke = history_manager.get_random_joke(channel_id) if random.random() < 0.15 else None
            await self._reply(
                message, prompt, username, channel_id, user_id,
                photo_mode=photo_mode,
                joke=joke,
                left_on_read=left_on_read,
                interaction_count=interaction_count,
                is_first_today=is_first_today,
                streak=streak,
            )
            return

        # Random chime-in
        if random.randint(1, _current_random_reply_chance()) == 1:
            if _on_cooldown(user_id):
                return
            is_first_today, streak = history_manager.bump_interaction(user_id)
            interaction_count = history_manager.get_interaction_count(user_id)
            _mark_used(user_id)
            await _maybe_react(message, _RANDOM_REACTIONS, RANDOM_REACTION_CHANCE)
            history_manager.remember(user_id, content)
            await self._reply(
                message, content, username, channel_id, user_id,
                interaction_count=interaction_count,
                is_first_today=is_first_today,
                streak=streak,
            )

    # ── reply delivery ────────────────────────────────────────────────────────

    async def _deliver(self, message: discord.Message, response: str, channel_id: int):
        """
        Send the response — sometimes with a '...' lead-in, sometimes split into
        two messages, to feel more like real texting.
        """
        # Occasionally send a "..." first (thinking beat) for longer replies
        if len(response) > 80 and random.random() < 0.12:
            try:
                await message.reply("...", mention_author=False)
            except (discord.Forbidden, discord.HTTPException):
                pass
            await asyncio.sleep(random.uniform(1.2, 2.2))

        parts = _try_split(response)

        if len(parts) == 2:
            try:
                await message.reply(parts[0], mention_author=False)
            except (discord.Forbidden, discord.HTTPException) as e:
                import logging
                logging.getLogger("bot").warning(f"Failed to send part 1 in {channel_id}: {e}")
                return
            await asyncio.sleep(random.uniform(0.7, 1.6))
            try:
                await message.channel.send(parts[1])
            except (discord.Forbidden, discord.HTTPException) as e:
                import logging
                logging.getLogger("bot").warning(f"Failed to send part 2 in {channel_id}: {e}")
        else:
            try:
                await message.reply(response, mention_author=False)
            except (discord.Forbidden, discord.HTTPException) as e:
                import logging
                logging.getLogger("bot").warning(f"Failed to send reply in {channel_id}: {e}")

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
        interaction_count: int = 0,
        is_first_today: bool = False,
        streak: int = 0,
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
                    interaction_count=interaction_count,
                    is_first_today=is_first_today,
                    streak=streak,
                )
                delay = min(_TYPING_MAX_DELAY, max(_TYPING_MIN_DELAY, len(response) / _TYPING_CHARS_PER_SECOND))
                await asyncio.sleep(delay)
        except (discord.Forbidden, discord.HTTPException) as e:
            import logging
            logging.getLogger("bot").warning(f"Missing permission to type in channel {channel_id}: {e}")
            return

        history_manager.add(channel_id, "user", user_text, username)
        history_manager.add(channel_id, "assistant", response)

        await self._deliver(message, response, channel_id)

    # ── commands ──────────────────────────────────────────────────────────────

    async def _rate_people(self, message: discord.Message, count: int):
        count = max(1, min(count, 10))
        try:
            members = await get_random_members(message.guild, count)
        except discord.Forbidden:
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

    # ── background loops ──────────────────────────────────────────────────────

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
                continue
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                continue

            _last_proactive_checkin[channel_id] = now
            try:
                async with channel.typing():
                    prompt = (
                        "it's been quiet in here for a while — say something short and casual, in "
                        "character, to restart the conversation. don't mention that it's been quiet "
                        "in a robotic or meta way."
                    )
                    response = await get_ai_response(history, prompt)
                    delay = min(_TYPING_MAX_DELAY, max(_TYPING_MIN_DELAY, len(response) / _TYPING_CHARS_PER_SECOND))
                    await asyncio.sleep(delay)
                history_manager.add(channel_id, "assistant", response)
                await channel.send(response)
                _last_channel_activity[channel_id] = time.time()
            except (discord.Forbidden, discord.HTTPException):
                pass
            except Exception as e:
                import logging
                logging.getLogger("bot").warning(f"Proactive check-in error in {channel_id}: {e}")

    @tasks.loop(minutes=SONG_DROP_INTERVAL_MINUTES)
    async def _song_drop_loop(self):
        """Randomly drop a song she's 'listening to' in an active channel."""
        if random.random() > SONG_DROP_CHANCE:
            return

        now = time.time()
        # Pre-filter: active within 3 hours AND quiet for at least 5 minutes
        candidates = [
            cid for cid, last in _last_channel_activity.items()
            if 5 * 60 <= now - last < 3 * 3600
        ]
        if not candidates:
            return

        channel_id = random.choice(candidates)
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            return

        drop = get_random_song_drop()
        try:
            await channel.send(drop)
            _last_channel_activity[channel_id] = time.time()
        except (discord.Forbidden, discord.HTTPException):
            pass

    @_proactive_checkin_loop.before_loop
    async def _before_proactive(self):
        await self.bot.wait_until_ready()

    @_song_drop_loop.before_loop
    async def _before_song_drop(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(ChatCog(bot))
