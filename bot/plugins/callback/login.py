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
        InlineKeyboardButton("🔒 Entrar com segurança", callback_data="connect_account")
    ]

    home_buttons = [
        [InlineKeyboardButton("➡️ Continuar", callback_data="add_forward")],
        [InlineKeyboardButton(text="🏠 Início", callback_data="start")],
    ]

    generate_button = [generate_single_button]


async def generate_session(bot: Client, msg: Message):
    user_id = msg.from_user.id

    api_id = bot.api_id
    api_hash = bot.api_hash

    t = "📲 Agora envie seu número de telefone com o código do país.\nExemplo: `+5511999999999`"
    t += "\n\nObs.: **Use o mesmo número da conta que você está usando agora.**"
    t += "\n\n/cancel para cancelar ❌"

    phone_number_msg: Message = await bot.ask(
        user_id,
        t,
        filters=filters.text | filters.contact,
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("Enviar número", request_contact=True)]],
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

    await msg.reply("🔐 Entrando como usuário...", reply_markup=ReplyKeyboardRemove())

    client = Client(
        name=f"user_{user_id}", api_id=api_id, api_hash=api_hash, in_memory=True
    )

    await client.connect()
    try:
        code = None
        code = await client.send_code(phone_number)
    except PhoneNumberInvalid:
        await msg.reply(
            "🚫 Número de telefone inválido. Comece o login novamente.",
            reply_markup=InlineKeyboardMarkup(Data.generate_button),
        )
        return
    try:
        phone_code_msg = None
        phone_code_msg = await bot.ask(
            user_id,
            "📩 Verifique o OTP no app oficial do Telegram. Quando receber, envie no formato: se o OTP for `12345`, **envie** `1 2 3 4 5`.",
            filters=filters.text,
            timeout=600,
        )
        if await cancelled(phone_code_msg):
            return
    except TimeoutError:
        await msg.reply(
            "⏰ Tempo esgotado (10 minutos). Comece o login novamente.",
            reply_markup=InlineKeyboardMarkup(Data.generate_button),
        )
        return

    if " " not in phone_code_msg.text:
        await phone_code_msg.reply(
            "🚫 Formato de OTP inválido. Se for `12345`, **envie** `1 2 3 4 5`.",
            quote=True,
            reply_markup=InlineKeyboardMarkup(Data.generate_button),
        )
        return

    phone_code = phone_code_msg.text.replace(" ", "")
    try:
        await client.sign_in(phone_number, code.phone_code_hash, phone_code)
    except PhoneCodeInvalid:
        await msg.reply(
            "❌ OTP inválido. Comece o login novamente.",
            reply_markup=InlineKeyboardMarkup(Data.generate_button),
        )
        return
    except PhoneCodeExpired:
        await msg.reply(
            "⌛ OTP expirado. Comece o login novamente.",
            reply_markup=InlineKeyboardMarkup(Data.generate_button),
        )
        return
    except SessionPasswordNeeded:
        try:
            two_step_msg = await bot.ask(
                user_id,
                "🔐 Sua conta tem verificação em duas etapas. Envie a senha.",
                filters=filters.text,
                timeout=300,
            )
        except TimeoutError:
            await msg.reply(
                "⏰ Tempo esgotado (5 minutos). Comece o login novamente.",
                reply_markup=InlineKeyboardMarkup(Data.generate_button),
            )
            return
        try:
            password = two_step_msg.text
            await client.check_password(password=password)
        except PasswordHashInvalid:
            await two_step_msg.reply(
                "🚫 Senha inválida. Comece o login novamente.",
                quote=True,
                reply_markup=InlineKeyboardMarkup(Data.generate_button),
            )
            return

    string_session = await client.export_session_string()
    me = await client.get_me()

    if me.id != user_id:
        await msg.reply(
            "🚫 Você não é o dono desta conta. Faça login com o seu próprio número.",
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
        "🎉 Login realizado com sucesso! Toque em **Continuar** para adicionar um encaminhamento Origem → Destino.",
        reply_markup=InlineKeyboardMarkup(Data.home_buttons),
    )

    client = User(string_session, name=f"user_{user_id}")
    await client.start()


async def cancelled(msg):
    if not msg.text:
        return
    if "/cancel" in msg.text:
        await msg.reply(
            "🚫 Processo cancelado!",
            quote=True,
            reply_markup=ReplyKeyboardRemove(),
        )
        await msg.reply(
            "Você pode entrar novamente tocando no botão abaixo.",
            quote=True,
            reply_markup=InlineKeyboardMarkup(Data.generate_button),
        )
        return True
    elif msg.text.startswith("/"):
        await msg.reply(
            "🚫 Processo cancelado!",
            quote=True,
            reply_markup=ReplyKeyboardRemove(),
        )
        return True
    else:
        return False
