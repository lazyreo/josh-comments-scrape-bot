from datetime import datetime

from database.core import Core


class TransfersDB(Core):
    "Users ongoing transfers"

    def __init__(self, uri, database_name):
        super().__init__(uri, database_name, "transfers")

    async def create(self, user_id, download_id, links, link_index, status, **kwargs):
        user_id = int(user_id)
        res = {
            "_id": download_id,
            "user_id": user_id,
            "links": links,
            "link_index": link_index,
            "status": status,
            "created_at": datetime.now(),
            **kwargs,
        }
        return await super().create(res)
