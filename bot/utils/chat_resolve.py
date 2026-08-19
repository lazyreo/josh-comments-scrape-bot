"""Resolve Telegram chat references from user input."""

from pyrogram import Client, errors
from pyrogram.types import Message


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
    

def parse_chat_input(ask: Message):
    forwarded_chat = ask.forward_from_chat.id if ask.forward_from_chat else None
    forwarded_post_id = ask.forward_from_message_id if ask.forward_from_message_id else None
    if forwarded_chat:
        return forwarded_chat.id, forwarded_post_id
    if ask.forward_from:
        return ask.forward_from.id, None
    if not ask.text:
        return None, None
    text = ask.text.strip()
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
