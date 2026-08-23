import logging

from pyrogram import Client, raw
from pyrogram.types import Message, User

from database import db

logger = logging.getLogger(__name__)


def user_id_from_raw(message: Message) -> int | None:
    raw_msg = getattr(message, "raw", None)
    from_id = getattr(raw_msg, "from_id", None) if raw_msg else None
    if isinstance(from_id, raw.types.PeerUser):
        return from_id.user_id
    return None


async def resolve_comment_user(
    bot: Client,
    app: Client,
    comment: Message,
    discussion_chat_id: int | None,
) -> User | None:
    if comment.from_user:
        return comment.from_user

    user_id = user_id_from_raw(comment)
    if user_id:
        try:
            user = await bot.floodwait_handler(app.get_users, user_id)
            if isinstance(user, User):
                return user
        except Exception:
            pass

    if not discussion_chat_id:
        return None

    try:
        refetched = await bot.floodwait_handler(
            app.get_messages, discussion_chat_id, comment.id
        )
    except Exception:
        return None

    if not refetched:
        return None
    if refetched.from_user:
        return refetched.from_user

    user_id = user_id_from_raw(refetched)
    if not user_id:
        return None
    try:
        user = await bot.floodwait_handler(app.get_users, user_id)
        return user if isinstance(user, User) else None
    except Exception:
        return None


async def fetch_users(bot: Client, app: Client, user_ids: list[int]) -> list[User]:
    get_users_limit = 200
    users: list[User] = []
    for i in range(0, len(user_ids), get_users_limit):
        chunk = user_ids[i : i + get_users_limit]
        try:
            result = await bot.floodwait_handler(app.get_users, chunk)
            if isinstance(result, User):
                result = [result]
            users.extend(u for u in result if isinstance(u, User))
        except Exception as e:
            logger.warning("Batch get_users failed (%s), retrying one by one", e)
            for user_id in chunk:
                try:
                    user = await bot.floodwait_handler(app.get_users, user_id)
                    if isinstance(user, User):
                        users.append(user)
                except Exception as err:
                    logger.debug("get_users(%s) failed: %s", user_id, err)
    return users


def merge_reactions(target: dict[str, int], incoming: dict[str, int]) -> None:
    for key, count in incoming.items():
        target[key] = target.get(key, 0) + count


async def save_qualifying_user(
    user: User,
    source_chat,
    source_post_link,
    csv_rows: dict,
    reactions: dict[str, int] | None = None,
):
    reactions = reactions or {}
    if user.id in csv_rows:
        if reactions:
            merge_reactions(csv_rows[user.id].setdefault("_reactions", {}), reactions)
        return

    await db.commented_users.upsert_user(
        user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        is_premium=bool(user.is_premium),
        source_chat=source_chat,
        source_post_link=source_post_link,
    )
    csv_rows[user.id] = {
        "telegram_id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_premium": bool(user.is_premium),
        "source_chat": source_chat,
        "source_post_link": source_post_link,
        "_reactions": dict(reactions),
    }
