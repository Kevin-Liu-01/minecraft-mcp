"""Classify and filter Minecraft chat messages by type.

Message types (mirroring bridge/server.mjs constants):
  - "player"  : message sent by another player
  - "system"  : server/game notification (death, achievement, join/leave, etc.)
  - "self"    : message sent by this bot
"""
from __future__ import annotations

MSG_TYPE_PLAYER = "player"
MSG_TYPE_SYSTEM = "system"
MSG_TYPE_SELF = "self"

GAME_NOTIFICATION_PATTERNS: tuple[str, ...] = (
    "Set own game mode to",
    "Gamerule ",
    "Killed ",
    " has made the advancement",
    " joined the game",
    " left the game",
    "Unable to open",
    "commands.give.success",
    "Teleported ",
    "Given ",
    " was killed",
    " was slain",
    " fell from",
    " drowned",
    " burned",
    " blew up",
    " hit the ground",
    " tried to swim",
    " suffocated",
    " starved",
    " withered away",
)

BOT_STATUS_TAGS: tuple[str, ...] = (
    "[On it!", "[Done!", "[Done:", "[Working on:",
    "[Finished:", "[Stopped:", "[Ran out", "[Got no", "[Error:",
)

BOT_MESSAGE_PREFIXES: tuple[str, ...] = (
    "On it!", "Done!", "Done:", "Working on:", "Finished:", "Stopped:", "Ran out of",
    "Got no response", "Error:", "I'm doing", "All done",
    "Moving to", "Mining ", "Placing ", "Pausing ", "Arrived", "Autonomous mode",
)


def is_game_notification(message: str) -> bool:
    """Return True if *message* looks like a Minecraft game notification."""
    stripped = message.strip()
    if not stripped:
        return False
    if stripped.endswith("]") and any(
        stripped.startswith(p) or p in stripped for p in GAME_NOTIFICATION_PATTERNS
    ):
        return True
    return any(stripped.startswith(p) for p in GAME_NOTIFICATION_PATTERNS)


def is_bot_like_message(message: str) -> bool:
    """Return True if *message* looks like it was sent by a bot (status/announcement)."""
    if not message:
        return True
    stripped = message.strip()
    if any(tag in stripped for tag in BOT_STATUS_TAGS):
        return True
    if is_game_notification(stripped):
        return True
    return stripped.startswith(BOT_MESSAGE_PREFIXES)


def classify_message(raw: dict) -> str:
    """Return the message type from a raw chat dict.

    Relies on the ``type`` field added by the bridge. Falls back to heuristic
    classification when the field is missing (backward compat).
    """
    explicit_type = raw.get("type", "")
    if explicit_type in (MSG_TYPE_PLAYER, MSG_TYPE_SYSTEM, MSG_TYPE_SELF):
        return explicit_type

    sender = (raw.get("sender") or raw.get("username") or "").strip()
    if sender == "server" or sender == "error":
        return MSG_TYPE_SYSTEM
    message = (raw.get("message") or raw.get("text") or "").strip()
    if is_bot_like_message(message) or is_game_notification(message):
        return MSG_TYPE_SYSTEM
    return MSG_TYPE_PLAYER
