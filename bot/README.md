# Rin — Discord Bot

An extremely-online gen z Discord bot with a real personality: energetic, playful, tsundere, music-obsessed, and talkative. Powered by an LLM via Cerebras.

## Setup

### 1. Discord Bot Token
1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Create a new Application → Bot
3. Enable **Message Content Intent** under Bot → Privileged Gateway Intents
4. Copy the token and add it as `DISCORD_TOKEN` in Replit Secrets

### 2. Cerebras API Key
1. Go to [cloud.cerebras.ai](https://cloud.cerebras.ai)
2. Create a key and add it as `CEREBRAS_API_KEY` in Replit Secrets

### 3. Invite the bot
Use this URL (replace `CLIENT_ID` with your app's client ID):
```
https://discord.com/api/oauth2/authorize?client_id=CLIENT_ID&permissions=274878024704&scope=bot%20applications.commands
```

Required permissions:
- Send Messages
- Read Message History
- Use Slash Commands
- Add Reactions

## Features

| Feature | Description |
|---|---|
| say "rin" anywhere | she's "called" — responds in character |
| `@mention` | mention her to chat |
| reply to her message | she'll pick the thread back up |
| post a picture | instant all-caps hype reaction, then back to normal |
| `/ask <prompt>` | direct slash command |
| `/roast [@user]` | playful roast, never mean |
| `/vibe` | vibe check the chat |
| `/reset` | clear her memory for the channel |
| `/forgetme` | clear what she remembers about you specifically |
| Random replies | she randomly chimes in (1 in 15 chance) — she's talkative |

## Provider

Rin runs on Cerebras (`gemma-4-31b`) via the OpenAI-compatible SDK pointed at `https://api.cerebras.ai/v1`. Needs `CEREBRAS_API_KEY` in Replit Secrets.

## Personality

Rin is not an assistant — she's an extremely online gen z best-friend type: playful, tsundere, slightly flirty (never explicit), music-obsessed, funny, a little chaotic, and genuinely caring when someone's actually upset. See `utils/ai.py` for the full personality spec.

She also remembers small things people tell her (favorite songs/artists/games, nicknames, birthdays, pets) per user and brings them up naturally later.
