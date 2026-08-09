from bot.config import Script
from database.core import Core


class UserDatabase(Core):
    def __init__(self, uri, database_name):
        super().__init__(uri, database_name, "users")

    async def create(self, user_id):
        return await super().create(
            {
                "_id": user_id,
                "banned": False,
                "session": {"string": None, "id": None, "username": None},
                "custom_caption": {"caption": Script.DEFAULT_CAPTION, "status": False},
            }
        )

    async def remove_session(self, user_id):
        return await super().update(
            user_id, {"session": {"string": None, "id": None, "username": None}}
        )
