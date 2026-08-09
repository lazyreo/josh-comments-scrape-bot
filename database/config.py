from database.core import Core


class ConfigDB(Core):
    def __init__(self, uri, database_name):
        super().__init__(uri, database_name, "config")

    async def add_config(self, name, value):
        item = {
            "name": name,
            "value": value,
        }
        return await self.create(item)

    async def get_config(self, name):
        return await self.col.find_one({"name": name})

    async def delete_config(self, name):
        return await self.col.delete_one({"name": name})

    async def update_config(self, name, value):
        return await self.col.update_one({"name": name}, {"$set": {"value": value}})

    # get or create config
    async def get_or_create_config(self, name, value):
        config = await self.get_config(name)
        if config:
            return config
        else:
            await self.add_config(name, value)
            return {"name": name, "value": value}
