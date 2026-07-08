# Rin — Discord Bot

A Discord bot named Rin with a real personality — energetic, playful, tsundere, music-obsessed gen z best friend — powered by an LLM via OpenRouter.

## Run & Operate

- `Discord Bot` workflow — runs `cd bot && python main.py`
- `pnpm --filter @workspace/api-server run dev` — run the API server (port 5000, unused by the bot; reserved for future web features)
- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- Required secrets: `DISCORD_TOKEN` (Discord bot token), `OPENROUTER_API_KEY` (OpenRouter API key)

## Stack

- Bot: Python 3.11, discord.py, openai SDK (pointed at OpenRouter), python-dotenv
- Model: `openai/gpt-oss-20b:free` via OpenRouter
- pnpm workspaces, Node.js 24, TypeScript 5.9 (for the API server / mockup sandbox, currently unused by the bot)

## Where things live

```
bot/
  main.py           — entry point, bot init, cog loading
  cogs/
    chat.py         — on_message handler, "called" trigger (name/@mention/reply), photo reactions, random chime-ins
    commands.py     — slash commands (/ask, /roast, /vibe, /reset, /forgetme, /help)
  utils/
    ai.py           — OpenRouter client wrapper + Rin's personality system prompt
    history.py      — per-channel in-memory conversation history + per-user remembered facts
  .env.example      — template for local dev
  README.md         — setup & invite instructions
```

`bot/` is a standalone Python app, not part of the pnpm workspace — it runs via its own `Discord Bot` workflow.

## Architecture decisions

- Single unified personality (Rin) — no admin/non-admin split, matches the product intent of one consistent character everywhere.
- Conversation history is in-memory per channel, capped at 20 messages — resets on restart (privacy/simplicity over persistence).
- Per-user "memory" (favorite songs/artists/games, nicknames, birthdays, pets) is also in-memory, extracted via lightweight regex from things people say, and injected into the system prompt so Rin can bring them up naturally.
- Triggers: saying "rin" anywhere, @mention, replying directly to one of her messages, posting an image (photo mode — all-caps hype reaction), "rate N people" (rates random real server members), "top N messages" (comments on the channel's most-reacted messages), slash commands, or a random 1-in-15 chance to chime in unprompted (she's talkative).
- Occasionally reacts with an emoji from her set (in addition to replying) when called/mentioned or on random chime-ins.
- Uses OpenRouter with the user's own API key (`OPENROUTER_API_KEY`) — Replit's AI Integrations proxy for OpenRouter required an account upgrade the user didn't want, so we fell back to a user-supplied key.

## Product

- Users chat with Rin by saying "rin", @mentioning her, replying to her, or via `/ask`.
- She reacts instantly (in all caps) whenever someone posts a picture, then goes back to normal.
- `/roast`, `/vibe`, `/reset`, `/forgetme`, `/help` slash commands.
- She occasionally chimes in unprompted to feel like an active, talkative member of the server.

## User preferences

_Populate as you build — explicit user instructions worth remembering across sessions._

## Gotchas

- Must enable **Message Content Intent** in the Discord Developer Portal or the bot can't read message text.
- Slash commands can take up to an hour to propagate globally on first sync (per-guild sync is instant).
- The "rin" name trigger uses a word-boundary regex, so it only fires on the standalone word "rin", not as a substring of other words.

## Pointers

- Bot invite URL template: `https://discord.com/api/oauth2/authorize?client_id=CLIENT_ID&permissions=274878024704&scope=bot%20applications.commands`
- See `bot/README.md` for full setup steps
- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details (applies to `artifacts/`, not `bot/`)
