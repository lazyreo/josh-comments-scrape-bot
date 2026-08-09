from pyrogram import Client, filters
from pyrogram.types import Message

from bot.config import settings
from bot.utils.helpers import add_admin, get_admins, remove_admin


@Client.on_message(
    filters.command("addadmin") & filters.private & filters.user(settings.OWNER_ID)
)
async def addadmin(client: Client, message: Message):
    if len(message.command) != 2:
        admins = await get_admins()
        text = "Admins:\n"
        for admin in admins:
            try:
                user = await client.get_users(admin)
                text += f" - {user.mention(style='md')} ({user.id})\n"
            except Exception:
                text += f" - {admin}\n"
        await message.reply_text(f"Usage: /addadmin user_id\n\n{text}")
        return

    user_id = message.text.split(None, 1)[1]

    if user_id.isdigit():
        user_id = int(user_id)
    else:
        user_id = user_id.replace("@", "")

    try:
        user = await client.get_users(user_id)
    except:
        await message.reply_text("Invalid user ID")
        return

    added = await add_admin(user_id)
    if added:
        await message.reply_text("Admin added successfully")
    else:
        await message.reply_text("This user is already an admin")


@Client.on_message(
    filters.command("admins") & filters.private & filters.user(settings.OWNER_ID)
)
async def admins(client: Client, message: Message):
    admins = await get_admins()
    text = "Admins:\n"
    for admin in admins:
        try:
            user = await client.get_users(admin)
            text += f" - {user.mention(style='md')} ({user.id})\n"
        except Exception:
            text += f" - {admin}\n"
    await message.reply_text(text)


@Client.on_message(
    filters.command("removeadmin") & filters.private & filters.user(settings.OWNER_ID)
)
async def removeadmin(client: Client, message: Message):
    if len(message.command) != 2:
        admins = await get_admins()
        text = "Admins:\n"
        for admin in admins:
            try:
                user = await client.get_users(admin)
                text += f" - {user.mention(style='md')} ({user.id})\n"
            except:
                text += f" - {admin}\n"
        await message.reply_text(f"Usage: /removeadmin user_id\n\n{text}")
        return
    user_id = message.text.split(None, 1)[1]
    if user_id.isdigit():
        user_id = int(user_id)
    else:
        user_id = user_id.replace("@", "")

    removed = await remove_admin(user_id)
    if removed:
        await message.reply_text("Admin removed successfully")
    else:
        await message.reply_text("This user is not an admin")
