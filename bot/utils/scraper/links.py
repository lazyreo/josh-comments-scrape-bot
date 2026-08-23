import re

from bot.utils import get_link_parts

_POST_LINK_RE = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me|telegram\.dog)/[^\s,]+",
    re.IGNORECASE,
)
# Chat path before post id: username/ or c/123456/
_TG_CHAT_PREFIX = (
    r"(?:https?://)?(?:t\.me|telegram\.me|telegram\.dog)/"
    r"(?:c/\d+/|[^\s,/]+/)"
)
# 328910-328920
# https://t.me/chan/328910 - 328920
# https://t.me/chan/328910 - https://t.me/chan/328920
_POST_RANGE_RE = re.compile(
    rf"(?:({_TG_CHAT_PREFIX}))?"
    r"(\d+)\s*[-–—]\s*"
    rf"(?:{_TG_CHAT_PREFIX})?"
    r"(\d+)",
    re.IGNORECASE,
)
_MAX_POST_RANGE = 500


def _normalize_post_link(link: str) -> str:
    link = link.strip().rstrip(".,;)")
    if link.startswith(("http://", "https://", "tg://")):
        return link
    return f"https://{link}"


def _private_chat_slug(chat_id: int) -> str:
    text = str(chat_id)
    if text.startswith("-100"):
        return text[4:]
    if text.startswith("-"):
        return text[1:]
    return text


def build_post_link(chat_or_id, post_id: int) -> str:
    """Build a t.me post link for public or private channels/groups."""
    if isinstance(chat_or_id, int):
        return f"https://t.me/c/{_private_chat_slug(chat_or_id)}/{post_id}"

    username = getattr(chat_or_id, "username", None)
    if username:
        return f"https://t.me/{username}/{post_id}"

    return f"https://t.me/c/{_private_chat_slug(chat_or_id.id)}/{post_id}"


def _chat_peer_id(peer) -> int | None:
    if peer is None:
        return None
    if isinstance(peer, int):
        return peer
    return getattr(peer, "id", None)


def _chat_username(peer) -> str:
    if peer is None or isinstance(peer, int):
        return ""
    return (getattr(peer, "username", None) or "").lower()


def link_chat_matches(chat, link_chat_id) -> bool:
    other_id = _chat_peer_id(link_chat_id)
    if other_id is not None and chat.id == other_id:
        return True

    linked_id = getattr(chat, "linked_chat_id", None)
    if other_id is not None and linked_id is not None and linked_id == other_id:
        return True

    if not isinstance(link_chat_id, int):
        other_linked_id = getattr(link_chat_id, "linked_chat_id", None)
        if other_linked_id is not None and other_linked_id == chat.id:
            return True

    chat_username = _chat_username(chat)
    other_username = _chat_username(link_chat_id)
    if other_username and chat_username and other_username == chat_username:
        return True

    if isinstance(link_chat_id, str):
        name = link_chat_id.lstrip("@").lower()
        return bool(chat_username) and chat_username == name

    return False


def _expand_range(start: int, end: int) -> list[int] | None:
    if start > end:
        start, end = end, start
    if end - start + 1 > _MAX_POST_RANGE:
        return None
    return list(range(start, end + 1))


def parse_post_tokens(
    text: str, chat
) -> tuple[list[int], list[str], dict[int, str]]:
    post_ids: list[int] = []
    invalid: list[str] = []
    post_links: dict[int, str] = {}
    seen: set[int] = set()

    def _add(post_id: int, link: str | None = None) -> None:
        if post_id in seen:
            return
        seen.add(post_id)
        post_ids.append(post_id)
        if link:
            post_links[post_id] = link

    # Ranges first so "link/328910 - 328920" is not split into a lone link + junk.
    for match in _POST_RANGE_RE.finditer(text):
        link_prefix, start_s, end_s = match.groups()
        start, end = int(start_s), int(end_s)
        expanded = _expand_range(start, end)
        if expanded is None:
            invalid.append(match.group(0).strip())
            continue

        if link_prefix:
            sample = _normalize_post_link(f"{link_prefix}{start}")
            parts = get_link_parts(sample)
            if not parts or not link_chat_matches(chat, parts[0]):
                invalid.append(match.group(0).strip())
                continue
            for post_id in expanded:
                _add(post_id, _normalize_post_link(f"{link_prefix}{post_id}"))
        else:
            for post_id in expanded:
                _add(post_id)

    remainder = _POST_RANGE_RE.sub(" ", text)

    links = _POST_LINK_RE.findall(remainder)
    remainder = _POST_LINK_RE.sub(" ", remainder)

    for raw_link in links:
        link = _normalize_post_link(raw_link)
        parts = get_link_parts(link)
        if not parts or not link_chat_matches(chat, parts[0]):
            invalid.append(raw_link)
            continue
        _add(parts[1], link)

    for token in re.split(r"[\s,]+", remainder):
        token = token.strip()
        if not token:
            continue
        if token.isdigit():
            _add(int(token))
            continue
        invalid.append(token)

    return post_ids, invalid, post_links
