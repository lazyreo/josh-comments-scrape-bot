from bot.config import settings

from .config import ConfigDB
from .transfers import TransfersDB
from .user_forwards import UserForwardsDatabase
from .users import UserDatabase


class Database:
    def __init__(self):
        self.users = UserDatabase(settings.DATABASE_URL, settings.DATABASE_NAME)
        self.config = ConfigDB(settings.DATABASE_URL, settings.DATABASE_NAME)
        self.user_forwards = UserForwardsDatabase(
            settings.DATABASE_URL, settings.DATABASE_NAME
        )
        self.transfers = TransfersDB(settings.DATABASE_URL, settings.DATABASE_NAME)


db = Database()
