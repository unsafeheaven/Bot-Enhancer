"""
Conversation history + lightweight per-user memory manager.
"""
import random
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

from utils.storage import load, save

MAX_HISTORY = 20  # messages kept per channel
MAX_JOKES_PER_CHANNEL = 15  # capped inside-joke callbacks kept per channel


@dataclass
class Message:
    role: str   # "user" or "assistant"
    content: str
    username: str = ""


# Simple patterns for auto-remembering things people mention about themselves.
# Keyed by the fact label we store, matched loosely so it fires naturally in chat.
_FACT_PATTERNS = {
    "favorite song": re.compile(r"\bfavou?rite song(?:'s| is|:)?\s+(.+)", re.IGNORECASE),
    "favorite artist": re.compile(r"\bfavou?rite artist(?:'s| is|:)?\s+(.+)", re.IGNORECASE),
    "favorite game": re.compile(r"\bfavou?rite game(?:'s| is|:)?\s+(.+)", re.IGNORECASE),
    "nickname": re.compile(r"\bcall me\s+(.+)", re.IGNORECASE),
    "birthday": re.compile(r"\bmy birthday(?:'s| is)?\s+(.+)", re.IGNORECASE),
    "pet": re.compile(r"\bmy (?:dog|cat|pet)(?:'s| is)? (?:named|called)\s+(.+)", re.IGNORECASE),
}


def extract_facts(text: str) -> Dict[str, str]:
    found = {}
    for label, pattern in _FACT_PATTERNS.items():
        match = pattern.search(text)
        if match:
            value = match.group(1).strip().rstrip(".!?").strip()
            if value:
                found[label] = value[:80]
    return found


class HistoryManager:
    def __init__(self, max_messages: int = MAX_HISTORY):
        self.max_messages = max_messages
        self._history: Dict[int, deque] = defaultdict(lambda: deque(maxlen=max_messages))
        # Facts persist across restarts — real long-term memory, not just in-process state.
        # Coerce defensively: corrupt/malformed entries are dropped instead of crashing startup.
        persisted_facts = load("user_facts", {})
        clean_facts: Dict[int, Dict[str, str]] = {}
        if isinstance(persisted_facts, dict):
            for uid, facts in persisted_facts.items():
                try:
                    uid_int = int(uid)
                except (TypeError, ValueError):
                    continue
                if isinstance(facts, dict):
                    clean_facts[uid_int] = {str(k): str(v) for k, v in facts.items()}
        self._user_facts: Dict[int, Dict[str, str]] = defaultdict(dict, clean_facts)

        # Inside jokes/callbacks per channel, also persisted long-term.
        persisted_jokes = load("channel_jokes", {})
        clean_jokes: Dict[int, list] = {}
        if isinstance(persisted_jokes, dict):
            for cid, jokes in persisted_jokes.items():
                try:
                    cid_int = int(cid)
                except (TypeError, ValueError):
                    continue
                if isinstance(jokes, list):
                    valid = [
                        j for j in jokes
                        if isinstance(j, dict) and isinstance(j.get("text"), str) and isinstance(j.get("author"), str)
                    ]
                    if valid:
                        clean_jokes[cid_int] = valid
        self._channel_jokes: Dict[int, list] = defaultdict(list, clean_jokes)

    def _save_facts(self):
        save("user_facts", {str(uid): facts for uid, facts in self._user_facts.items()})

    def _save_jokes(self):
        save("channel_jokes", {str(cid): jokes for cid, jokes in self._channel_jokes.items()})

    def add(self, channel_id: int, role: str, content: str, username: str = ""):
        self._history[channel_id].append(Message(role=role, content=content, username=username))

    def get_messages(self, channel_id: int) -> List[Dict]:
        """Return OpenAI-formatted message list for a channel."""
        messages = []
        for msg in self._history[channel_id]:
            if msg.role == "user":
                content = f"{msg.username}: {msg.content}" if msg.username else msg.content
            else:
                content = msg.content
            messages.append({"role": msg.role, "content": content})
        return messages

    def clear(self, channel_id: int):
        self._history[channel_id].clear()

    def remember(self, user_id: int, text: str):
        """Scan a message for memorable facts and store them for this user, long-term."""
        facts = extract_facts(text)
        if facts:
            self._user_facts[user_id].update(facts)
            self._save_facts()

    def get_facts(self, user_id: int) -> Dict[str, str]:
        return dict(self._user_facts.get(user_id, {}))

    def clear_facts(self, user_id: int):
        self._user_facts.pop(user_id, None)
        self._save_facts()

    def remember_joke(self, channel_id: int, text: str, author: str):
        """Store a memorable line (one that got a big reaction) as a long-term inside joke."""
        jokes = self._channel_jokes[channel_id]
        if any(j["text"] == text for j in jokes):
            return
        jokes.append({"text": text[:200], "author": author})
        if len(jokes) > MAX_JOKES_PER_CHANNEL:
            del jokes[0]
        self._save_jokes()

    def get_random_joke(self, channel_id: int) -> Optional[Tuple[str, str]]:
        jokes = self._channel_jokes.get(channel_id) or []
        if not jokes:
            return None
        joke = random.choice(jokes)
        return joke["text"], joke["author"]


history_manager = HistoryManager()
