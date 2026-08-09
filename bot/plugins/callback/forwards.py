from bson import ObjectId
from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.utils.chat_resolve import chat_title, parse_chat_ref, resolve_chat
from bot.utils.forward_sources import refresh_active_sources
from bot.utils.helpers import get_user_client
from database import db


@Client.on_callback_query(filters.regex(r"^forwards$"))
@Client.on_message(filters.command("forwards") & filters.private & filters.incoming)
async def forwards(bot, message: CallbackQuery | Message):
    user_id = message.from_user.id
    rows = await db.user_forwards.filter_documents({"user_id": user_id})

    text = "🔀 **Your forwards**\n\n"
    text += (
        "Each forward copies new messages from a **Source** "
        "to a **Destination** using the connected account.\n"
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
        text += "\nNo forwards yet. Tap **Add** to create one.\n"

    buttons.append(
        [InlineKeyboardButton("➕ Add", callback_data="add_forward")]
    )
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="start")])

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
            "You need to log in first.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔐 Log in", callback_data="connect_account"
                        )
                    ],
                    [InlineKeyboardButton("🔙 Back", callback_data="forwards")],
                ]
            ),
        )

    back = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 Back", callback_data="forwards")]]
    )

    try:
        ask = await message.message.chat.ask(
            "📥 **Source**\n\n"
            "Send the chat you want to copy from:\n"
            "• @username\n"
            "• chat / user id\n"
            "• or forward any message from that chat\n\n"
            "The connected account must be able to see that chat.\n\n"
            "/cancel to cancel"
        )
    except Exception as e:
        return await message.message.reply_text(f"🚫 Error: {e}", reply_markup=back)

    if ask.text and ask.text.strip().lower() == "/cancel":
        return await ask.reply("❌ Cancelled", reply_markup=back)

    source_ref = parse_chat_ref(ask)
    if source_ref is None:
        return await ask.reply("⚠️ Invalid source. Try again.", reply_markup=back)

    source = await resolve_chat(app, source_ref)
    if not source:
        return await ask.reply(
            "⚠️ Could not find that source.\n"
            "Join the chat with the connected account and try again.",
            reply_markup=back,
        )

    try:
        ask = await message.message.chat.ask(
            "📤 **Destination**\n\n"
            "Send the chat you want to copy to:\n"
            "• @username\n"
            "• chat / user id\n"
            "• or forward any message from that chat\n\n"
            "The connected account must be able to post there.\n\n"
            "/cancel to cancel"
        )
    except Exception as e:
        return await message.message.reply_text(f"🚫 Error: {e}", reply_markup=back)

    if ask.text and ask.text.strip().lower() == "/cancel":
        return await ask.reply("❌ Cancelled", reply_markup=back)

    dest_ref = parse_chat_ref(ask)
    if dest_ref is None:
        return await ask.reply("⚠️ Invalid destination. Try again.", reply_markup=back)

    dest = await resolve_chat(app, dest_ref)
    if not dest:
        return await ask.reply(
            "⚠️ Could not find that destination.\n"
            "Join the chat with the connected account and try again.",
            reply_markup=back,
        )

    source_name = chat_title(source)
    dest_name = chat_title(dest)

    await db.user_forwards.create(
        user_id=user_id,
        source_id=source.id,
        source_title=source_name,
        dest_id=dest.id,
        dest_title=dest_name,
    )
    await refresh_active_sources()

    text = (
        f"✅ Forward added\n\n"
        f"**From:** {source_name} (`{source.id}`)\n"
        f"**To:** {dest_name} (`{dest.id}`)\n"
    )

    return await message.message.reply_text(text, reply_markup=back)


@Client.on_callback_query(filters.regex(r"^view_forward "))
async def view_forward(_, message: CallbackQuery):
    _id = ObjectId(message.data.split()[1])
    row = await db.user_forwards.filter_document({"_id": _id})
    if not row or row["user_id"] != message.from_user.id:
        return await message.answer("Not found", show_alert=True)

    text = "**Forward details**\n\n"
    text += f"📥 Source: {row['source_title']}\n"
    text += f"   `{row['source_id']}`\n"
    text += f"📤 Destination: {row['dest_title']}\n"
    text += f"   `{row['dest_id']}`\n"
    text += f"📊 Status: {'✅ Active' if row['status'] else '❌ Inactive'}\n"

    buttons = [
        [
            InlineKeyboardButton(
                "🔒 Disable" if row["status"] else "🔓 Enable",
                callback_data=f"toggle_forward {_id}",
            ),
            InlineKeyboardButton(
                "🗑️ Delete", callback_data=f"delete_forward {_id}"
            ),
        ],
    ]
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="forwards")])

    await message.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))


@Client.on_callback_query(filters.regex(r"^delete_forward "))
async def delete_forward(_, message: CallbackQuery):
    _id = message.data.split()[1]
    return await message.edit_message_text(
        "⚠️ Delete this forward?",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Yes", callback_data=f"confirm_delete_forward {_id}"
                    ),
                    InlineKeyboardButton("❌ No", callback_data="forwards"),
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
        return await message.answer("Not found", show_alert=True)

    await db.user_forwards.update(ObjectId(_id), {"status": not row["status"]})
    await refresh_active_sources()
    message.data = f"view_forward {_id}"
    await view_forward(bot, message)
