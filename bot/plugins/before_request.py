from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message

from bot.utils.helpers import get_admins


@Client.on_message(filters.incoming & filters.private, group=-1)
@Client.on_callback_query(group=-1)
async def before_request(_: Client, update: Message | CallbackQuery):
    """Block non-admins before other handlers run."""
    user = getattr(update, "from_user", None)
    if not user:
        update.stop_propagation()


    admins = await get_admins()
    if user.id not in admins:
        update.stop_propagation()
