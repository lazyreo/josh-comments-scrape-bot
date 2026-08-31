"""Resolve Telegram chat references from user input."""

from pyrogram import Client, errors
from pyrogram.enums import ChatType
from pyrogram.types import Chat, Message

from bot.utils.helpers import get_link_parts

_GROUP_TYPES = (ChatType.GROUP, ChatType.SUPERGROUP)


def chat_title(chat) -> str:
    if getattr(chat, "title", None):
        return chat.title
    if getattr(chat, "first_name", None):
        name = chat.first_name
        if getattr(chat, "last_name", None):
            name = f"{name} {chat.last_name}"
        return name
    if getattr(chat, "username", None):
        return f"@{chat.username}"
    return str(getattr(chat, "id", "Unknown"))


def parse_chat_ref(ask: Message):
    chat_ref, _ = parse_chat_input(ask)
    return chat_ref


def forward_post_ref(message: Message):
    """Return (source chat, message id) for a forwarded channel/group post."""
    origin = getattr(message, "forward_origin", None)
    if origin is not None:
        chat = getattr(origin, "chat", None) or getattr(origin, "sender_chat", None)
        msg_id = getattr(origin, "message_id", None)
        if chat is not None and msg_id is not None:
            return chat, msg_id

    chat = getattr(message, "forward_from_chat", None)
    msg_id = getattr(message, "forward_from_message_id", None)
    if chat is not None and msg_id is not None:
        return chat, msg_id
    return None, None


def parse_chat_input(ask: Message):
    """Return (chat_ref, original_message_id | None)."""
    forwarded_chat, forwarded_post_id = forward_post_ref(ask)
    if forwarded_chat:
        return forwarded_chat.id, forwarded_post_id
    if ask.forward_from:
        return ask.forward_from.id, None
    if not ask.text:
        return None, None
    text = ask.text.strip()
    parts = get_link_parts(text)
    if parts:
        chat_id, message_id, topic_tail = parts
        # 4-part forum links store the real message id in topic_tail
        return chat_id, topic_tail if topic_tail is not None else message_id
    if text.replace("-", "").isdigit():
        return int(text), None
    return text.replace("@", ""), None


async def resolve_chat(app: Client, chat_ref):
    try:
        return await app.get_chat(chat_ref)
    except errors.FloodWait:
        raise
    except Exception:
        pass
    try:
        return await app.get_users(chat_ref)
    except errors.FloodWait:
        raise
    except Exception:
        return None


async def resolve_topic_id(
    app: Client,
    chat: Chat | None,
    message_id: int | None,
) -> int | None:
    """Fetch the original message and read its forum topic / thread id."""
    if not chat or chat.type not in _GROUP_TYPES or not message_id:
        return None
    try:
        msg = await app.get_messages(chat.id, message_id)
    except errors.FloodWait:
        raise
    except Exception:
        return None
    if not msg or getattr(msg, "empty", False):
        return None
    if msg.topic is not None:
        return msg.topic.id
    return msg.message_thread_id
