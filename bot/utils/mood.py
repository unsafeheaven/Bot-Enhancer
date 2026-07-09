"""
Rin's persistent mood — a light daily mood roll plus an "energy" counter that
builds up with interaction, so she feels like she has good days and bad days
instead of being a static chatbot. Persisted so it survives restarts.
"""
import random
from datetime import date
from typing import Tuple

from utils.storage import load, save

_MOODS = [
    ("sleepy", "you're feeling a little sleepy/soft today, slower and mellower than usual, but still you"),
    ("hyped", "you're in a really good, hyped mood today — extra playful and talkative"),
    ("annoyed", "you're mildly cranky today, a bit more sarcastic than usual, but never actually mean"),
    ("soft", "you're feeling soft and affectionate today, more sincere and less guarded than usual"),
    ("normal", "you're just in your normal everyday mood today"),
    ("chaotic", "you're feeling extra unhinged/chaotic today, more brainrot energy than usual"),
]

_state = load("mood", {})


def _today() -> str:
    return date.today().isoformat()


def _ensure_today() -> dict:
    global _state
    if _state.get("date") != _today():
        name, descriptor = random.choice(_MOODS)
        _state = {
            "date": _today(),
            "mood": name,
            "descriptor": descriptor,
            "energy": _state.get("energy", 50),
        }
        save("mood", _state)
    return _state


def get_mood() -> Tuple[str, str]:
    """Return (mood_name, descriptor) for today, rolling a new mood at the start of each day."""
    state = _ensure_today()
    return state.get("mood", "normal"), state.get("descriptor", "")


def get_mood_descriptor() -> str:
    return get_mood()[1]


def get_energy() -> int:
    return _ensure_today().get("energy", 50)


def bump_energy(amount: int = 1):
    """Interactions nudge her energy up a little; call this after each real reply."""
    global _state
    state = _ensure_today()
    state["energy"] = min(100, state.get("energy", 50) + amount)
    _state = state
    save("mood", _state)
