"""Group / forum topic helpers for session auto-copy."""

from pyrogram import Client
from pyrogram.enums import ChatType
from pyrogram.types import Chat, Message

_GROUP_TYPES = (ChatType.GROUP, ChatType.SUPERGROUP)


def is_group_chat(chat: Chat | None) -> bool:
    return bool(chat and chat.type in _GROUP_TYPES)


def message_topic_id(message: Message) -> int | None:
    """Topic id for a source message when it belongs to a group/forum."""
    if not is_group_chat(message.chat):
        return None
    if message.topic is not None:
        return message.topic.id
    return message.message_thread_id


async def dest_thread_id(
    client: Client,
    dest_id: int,
    stored_topic_id: int | None,
) -> int | None:
    """Return message_thread_id when dest is a group and a topic is configured."""
    if not stored_topic_id:
        return None
    chat = await client.get_chat(dest_id)
    if is_group_chat(chat):
        return int(stored_topic_id)
    return None
