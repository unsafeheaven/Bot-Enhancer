"""
Conversation history + lightweight per-user memory manager.
"""
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import List, Dict

MAX_HISTORY = 20  # messages kept per channel


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
        self._user_facts: Dict[int, Dict[str, str]] = defaultdict(dict)

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
        """Scan a message for memorable facts and store them for this user."""
        facts = extract_facts(text)
        if facts:
            self._user_facts[user_id].update(facts)

    def get_facts(self, user_id: int) -> Dict[str, str]:
        return dict(self._user_facts.get(user_id, {}))

    def clear_facts(self, user_id: int):
        self._user_facts.pop(user_id, None)


history_manager = HistoryManager()
