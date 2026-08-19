from database.core import Core


class PostsDB(Core):
    def __init__(self, uri, database_name):
        super().__init__(uri, database_name, "posts")

    @staticmethod
    def make_id(chat_id, post_id):
        return f"{chat_id}_{post_id}"

    async def create(self, chat_id, post_id):
        _id = self.make_id(chat_id, post_id)
        existing = await self.read(_id)
        if existing:
            return existing["_id"]
        return await super().create(
            {
                "_id": _id,
                "chat_id": chat_id,
                "post_id": post_id,
            }
        )
