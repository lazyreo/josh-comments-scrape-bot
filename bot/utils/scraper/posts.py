from pyrogram import Client

from bot.utils.scraper.helpers import floodwait_aiter
from database import db


def discussion_chat_id(chat) -> int | None:
    linked = getattr(chat, "linked_chat", None)
    if linked is not None:
        return linked.id
    return getattr(chat, "linked_chat_id", None)


def _post_replies(post):
    replies = getattr(post, "replies", None)
    if replies is None:
        raw_post = getattr(post, "raw", None)
        replies = getattr(raw_post, "replies", None) if raw_post else None
    return replies


def has_comments(post) -> bool:
    replies = _post_replies(post)
    return bool(replies and getattr(replies, "replies", 0))


async def collect_commented_posts(bot: Client, app: Client, chat) -> list[int]:
    post_ids: list[int] = []
    async for post in floodwait_aiter(bot, app.get_chat_history(chat.id)):
        if not has_comments(post):
            continue
        post_ids.append(post.id)
        await db.posts.create(chat.id, post.id)
    return post_ids
