# Discord AI Chatbot

A chill Gen Z Discord bot powered by GPT-4o-mini.

## Setup

### 1. Discord Bot Token
1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Create a new Application → Bot
3. Enable **Message Content Intent** under Bot → Privileged Gateway Intents
4. Copy the token and add it as `DISCORD_TOKEN` in Replit Secrets

### 2. OpenRouter API Key
1. Go to [openrouter.ai/keys](https://openrouter.ai/keys)
2. Create a key and add it as `OPENROUTER_API_KEY` in Replit Secrets

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

## Deploying on Railway

This folder is ready to deploy standalone on [Railway](https://railway.app):

1. Push this `bot/` folder to a GitHub repo (or use `railway up` from inside it with the Railway CLI).
2. In Railway, create a new project → **Deploy from GitHub repo** (or `railway init` + `railway up` if using the CLI), pointing at this folder as the root.
3. Railway auto-detects it as a Python app via `requirements.txt` and `railway.json`/`Procfile` (worker process, no web port needed).
4. In the Railway project's **Variables** tab, add:
   - `DISCORD_TOKEN`
   - `OPENROUTER_API_KEY` (or `CEREBRAS_API_KEY`/`GROQ_API_KEY` if you've switched providers in `utils/ai.py`)
5. Deploy. Railway will run `python main.py` as a background worker — check the **Deployments → Logs** tab to confirm it logs in successfully.

**Note:** never paste API keys or tokens directly into chat, README files, or commits — always add them through Railway's Variables tab (or Replit Secrets when running here).

## Features

| Feature | Description |
|---|---|
| `@mention` | Mention the bot to chat with it |
| `servent <prompt>` | Say "servent" anywhere + your message |
| `/ask <prompt>` | Direct slash command |
| `/roast [@user]` | Get roasted |
| `/vibe` | Vibe check the chat |
| `/reset` | Clear bot memory for the channel |
| Random replies | Bot randomly chimes in (1 in 15 chance) |

## Personality

Talks like a chill 2026 TikTok/Instagram commenter. Dry humor, Gen Z slang, short replies (3–20 words), rarely uses punctuation, 0–2 emojis per message.
