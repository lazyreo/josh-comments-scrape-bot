import logging

from pyrogram import Client, enums, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import settings
from bot.plugins.on_https_message import on_https_message
from bot.utils import (
    get_config_from_dest_link,
    get_link_parts,
    get_user_client,
    is_input_cancelled,
)

logger = logging.getLogger(__name__)


@Client.on_message(
    filters.command("batch")
    & filters.private
    & filters.incoming
    & filters.user(settings.OWNER_ID)
)
async def batch(bot: Client, message: Message):
    user_id = message.from_user.id

    app = await get_user_client(user_id)

    if not app or not app.is_connected:
        settings.CLIENTS.pop(app.me.id, None) if app and app.me else None
        return await message.reply_text(
            "⚠️ You need to log in first to use this feature.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔗 Log in", callback_data="connect_account")]]
            ),
        )

    user_message = message

    text = "📊 Batch limit: 1000 messages\n\n"
    text += "Send the message link from the chat you want to batch-save from.\n\n"
    text += "Example: \n1. https://t.me/c/2114152609/1\n\n"
    text += "\n\n/cancel to cancel ❌"

    ask = await message.chat.ask(text)

    if await is_input_cancelled(ask):
        return

    first_message = ask

    text = "Send one of the options below:\n\n"
    text += "1. Copy the message link and send it to me 📎\n"
    text += "Example: https://t.me/c/2114152609/10\n\n"
    text += "2. Send how many messages you want to save 🔢\n"
    text += "Example: 10"
    text += "\n\n/cancel to cancel ❌"

    ask = await message.chat.ask(text)

    if await is_input_cancelled(ask):
        return

    last_message = ask

    first_parts = get_link_parts(first_message.text)

    if not first_parts:
        text = f"❌ Invalid link - {first_message.text}"
        await message.reply_text(text)
        return

    if last_message.text.isdigit():
        last_parts = (
            first_parts[0],
            first_parts[1] + int(last_message.text) - 1,
            first_parts[2],
        )
    else:
        last_parts = get_link_parts(last_message.text)

    if not last_parts:
        text = f"❌ Invalid link - {last_message.text}"
        await message.reply_text(text)
        return

    first_chat_id, first_message_id, first_topic_id = first_parts
    last_chat_id, last_message_id, last_topic_id = last_parts

    if last_message_id < first_message_id:
        text = "⚠️ The last message must be more recent than the first."
        await message.reply_text(text)
        return

    if first_chat_id != last_chat_id:
        text = "⚠️ Both messages must be from the same chat."
        await message.reply_text(text)
        return

    if (first_topic_id and not last_topic_id) or (not first_topic_id and last_topic_id):
        text = "⚠️ Both messages must be from the same topic."
        await message.reply_text(text)
        return

    if (first_topic_id and last_topic_id) and first_message_id != last_message_id:
        text = "⚠️ Both messages must be from the same topic."
        await message.reply_text(text)
        return

    # Get destination config
    config = await get_config_from_dest_link(message, first_message.text)
    if not config:
        return
        
    out = await message.reply_text("🔄 Fetching messages...")

    if not (first_topic_id and last_topic_id):
        messages = []
        total_messages = list(range(first_message_id, last_message_id + 1))
        for i in range(0, len(total_messages), 200):
            try:
                messages.extend(
                    await app.get_messages(first_chat_id, total_messages[i : i + 200])
                )
            except Exception as e:
                text = f"⚠️ An error occurred while fetching messages: {e}"
                return await out.edit(text)
    else:
        messages = []
        async for message in app.get_discussion_replies(
            first_chat_id, first_message_id
        ):
            if not message.topic:
                continue

            if (
                message.topic.id != first_message_id
            ):  # for topic links, message id acts as topic id
                continue

            if len(messages) > len(range(first_topic_id, last_topic_id + 1)):
                logger.info(
                    f"Got {len(messages)} messages for {len(range(first_topic_id, last_topic_id + 1))} topics"
                )
                break

            if message.id not in range(first_topic_id, last_topic_id + 1):
                continue

            messages.append(message)


    messages = sorted(messages, key=lambda x: x.id)

    valid_messages = []

    for message in messages:
        if message.empty:
            continue

        if message.chat.type == enums.ChatType.BOT:
            link = f"https://t.me/{message.chat.username}/{message.id}"
        else:
            link = message.link

        valid_messages.append(link)

    if not valid_messages:
        text = "🔍 No valid messages found."
        return await out.edit(text)

    await out.delete()
    text = "\n".join(valid_messages)

    user_message.text = text

    logger.info(f"Batching {len(valid_messages)} messages")
    await on_https_message(bot, user_message, is_batch=True, config=config)
