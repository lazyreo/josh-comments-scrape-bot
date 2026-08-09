from motor.motor_asyncio import AsyncIOMotorClient


class Core:
    def __init__(self, uri, database_name, col):
        self._client = AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.col = self.db[col]

    async def create(self, document):
        result = await self.col.insert_one(document)
        return result.inserted_id

    async def read(self, _id):
        document = await self.col.find_one({"_id": _id})
        return document

    async def update(self, _id, query, tag="set"):
        result = await self.col.update_one({"_id": _id}, {f"${tag}": query})
        return result.modified_count

    async def delete(self, _id):
        result = await self.col.delete_one({"_id": _id})
        return result.deleted_count

    async def count_documents(self, query=None):
        if query is None:
            query = {}
        count = await self.col.count_documents(query)
        return count

    async def filter_documents(self, query={}, limit=None, skip=0, sort=None):
        cursor = self.col.find(query).skip(skip)

        if sort:
            cursor = cursor.sort(sort)

        documents = await cursor.to_list(length=limit)
        return documents

    async def filter_document(self, query):
        document = await self.col.find_one(query)
        return document

    async def delete_many(self, query):
        result = await self.col.delete_many(query)
        return result.deleted_count
