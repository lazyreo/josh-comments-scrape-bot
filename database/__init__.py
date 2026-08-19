from bot.config import settings

from .commented_users import CommentedUsers
from .comments import CommentsDB
from .config import ConfigDB
from .posts import PostsDB
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
        self.commented_users = CommentedUsers(
            settings.DATABASE_URL, settings.DATABASE_NAME
        )
        self.posts = PostsDB(settings.DATABASE_URL, settings.DATABASE_NAME)
        self.comments = CommentsDB(settings.DATABASE_URL, settings.DATABASE_NAME)


db = Database()
