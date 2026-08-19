from database.core import Core


class CommentsDB(Core):
    def __init__(self, uri, database_name):
        super().__init__(uri, database_name, "comments")

    @staticmethod
    def make_id(chat_id, comment_id):
        return f"{chat_id}_{comment_id}"

    async def create(self, chat_id, comment_id, post_id, user_id):
        _id = self.make_id(chat_id, comment_id)
        existing = await self.read(_id)
        if existing:
            return existing["_id"]
        return await super().create(
            {
                "_id": _id,
                "chat_id": chat_id,
                "post_id": post_id,
                "user_id": user_id,
            }
        )
