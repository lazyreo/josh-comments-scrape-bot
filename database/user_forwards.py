from database.core import Core
from pyrogram.types import Message

class UserForwardsDatabase(Core):
    def __init__(self, uri, database_name):
        super().__init__(uri, database_name, "user_forwards")

    async def create(
        self,
        user_id: int,
        source_id: int,
        source_title: str,
        dest_id: int,
        dest_title: str,
        text_replacements: list | None = None,
        source_topic_id: int | None = None,
        dest_topic_id: int | None = None,
    ):
        return await super().create(
            {
                "user_id": user_id,
                "source_id": source_id,
                "source_title": source_title,
                "source_topic_id": source_topic_id,
                "dest_id": dest_id,
                "dest_title": dest_title,
                "dest_topic_id": dest_topic_id,
                "status": True,
                "text_replacements": text_replacements or [],
            }
        )
