from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from tabulate import tabulate

from database import db


@Client.on_callback_query(filters.regex(r"^settings"))
@Client.on_message(filters.command("settings") & filters.private & filters.incoming)
async def settings(bot: Client, query: CallbackQuery):
    key = "settings"
    user = await db.users.read(query.from_user.id)

    forwards_count = await db.user_forwards.count_documents(
        {"user_id": query.from_user.id}
    )

    session_username = (
        f'@{user["session"]["username"]}'
        if user["session"]["username"]
        else "No username"
    )

    markup = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("👤 My account", callback_data="connected_account")],
            [InlineKeyboardButton("🔀 Forwards", callback_data="forwards")],
            [InlineKeyboardButton("🔙 Back", callback_data="start")],
        ]
    )
    text = get_settings_table(query, session_username, forwards_count)

    await bot.reply(query, text=text, key=key, reply_markup=markup)


def get_settings_table(query, session_username, forwards_count):
    table_data = [
        ["User", query.from_user.first_name],
        ["Session", session_username],
        ["User ID", f"{query.from_user.id}"],
        ["Forwards", forwards_count],
    ]

    header_text = "Settings\n\n"
    table = tabulate(
        table_data,
        tablefmt="grid",
        headers=["Option", "Status"],
        colalign=("left", "right"),
    )
    table = "`" + table + "`"

    extra_info = (
        "\n\nLog in with your account, then add a Source → Destination forward.\n"
    )

    return header_text + table + extra_info
