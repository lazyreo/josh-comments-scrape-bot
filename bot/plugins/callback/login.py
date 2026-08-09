from asyncio.exceptions import TimeoutError

from pyrogram import Client, filters
from pyrogram.errors import (
    PasswordHashInvalid,
    PhoneCodeExpired,
    PhoneCodeInvalid,
    PhoneNumberInvalid,
    SessionPasswordNeeded,
)
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from bot import User
from database import db


class Data:
    generate_single_button = [
        InlineKeyboardButton("🔒 Log in securely", callback_data="connect_account")
    ]

    home_buttons = [
        [InlineKeyboardButton("➡️ Continue", callback_data="add_forward")],
        [InlineKeyboardButton(text="🏠 Home", callback_data="start")],
    ]

    generate_button = [generate_single_button]


async def generate_session(bot: Client, msg: Message):
    user_id = msg.from_user.id

    api_id = bot.api_id
    api_hash = bot.api_hash

    t = "📲 Now send your phone number with the country code.\nExample: `+15551234567`"
    t += "\n\nNote: **Use the same number as the account you're using right now.**"
    t += "\n\n/cancel to cancel ❌"

    phone_number_msg: Message = await bot.ask(
        user_id,
        t,
        filters=filters.text | filters.contact,
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("Send number", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
        timeout=300,
    )
    if await cancelled(phone_number_msg):
        return

    if phone_number_msg.contact:
        phone_number = phone_number_msg.contact.phone_number
    else:
        phone_number = phone_number_msg.text

    await msg.reply("🔐 Signing in as user...", reply_markup=ReplyKeyboardRemove())

    client = Client(
        name=f"user_{user_id}", api_id=api_id, api_hash=api_hash, in_memory=True
    )

    await client.connect()
    try:
        code = None
        code = await client.send_code(phone_number)
    except PhoneNumberInvalid:
        await msg.reply(
            "🚫 Invalid phone number. Start login again.",
            reply_markup=InlineKeyboardMarkup(Data.generate_button),
        )
        return
    try:
        phone_code_msg = None
        phone_code_msg = await bot.ask(
            user_id,
            "📩 Check the OTP in the official Telegram app. When you get it, send it like this: if the OTP is `12345`, **send** `1 2 3 4 5`.",
            filters=filters.text,
            timeout=600,
        )
        if await cancelled(phone_code_msg):
            return
    except TimeoutError:
        await msg.reply(
            "⏰ Timed out (10 minutes). Start login again.",
            reply_markup=InlineKeyboardMarkup(Data.generate_button),
        )
        return

    if " " not in phone_code_msg.text:
        await phone_code_msg.reply(
            "🚫 Invalid OTP format. If it is `12345`, **send** `1 2 3 4 5`.",
            quote=True,
            reply_markup=InlineKeyboardMarkup(Data.generate_button),
        )
        return

    phone_code = phone_code_msg.text.replace(" ", "")
    try:
        await client.sign_in(phone_number, code.phone_code_hash, phone_code)
    except PhoneCodeInvalid:
        await msg.reply(
            "❌ Invalid OTP. Start login again.",
            reply_markup=InlineKeyboardMarkup(Data.generate_button),
        )
        return
    except PhoneCodeExpired:
        await msg.reply(
            "⌛ OTP expired. Start login again.",
            reply_markup=InlineKeyboardMarkup(Data.generate_button),
        )
        return
    except SessionPasswordNeeded:
        try:
            two_step_msg = await bot.ask(
                user_id,
                "🔐 Your account has two-step verification. Send the password.",
                filters=filters.text,
                timeout=300,
            )
        except TimeoutError:
            await msg.reply(
                "⏰ Timed out (5 minutes). Start login again.",
                reply_markup=InlineKeyboardMarkup(Data.generate_button),
            )
            return
        try:
            password = two_step_msg.text
            await client.check_password(password=password)
        except PasswordHashInvalid:
            await two_step_msg.reply(
                "🚫 Invalid password. Start login again.",
                quote=True,
                reply_markup=InlineKeyboardMarkup(Data.generate_button),
            )
            return

    string_session = await client.export_session_string()
    me = await client.get_me()

    if me.id != user_id:
        await msg.reply(
            "🚫 You are not the owner of this account. Log in with your own number.",
            reply_markup=InlineKeyboardMarkup(Data.generate_button),
        )
        return

    await db.users.update(
        user_id,
        {
            "session.string": string_session,
            "session.id": me.id,
            "session.username": me.username,
        },
    )

    await bot.send_message(
        msg.chat.id,
        "🎉 Login successful! Tap **Continue** to add a Source → Destination forward.",
        reply_markup=InlineKeyboardMarkup(Data.home_buttons),
    )

    client = User(string_session, name=f"user_{user_id}")
    await client.start()


async def cancelled(msg):
    if not msg.text:
        return
    if "/cancel" in msg.text:
        await msg.reply(
            "🚫 Process cancelled!",
            quote=True,
            reply_markup=ReplyKeyboardRemove(),
        )
        await msg.reply(
            "You can log in again by tapping the button below.",
            quote=True,
            reply_markup=InlineKeyboardMarkup(Data.generate_button),
        )
        return True
    elif msg.text.startswith("/"):
        await msg.reply(
            "🚫 Process cancelled!",
            quote=True,
            reply_markup=ReplyKeyboardRemove(),
        )
        return True
    else:
        return False
