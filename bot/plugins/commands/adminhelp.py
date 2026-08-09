from pyrogram import Client, filters
from pyrogram.types import Message

from bot.config import settings


@Client.on_message(
    filters.command("admin") & filters.private & filters.user(settings.OWNER_ID)
)
@Client.on_callback_query(filters.regex("^admin"))
async def admin(client: Client, message: Message):
    text = """
**Admin Commands**

👥 Admins:
/addadmin - Add an admin
/admins - Get all admins
/removeadmin - Remove an admin

👤 Users:
/users - Get all users
/user - Get User Details, Ban/Unban User

📢 Others:
/broadcast - Broadcast a message to all users
"""

    await client.reply(message, text)
