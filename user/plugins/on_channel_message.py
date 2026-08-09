#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Auto-forward source messages to destinations via the logged-in session."""

import logging
from contextlib import suppress

from pyrogram import Client, filters
from pyrogram.types import Message

from bot.utils.email_resend import (
    build_forward_email_body,
    notify_forward_emails,
)
from bot.utils.forward_sources import is_active_source_chat
from database import db

logger = logging.getLogger(__name__)


async def _session_user_id(client: Client) -> int | None:
    me = client.me or await client.get_me()
    user = await db.users.filter_document({"session.id": me.id})
    if not user:
        return None
    return user["_id"]


async def _send_to_dest(client: Client, message: Message, dest_id: int):
    """Forward via session; fall back to copy, then text/caption re-send."""
    with suppress(Exception):
        sent = await client.forward_messages(dest_id, message.chat.id, message.id)
        return sent[0] if isinstance(sent, list) else sent

    with suppress(Exception):
        return await message.copy(chat_id=dest_id)

    text = message.text or message.caption
    if text:
        with suppress(Exception):
            return await client.send_message(dest_id, text.html)

    return None


@Client.on_message(filters.create(is_active_source_chat))
async def on_channel_message(client: Client, message: Message):
    """Copy new source messages to every active destination for this session user."""
    if message.service or message.empty:
        return

    me = client.me or await client.get_me()
    # Skip messages sent by the logged-in account itself
    if message.outgoing:
        return
    if message.from_user and message.from_user.id == me.id:
        return
    if message.sender_chat and message.sender_chat.id == me.id:
        return

    user_id = await _session_user_id(client)
    if not user_id:
        return

    source_id = message.chat.id
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
        dest_id = fwd["dest_id"]
        try:
            log = await _send_to_dest(client, message, dest_id)
        except Exception as e:
            logger.warning(
                "Forward failed %s -> %s for user %s: %s",
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
            continue

        emails = fwd.get("emails") or []
        if not emails:
            continue

        subject = f"Encaminhamento: {fwd['source_title']} → {fwd['dest_title']}"
        body = build_forward_email_body(
            message,
            source_title=fwd["source_title"],
            dest_title=fwd["dest_title"],
        )
        await notify_forward_emails(emails, subject=subject, body=body)
