"""Active forward source cache for session auto-listen filters."""

from bot.config import settings
from database import db


async def refresh_active_sources() -> set:
    """Reload active source chat ids from Mongo into settings.ACTIVE_SOURCE_IDS."""
    docs = await db.user_forwards.filter_documents({"status": True})
    settings.ACTIVE_SOURCE_IDS = {doc["source_id"] for doc in docs}
    return settings.ACTIVE_SOURCE_IDS


def is_active_source_chat(_, __, message) -> bool:
    chat = getattr(message, "chat", None)
    if not chat:
        return False
    return chat.id in settings.ACTIVE_SOURCE_IDS
