from database.core import Core


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
        emails: list | None = None,
    ):
        return await super().create(
            {
                "user_id": user_id,
                "source_id": source_id,
                "source_title": source_title,
                "dest_id": dest_id,
                "dest_title": dest_title,
                "emails": emails or [],
                "status": True,
            }
        )
