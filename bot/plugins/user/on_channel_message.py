"""Auto-copy source messages to destinations via the logged-in session."""

import logging

from pyrogram import Client, filters
from pyrogram.types import Message

from bot.plugins.user.send import send_to_dest
from bot.plugins.user.session import session_user_id
from bot.plugins.user.topics import dest_thread_id, message_topic_id
from bot.utils.forward_sources import is_active_source_chat
from database import db

logger = logging.getLogger(__name__)


@Client.on_message(filters.create(is_active_source_chat))
async def on_channel_message(client: Client, message: Message):
    """Copy new source messages to every active destination for this session user."""
    if message.service or message.empty:
        return

    me = client.me or await client.get_me()
    # Skip messages sent by the logged-in account itself
    # if message.outgoing:
    #     return
    # if message.from_user and message.from_user.id == me.id:
    #     return
    # if message.sender_chat and message.sender_chat.id == me.id:
    #     return

    user_id = await session_user_id(client)
    if not user_id:
        return

    source_id = message.chat.id
    src_topic = message_topic_id(message)
    forwards = await db.user_forwards.filter_documents(
        {
            "user_id": user_id,
            "source_id": source_id,
            "status": True,
        }
    )
    if not forwards:
        return

    for fwd in forwards:
        fwd_src_topic = fwd.get("source_topic_id")
        if fwd_src_topic is not None and src_topic != fwd_src_topic:
            continue

        dest_id = fwd["dest_id"]
        rules = fwd.get("text_replacements") or []
        thread_id = await dest_thread_id(
            client, dest_id, fwd.get("dest_topic_id")
        )
        try:
            log = await send_to_dest(
                client, message, dest_id, rules, message_thread_id=thread_id
            )
        except Exception as e:
            logger.warning(
                "Copy failed %s -> %s for user %s: %s",
                source_id,
                dest_id,
                user_id,
                e,
            )
            continue

        if not log:
            logger.warning(
                "No dest message created %s -> %s for user %s",
                source_id,
                dest_id,
                user_id,
            )
