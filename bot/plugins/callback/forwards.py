from bson import ObjectId
from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.utils.chat_resolve import chat_title, parse_chat_ref, resolve_chat
from bot.utils.email_resend import parse_emails
from bot.utils.forward_sources import refresh_active_sources
from bot.utils.helpers import get_user_client
from database import db


@Client.on_callback_query(filters.regex(r"^forwards$"))
@Client.on_message(filters.command("forwards") & filters.private & filters.incoming)
async def forwards(bot, message: CallbackQuery | Message):
    user_id = message.from_user.id
    rows = await db.user_forwards.filter_documents({"user_id": user_id})

    text = "🔀 **Seus encaminhamentos**\n\n"
    text += (
        "Cada encaminhamento copia novas mensagens de uma **Origem** "
        "para um **Destino** usando a conta conectada.\n"
    )

    buttons = []
    for row in rows:
        status = "✅" if row["status"] else "❌"
        label = f"{status} {row['source_title']} → {row['dest_title']}"
        text += f"\n{label}"
        buttons.append(
            [
                InlineKeyboardButton(
                    label[:64],
                    callback_data=f"view_forward {row['_id']}",
                )
            ]
        )

    if not rows:
        text += "\nNenhum encaminhamento ainda. Toque em **Adicionar** para criar um.\n"

    buttons.append(
        [InlineKeyboardButton("➕ Adicionar", callback_data="add_forward")]
    )
    buttons.append([InlineKeyboardButton("🔙 Voltar", callback_data="start")])

    await bot.reply(
        message,
        text,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@Client.on_callback_query(filters.regex(r"^add_forward$"))
async def add_forward(bot: Client, message: CallbackQuery):
    user_id = message.from_user.id
    app = await get_user_client(user_id)

    if not app:
        return await message.message.reply_text(
            "Você precisa entrar primeiro.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔐 Entrar", callback_data="connect_account"
                        )
                    ],
                    [InlineKeyboardButton("🔙 Voltar", callback_data="forwards")],
                ]
            ),
        )

    back = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 Voltar", callback_data="forwards")]]
    )

    try:
        ask = await message.message.chat.ask(
            "📥 **Origem**\n\n"
            "Envie o chat de onde deseja copiar:\n"
            "• @usuário\n"
            "• id do chat / usuário\n"
            "• ou encaminhe qualquer mensagem desse chat\n\n"
            "A conta conectada precisa conseguir ver esse chat.\n\n"
            "/cancel para cancelar"
        )
    except Exception as e:
        return await message.message.reply_text(f"🚫 Erro: {e}", reply_markup=back)

    if ask.text and ask.text.strip().lower() == "/cancel":
        return await ask.reply("❌ Cancelado", reply_markup=back)

    source_ref = parse_chat_ref(ask)
    if source_ref is None:
        return await ask.reply("⚠️ Origem inválida. Tente de novo.", reply_markup=back)

    source = await resolve_chat(app, source_ref)
    if not source:
        return await ask.reply(
            "⚠️ Não foi possível encontrar essa origem.\n"
            "Entre no chat com a conta conectada e tente de novo.",
            reply_markup=back,
        )

    try:
        ask = await message.message.chat.ask(
            "📤 **Destino**\n\n"
            "Envie o chat para onde deseja copiar:\n"
            "• @usuário\n"
            "• id do chat / usuário\n"
            "• ou encaminhe qualquer mensagem desse chat\n\n"
            "A conta conectada precisa conseguir publicar lá.\n\n"
            "/cancel para cancelar"
        )
    except Exception as e:
        return await message.message.reply_text(f"🚫 Erro: {e}", reply_markup=back)

    if ask.text and ask.text.strip().lower() == "/cancel":
        return await ask.reply("❌ Cancelado", reply_markup=back)

    dest_ref = parse_chat_ref(ask)
    if dest_ref is None:
        return await ask.reply("⚠️ Destino inválido. Tente de novo.", reply_markup=back)

    dest = await resolve_chat(app, dest_ref)
    if not dest:
        return await ask.reply(
            "⚠️ Não foi possível encontrar esse destino.\n"
            "Entre no chat com a conta conectada e tente de novo.",
            reply_markup=back,
        )

    source_name = chat_title(source)
    dest_name = chat_title(dest)

    try:
        ask = await message.message.chat.ask(
            "📧 **E-mails** (opcional)\n\n"
            "Envie até **3** e-mails para também receber as mensagens encaminhadas.\n"
            "Separe por espaços ou linhas.\n\n"
            "Exemplo:\n"
            "`um@mail.com dois@mail.com`\n\n"
            "/skip para pular\n"
            "/cancel para cancelar"
        )
    except Exception as e:
        return await message.message.reply_text(f"🚫 Erro: {e}", reply_markup=back)

    if ask.text and ask.text.strip().lower() == "/cancel":
        return await ask.reply("❌ Cancelado", reply_markup=back)

    emails: list = []
    if ask.text and ask.text.strip().lower() == "/skip":
        emails = []
    else:
        emails, error = parse_emails(ask.text or "")
        if error:
            return await ask.reply(f"⚠️ {error}", reply_markup=back)

    await db.user_forwards.create(
        user_id=user_id,
        source_id=source.id,
        source_title=source_name,
        dest_id=dest.id,
        dest_title=dest_name,
        emails=emails,
    )
    await refresh_active_sources()

    text = (
        f"✅ Encaminhamento adicionado\n\n"
        f"**De:** {source_name} (`{source.id}`)\n"
        f"**Para:** {dest_name} (`{dest.id}`)\n"
    )
    if emails:
        text += "**E-mails:**\n" + "\n".join(f"• `{e}`" for e in emails)
    else:
        text += "**E-mails:** Nenhum"

    return await message.message.reply_text(text, reply_markup=back)


