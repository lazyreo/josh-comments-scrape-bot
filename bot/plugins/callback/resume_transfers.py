from pyrogram import Client, filters
from pyrogram.types import CallbackQuery

from bot.plugins.on_https_message import on_https_message
from bot.utils import remove_transfer_from_queue
from database import db


@Client.on_callback_query(filters.regex("^resume_transfers"))
async def resume_transfers(bot: Client, query: CallbackQuery):
    download_id = int(query.data.split(" ", 1)[1])
    user_id = query.from_user.id
    transfer = await db.transfers.read(download_id)
    if not transfer:
        return await query.answer("❌ Nenhuma transferência encontrada.", show_alert=True)

    link_index = int(transfer["link_index"])
    links = transfer["links"][link_index:]
    await remove_transfer_from_queue(transfer["_id"])
    if not links:
        return await query.answer("Transferência concluída.", show_alert=True)

    text = "\n".join(links)

    user_message_id = transfer["user_message_id"]
    user_message_chat_id = transfer["user_message_chat_id"]

    user_message = await bot.get_messages(user_message_chat_id, user_message_id)
    await query.message.delete()
    user_message.text = text
    await on_https_message(bot, user_message)
