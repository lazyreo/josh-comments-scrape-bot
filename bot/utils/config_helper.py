"""Resolve per-user Source → Destination config from a pasted message link."""

from typing import Any, Dict, Optional

from pyrogram.types import Message

from bot.utils.helpers import get_link_parts
from database import db

__all__ = ["get_config_from_dest_link"]


async def get_config_from_dest_link(
    message: Message, link: str
) -> Optional[Dict[str, Any]]:
    """
    Find active forward(s) for this user whose source matches the link.
    If only one destination exists, return it. If several, ask which dest.
    """
    parts = get_link_parts(link)
    if not parts:
        await message.reply_text("❌ Invalid source link")
        return None

    source_chat_id = parts[0]
    user_id = message.from_user.id

    source_configs = await db.user_forwards.filter_documents(
        {
            "user_id": user_id,
            "source_id": source_chat_id,
            "status": True,
        }
    )

    if not source_configs:
        await message.reply_text(
            "❌ No forward found for this source.\n"
            "Add one under Forwards first."
        )
        return None

    if len(source_configs) == 1:
        row = source_configs[0]
        return {"source": row["source_id"], "dest": row["dest_id"]}

    text = f"📍 Found {len(source_configs)} destinations for this source.\n\n"
    text += "Available destinations:\n"
    for i, row in enumerate(source_configs, 1):
        text += f"{i}. {row['dest_title']} (`{row['dest_id']}`)\n"
    text += "\nSend the destination ID (copy and paste from above):\n\n"
    text += "/cancel to cancel ❌"

    ask = await message.chat.ask(text)

    if not ask or not ask.text:
        return None

    if ask.text.lower() in ["/cancel", "cancel"]:
        return None

    try:
        dest_chat_id = int(ask.text.strip())
    except ValueError:
        await message.reply_text("❌ Invalid destination ID.")
        return None

    for row in source_configs:
        if row.get("dest_id") == dest_chat_id:
            return {"source": row["source_id"], "dest": row["dest_id"]}

    await message.reply_text(f"❌ No forward for destination: {dest_chat_id}")
    return None