@Client.on_callback_query(filters.regex(r"^view_forward "))
async def view_forward(_, message: CallbackQuery):
    _id = ObjectId(message.data.split()[1])
    row = await db.user_forwards.filter_document({"_id": _id})
    if not row or row["user_id"] != message.from_user.id:
        return await message.answer("Não encontrado", show_alert=True)

    emails = row.get("emails") or []

    text = "**Detalhes do encaminhamento**\n\n"
    text += f"📥 Origem: {row['source_title']}\n"
    text += f"   `{row['source_id']}`\n"
    text += f"📤 Destino: {row['dest_title']}\n"
    text += f"   `{row['dest_id']}`\n"
    text += f"📊 Status: {'✅ Ativo' if row['status'] else '❌ Inativo'}\n"
    if emails:
        text += "📧 E-mails:\n"
        for addr in emails:
            text += f"   • `{addr}`\n"
    else:
        text += "📧 E-mails: Nenhum\n"

    buttons = [
        [
            InlineKeyboardButton(
                "🔒 Desativar" if row["status"] else "🔓 Ativar",
                callback_data=f"toggle_forward {_id}",
            ),
            InlineKeyboardButton(
                "🗑️ Excluir", callback_data=f"delete_forward {_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                "📧 Definir e-mails", callback_data=f"set_forward_emails {_id}"
            ),
        ],
    ]
    if emails:
        buttons.append(
            [
                InlineKeyboardButton(
                    "🧹 Limpar e-mails",
                    callback_data=f"clear_forward_emails {_id}",
                )
            ]
        )
    buttons.append([InlineKeyboardButton("🔙 Voltar", callback_data="forwards")])

    await message.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))


@Client.on_callback_query(filters.regex(r"^set_forward_emails "))
async def set_forward_emails(bot: Client, message: CallbackQuery):
    _id = message.data.split()[1]
    row = await db.user_forwards.filter_document({"_id": ObjectId(_id)})
    if not row or row["user_id"] != message.from_user.id:
        return await message.answer("Não encontrado", show_alert=True)

    back = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 Voltar", callback_data=f"view_forward {_id}")]]
    )

    try:
        ask = await message.message.chat.ask(
            "📧 Envie até **3** e-mails.\n\n"
            "Separe por espaços ou linhas.\n\n"
            "Exemplo:\n"
            "`um@mail.com dois@mail.com`\n\n"
            "/cancel para cancelar"
        )
    except Exception as e:
        return await message.message.reply_text(f"🚫 Erro: {e}", reply_markup=back)

    if ask.text and ask.text.strip().lower() == "/cancel":
        return await ask.reply("❌ Cancelado", reply_markup=back)

    emails, error = parse_emails(ask.text or "")
    if error:
        return await ask.reply(f"⚠️ {error}", reply_markup=back)

    await db.user_forwards.update(ObjectId(_id), {"emails": emails})
    listed = "\n".join(f"• `{e}`" for e in emails)
    return await ask.reply(
        f"✅ E-mails salvos:\n{listed}",
        reply_markup=back,
    )


@Client.on_callback_query(filters.regex(r"^clear_forward_emails "))
async def clear_forward_emails(bot, message: CallbackQuery):
    _id = message.data.split()[1]
    row = await db.user_forwards.filter_document({"_id": ObjectId(_id)})
    if not row or row["user_id"] != message.from_user.id:
        return await message.answer("Não encontrado", show_alert=True)

    await db.user_forwards.update(ObjectId(_id), {"emails": []})
    message.data = f"view_forward {_id}"
    await view_forward(bot, message)


@Client.on_callback_query(filters.regex(r"^delete_forward "))
async def delete_forward(_, message: CallbackQuery):
    _id = message.data.split()[1]
    return await message.edit_message_text(
        "⚠️ Excluir este encaminhamento?",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Sim", callback_data=f"confirm_delete_forward {_id}"
                    ),
                    InlineKeyboardButton("❌ Não", callback_data="forwards"),
                ]
            ]
        ),
    )


@Client.on_callback_query(filters.regex(r"^confirm_delete_forward "))
async def confirm_delete_forward(bot, message: CallbackQuery):
    _id = message.data.split()[1]
    row = await db.user_forwards.filter_document({"_id": ObjectId(_id)})
    if row and row["user_id"] == message.from_user.id:
        await db.user_forwards.delete(ObjectId(_id))
        await refresh_active_sources()
    await forwards(bot, message)


@Client.on_callback_query(filters.regex(r"^toggle_forward "))
async def toggle_forward(bot, message: CallbackQuery):
    _id = message.data.split()[1]
    row = await db.user_forwards.filter_document({"_id": ObjectId(_id)})
    if not row or row["user_id"] != message.from_user.id:
        return await message.answer("Não encontrado", show_alert=True)

    await db.user_forwards.update(ObjectId(_id), {"status": not row["status"]})
    await refresh_active_sources()
    message.data = f"view_forward {_id}"
    await view_forward(bot, message)
