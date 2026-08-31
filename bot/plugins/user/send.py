"""Copy a source message to a destination via the session client."""

from contextlib import suppress

from pyrogram import Client
from pyrogram.types import LinkPreviewOptions, Message

from bot.utils.text_replacements import apply_text_replacements

_PREVIEW_OFF = LinkPreviewOptions(is_disabled=True)


async def send_to_dest(
    client: Client,
    message: Message,
    dest_id: int,
    text_replacements: list | None = None,
    message_thread_id: int | None = None,
):
    """Copy via session; apply text replacements when configured."""
    await client.resolve_peer(dest_id)
    thread = {"message_thread_id": message_thread_id} if message_thread_id else {}

    rules = text_replacements or []
    raw = message.text or message.caption

    if rules and raw:
        new_text = apply_text_replacements(str(raw), rules)
        if message.media:
            with suppress(Exception):
                return await message.copy(
                    chat_id=dest_id, caption=new_text, **thread
                )
            return None
        with suppress(Exception):
            return await client.send_message(
                dest_id,
                new_text,
                link_preview_options=_PREVIEW_OFF,
                **thread,
            )
        return None

    with suppress(Exception):
        sent = await client.copy_message(
            dest_id, message.chat.id, message.id, **thread
        )
        return sent[0] if isinstance(sent, list) else sent

    with suppress(Exception):
        return await message.copy(chat_id=dest_id, **thread)

    text = message.text or message.caption
    if text:
        with suppress(Exception):
            return await client.send_message(
                dest_id,
                text.html,
                link_preview_options=_PREVIEW_OFF,
                **thread,
            )

    return None
