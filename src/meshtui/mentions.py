"""Channel mention / reply helpers.

Official MeshCore apps reply in a channel with::

    @[Name]: message text

Typing ``@`` or ``@[`` plus Tab completes the nickname from people who
have spoken in the current channel (and from the contact list).
"""

from __future__ import annotations

import re
from typing import Callable, Dict, Iterable, List, Optional

from textual.suggester import Suggester

SKIP_NICKNAMES = frozenset({"me", "unknown", "system", ""})

# In-progress mention at the end of the input: @name or @[name
_IN_PROGRESS = re.compile(r"@\[?(?P<partial>[^\s\]]*)$")


def format_mention(name: str) -> str:
    """Return the official mention token plus a trailing space."""
    return f"@[{name}]: "


def nicknames_from_messages(
    messages: Iterable[Dict],
    extra: Iterable[str] = (),
    exclude: Iterable[str] = (),
) -> List[str]:
    """Unique nicknames, most recent channel senders first."""
    excluded = {name.casefold() for name in exclude} | SKIP_NICKNAMES
    seen: set[str] = set()
    names: List[str] = []

    for msg in reversed(list(messages)):
        raw = msg.get("actual_sender") or msg.get("sender") or ""
        name = str(raw).strip()
        key = name.casefold()
        if key in excluded or key in seen:
            continue
        seen.add(key)
        names.append(name)

    for raw in extra:
        name = str(raw).strip()
        key = name.casefold()
        if key in excluded or key in seen:
            continue
        seen.add(key)
        names.append(name)

    return names


def complete_mention(text: str, names: Iterable[str]) -> Optional[str]:
    """If ``text`` ends with an in-progress @mention, complete it.

    Returns the full input with the mention replaced by ``@[Name]: ``,
    or None if nothing matches.
    """
    match = _IN_PROGRESS.search(text)
    if not match:
        return None

    partial = match.group("partial").casefold()
    start = match.start()
    for name in names:
        if name and name.casefold().startswith(partial):
            return text[:start] + format_mention(name)
    return None


def message_mentions(text: str, name: str) -> bool:
    """True if ``text`` contains an official ``@[name]`` mention."""
    if not text or not name:
        return False
    return f"@[{name}]".casefold() in text.casefold()


class MentionSuggester(Suggester):
    """Complete an in-progress ``@`` mention from a live name list."""

    def __init__(self, get_names: Callable[[], List[str]]) -> None:
        super().__init__(use_cache=False, case_sensitive=True)
        self._get_names = get_names

    async def get_suggestion(self, value: str) -> Optional[str]:
        return complete_mention(value, self._get_names())
