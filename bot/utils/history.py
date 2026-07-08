"""
Conversation history manager — keeps per-channel rolling context.
"""
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import List, Dict

MAX_HISTORY = 20  # messages kept per channel


@dataclass
class Message:
    role: str   # "user" or "assistant"
    content: str
    username: str = ""


class HistoryManager:
    def __init__(self, max_messages: int = MAX_HISTORY):
        self.max_messages = max_messages
        self._history: Dict[int, deque] = defaultdict(lambda: deque(maxlen=max_messages))

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


history_manager = HistoryManager()
