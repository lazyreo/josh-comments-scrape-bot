from pyrogram import Client, filters, types

from bot.utils import check_admin
from database import db


@Client.on_message(filters.command("users", prefixes="/") & filters.incoming)
@Client.on_callback_query(filters.regex(pattern=r"^users"))
@check_admin
async def users(client, message):
    page = 1
    if isinstance(message, types.CallbackQuery):
        if len(message.data.split()) == 2:
            page = int(message.data.split()[1])

    users_list = await db.users.filter_documents({})
    user_ids = [user["_id"] for user in users_list]
    if users_list:
        tg_users = await client.get_users(user_ids, raise_error=False)

        # Pagination logic
        per_page = 20  # Number of users per page
        start_index = (page - 1) * per_page
        end_index = start_index + per_page
        paginated_users = tg_users[start_index:end_index]

        users = ""
        for user in paginated_users:
            if isinstance(user, types.User):
                users += f"👤 `{user.id}` - {user.mention}\n"
            else:
                users += f"🚫 `{user}` - Blocked Account\n"

        # Calculate the number of pages
        total_pages = (len(tg_users) + per_page - 1) // per_page

        # Generate pagination buttons
        buttons = []
        if page > 1:
            buttons.append(
                types.InlineKeyboardButton("⬅️ Back", callback_data=f"users {page - 1}")
            )
        if page < total_pages:
            buttons.append(
                types.InlineKeyboardButton("➡️ Next", callback_data=f"users {page + 1}")
            )
        buttons.append(
            types.InlineKeyboardButton(f"Page {page}/{total_pages}", callback_data="1")
        )
        buttons = [buttons]
        buttons.append([types.InlineKeyboardButton("🔙 Back", callback_data="users 1")])

        # Create inline keyboard markup
        keyboard = types.InlineKeyboardMarkup(buttons)
        func = (
            message.edit_message_text
            if isinstance(message, types.CallbackQuery)
            else message.reply_text
        )
        await func(
            f"**Total Users:**\n\n{users}\n**Total Users Count:** {len(users_list)}",
            reply_markup=keyboard,
        )

    else:
        await message.reply_text("**Total Users:**\n\nNo Users")
