from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message

from bot.config import settings
from bot.enums import TransferStatus
from bot.utils import update_transfer


@Client.on_callback_query(filters.regex("^cancel"))
@Client.on_message(filters.command("cancel") & filters.private & filters.incoming)
async def cancel_transfer(bot: Client, query: CallbackQuery | Message):
    if isinstance(query, Message):
        transfers = {
            download_id: transfer
            for download_id, transfer in settings.TRANSFERS.items()
            if transfer["user_id"] == query.from_user.id
        }
        download_id = list(transfers.keys())
        func = query.reply_text
        kwargs = {}
    else:
        download_id = [int(query.data.split(" ", 1)[1])]
        func = query.answer
        kwargs = {"show_alert": True}

    if not download_id:
        return await func("❌ Nenhuma transferência encontrada.", **kwargs)

    for d_id in download_id:
        transfer = settings.TRANSFERS.get(d_id)
        if not transfer:
            continue

        if transfer["status"] == TransferStatus.CANCELLED.value:
            continue

        transfer["status"] = TransferStatus.CANCELLED.value
        await update_transfer(d_id, **transfer)
    return await func("✅ A transferência será cancelada.", **kwargs)
