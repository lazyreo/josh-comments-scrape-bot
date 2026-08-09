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
        await message.reply_text("❌ Link de origem inválido")
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
            "❌ Nenhum encaminhamento encontrado para esta origem.\n"
            "Adicione um em Encaminhamentos primeiro."
        )
        return None

    if len(source_configs) == 1:
        row = source_configs[0]
        return {"source": row["source_id"], "dest": row["dest_id"]}

    text = f"📍 Encontrados {len(source_configs)} destinos para esta origem.\n\n"
    text += "Destinos disponíveis:\n"
    for i, row in enumerate(source_configs, 1):
        text += f"{i}. {row['dest_title']} (`{row['dest_id']}`)\n"
    text += "\nEnvie o ID do destino (copie e cole de cima):\n\n"
    text += "/cancel para cancelar ❌"

    ask = await message.chat.ask(text)

    if not ask or not ask.text:
        return None

    if ask.text.lower() in ["/cancel", "cancel"]:
        return None

    try:
        dest_chat_id = int(ask.text.strip())
    except ValueError:
        await message.reply_text("❌ ID de destino inválido.")
        return None

    for row in source_configs:
        if row.get("dest_id") == dest_chat_id:
            return {"source": row["source_id"], "dest": row["dest_id"]}

    await message.reply_text(f"❌ Nenhum encaminhamento para o destino: {dest_chat_id}")
    return None
