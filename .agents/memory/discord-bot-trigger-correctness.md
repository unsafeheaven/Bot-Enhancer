---
name: Discord bot on_message trigger correctness
description: Common pitfalls in discord.py on_message handlers that cause missed or duplicated bot triggers.
---

Two correctness pitfalls found in a discord.py `on_message` handler that decides whether to respond:

1. **`message.reference.resolved` is often `None`** even for genuine replies, because discord.py only populates it from the local message cache. Checking only `message.reference.resolved` to detect "this message replies to me" silently misses valid replies. Resolve once per message: use `message.reference.resolved` if it's already a `discord.Message`, otherwise fall back to `await message.channel.fetch_message(message.reference.message_id)` wrapped in try/except. Reuse that single resolved object for both trigger detection and prompt-building context instead of resolving twice.

2. **Filtering only `message.author == self.bot.user`** ignores messages from *other* bots and webhooks. If the bot's trigger word/mention logic can match another bot's message, this creates feedback loops or wasted API spend. Filter on `message.author.bot` instead, which excludes all bots including the bot itself.

**Why:** both bugs were caught by a code-review subagent pass on a first-build Discord bot, not by manual testing — the failure mode (missed replies, other-bot feedback loops) doesn't show up until specific runtime conditions happen (uncached messages, other bots present in the server).

**How to apply:** whenever writing a discord.py `on_message` trigger that reacts to replies, always resolve via cache-then-fetch, and always filter `author.bot` rather than a specific user-equality check.
