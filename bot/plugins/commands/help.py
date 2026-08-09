from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.config import Script


@Client.on_message(filters.command("help") & filters.private & filters.incoming)
@Client.on_callback_query(filters.regex("^help_\d+$"))
async def help(bot: Client, message: Message | CallbackQuery):
    markup = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔙 Back", callback_data="start")],
        ]
    )
    text = Script.HELP_MESSAGE_1
    await bot.reply(message, text=text, reply_markup=markup)
