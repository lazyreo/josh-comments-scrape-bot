import traceback

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.config import settings
from bot.plugins.callback.login import generate_session
from database import db


@Client.on_message(filters.command("account") & filters.private & filters.incoming)
@Client.on_callback_query(filters.regex("^connected_account$"))
async def connected_account(bot: Client, message: CallbackQuery | Message):
    user = await db.users.read(message.from_user.id)
    session = user.get("session", {})

    text = ""

    if session.get("string"):
        text += "🔗 **Account connected**\n\n"
        text += "💻 **Status**: Connected ✅\n"
        text += f"👤 **Username**: {'@' + session['username'] if session['username'] else 'Not available'}\n"
        text += f"🔑 **Session ID**: {session['id']}\n"
    else:
        text += "💻 **Status**: Not connected ❌\n\n"
        text += "🔗 **Connect your account to start using the bot**\n\n"

    buttons = []

    if session.get("string"):
        buttons.append(
            [InlineKeyboardButton("🔓 Log out", callback_data="disconnect_account")]
        )
    else:
        buttons.append(
            [InlineKeyboardButton("🔐 Log in", callback_data="connect_account")]
        )

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="start")])

    await bot.reply(message, text, reply_markup=InlineKeyboardMarkup(buttons))


@Client.on_callback_query(filters.regex("^disconnect_account$"))
async def disconnect_account(bot: Client, message: CallbackQuery):
    user = await db.users.read(message.from_user.id)
    if not user.get("session").get("id"):
        return await message.answer("⚠️ No account connected.", show_alert=True)

    await db.users.remove_session(message.from_user.id)

    try:
        app = settings.CLIENTS[user["session"]["id"]]
        await app.stop()
    except Exception:
        traceback.print_exc()

    settings.CLIENTS.pop(user["session"]["id"], None)

    await message.edit_message_text(
        "🚪 **Account disconnected successfully.**",
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🔐 Log in", callback_data="connect_account")],
                [InlineKeyboardButton("🔙 Back", callback_data="start")],
            ]
        ),
        disable_web_page_preview=True,
    )


@Client.on_callback_query(filters.regex("^connect_account$"))
async def connect_account(bot: Client, message: CallbackQuery):
    user_message = message.message
    user_message.from_user = message.from_user
    await generate_session(bot, user_message)
