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
            "⚠️ Você precisa entrar primeiro para usar este recurso.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔗 Entrar", callback_data="connect_account")]]
            ),
        )

    user_message = message

    text = "📊 Limite do lote: 1000 mensagens\n\n"
    text += "Envie o link da mensagem do chat de onde deseja salvar em lote.\n\n"
    text += "Exemplo: \n1. https://t.me/c/2114152609/1\n\n"
    text += "\n\n/cancel para cancelar ❌"

    ask = await message.chat.ask(text)

    if await is_input_cancelled(ask):
        return

    first_message = ask

    text = "Envie uma das opções abaixo:\n\n"
    text += "1. Copie o link da mensagem e me envie 📎\n"
    text += "Exemplo: https://t.me/c/2114152609/10\n\n"
    text += "2. Envie a quantidade de mensagens que deseja salvar 🔢\n"
    text += "Exemplo: 10"
    text += "\n\n/cancel para cancelar ❌"

    ask = await message.chat.ask(text)

    if await is_input_cancelled(ask):
        return

    last_message = ask

    first_parts = get_link_parts(first_message.text)

    if not first_parts:
        text = f"❌ Link inválido - {first_message.text}"
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
        text = f"❌ Link inválido - {last_message.text}"
        await message.reply_text(text)
        return

    first_chat_id, first_message_id, first_topic_id = first_parts
    last_chat_id, last_message_id, last_topic_id = last_parts

    if last_message_id < first_message_id:
        text = "⚠️ A última mensagem deve ser mais recente que a primeira."
        await message.reply_text(text)
        return

    if first_chat_id != last_chat_id:
        text = "⚠️ As duas mensagens devem ser do mesmo chat."
        await message.reply_text(text)
        return

    if (first_topic_id and not last_topic_id) or (not first_topic_id and last_topic_id):
        text = "⚠️ As duas mensagens devem ser do mesmo tópico."
        await message.reply_text(text)
        return

    if (first_topic_id and last_topic_id) and first_message_id != last_message_id:
        text = "⚠️ As duas mensagens devem ser do mesmo tópico."
        await message.reply_text(text)
        return

    # Get destination config
    config = await get_config_from_dest_link(message, first_message.text)
    if not config:
        return
        
    out = await message.reply_text("🔄 Buscando mensagens...")

    if not (first_topic_id and last_topic_id):
        messages = []
        total_messages = list(range(first_message_id, last_message_id + 1))
        for i in range(0, len(total_messages), 200):
            try:
                messages.extend(
                    await app.get_messages(first_chat_id, total_messages[i : i + 200])
                )
            except Exception as e:
                text = f"⚠️ Ocorreu um erro ao buscar as mensagens: {e}"
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
        text = "🔍 Nenhuma mensagem válida encontrada."
        return await out.edit(text)

    await out.delete()
    text = "\n".join(valid_messages)

    user_message.text = text

    logger.info(f"Batching {len(valid_messages)} messages")
    await on_https_message(bot, user_message, is_batch=True, config=config)
