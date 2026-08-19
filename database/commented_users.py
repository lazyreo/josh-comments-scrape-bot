from database.core import Core


class CommentedUsers(Core):
    def __init__(self, uri, database_name):
        super().__init__(uri, database_name, "CommentedUsers")

    async def create(
        self,
        user_id,
        username=None,
        first_name=None,
        last_name=None,
        is_premium=False,
        source_chat=None,
        source_post_link=None,
    ):
        return await super().create(
            {
                "_id": user_id,
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "is_premium": is_premium,
                "source_chat": source_chat,
                "source_post_link": source_post_link,
            }
        )

    async def upsert_user(
        self,
        user_id,
        username=None,
        first_name=None,
        last_name=None,
        is_premium=False,
        source_chat=None,
        source_post_link=None,
    ):
        existing = await self.read(user_id)
        if existing:
            return existing["_id"]
        return await self.create(
            user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            is_premium=is_premium,
            source_chat=source_chat,
            source_post_link=source_post_link,
        )
