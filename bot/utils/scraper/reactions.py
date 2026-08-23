import asyncio
import logging

from pyrogram import Client, raw
from pyrogram.errors import MsgIdInvalid
from pyrogram.types import Message, User

from bot.utils.scraper.activity import is_active_last_4_days
from bot.utils.scraper.constants import COMMENT_BATCH_SLEEP_SECONDS
from bot.utils.scraper.users import fetch_users, merge_reactions, save_qualifying_user

logger = logging.getLogger(__name__)


def message_has_reactions(message: Message | None) -> bool:
    """Telegram returns MSG_ID_INVALID for GetMessageReactionsList when there are none."""
    if not message:
        return False
    reactions = getattr(message, "reactions", None)
    if not reactions:
        return False
    items = getattr(reactions, "reactions", None)
    if items is not None:
        return bool(items)
    return True


def reaction_key(reaction) -> str | None:
    if isinstance(reaction, raw.types.ReactionEmoji):
        return reaction.emoticon
    if isinstance(reaction, raw.types.ReactionCustomEmoji):
        return f"custom:{reaction.document_id}"
    if isinstance(reaction, raw.types.ReactionPaid):
        return "paid"
    return None


async def scrape_message_reactions(
    bot: Client,
    app: Client,
    reaction_chat_id,
    reaction_message_id: int,
    source_chat,
    activity_cache: dict[int, bool],
    csv_rows: dict,
    source_post_link: str,
) -> int:
    peer = await bot.floodwait_handler(app.resolve_peer, reaction_chat_id)
    offset: str | None = None
    reactions_processed = 0
    pending: dict[int, dict[str, int]] = {}
    users_by_id: dict[int, User] = {}

    while True:
        logger.debug(
            "Scraping reactions for message %s in chat %s",
            reaction_message_id,
            reaction_chat_id,
        )
        try:
            result = await bot.floodwait_handler(
                app.invoke,
                raw.functions.messages.GetMessageReactionsList(
                    peer=peer,
                    id=reaction_message_id,
                    limit=100,
                    offset=offset,
                ),
            )
        except MsgIdInvalid:
            logger.debug(
                "No listable reactions for message %s in %s",
                reaction_message_id,
                reaction_chat_id,
            )
            return reactions_processed

        for raw_user in getattr(result, "users", None) or []:
            user = User._parse(app, raw_user)
            if isinstance(user, User):
                users_by_id[user.id] = user

        page = getattr(result, "reactions", None) or []
        if not page:
            break

        reactions_processed += len(page)
        for item in page:
            peer_id = getattr(item, "peer_id", None)
            if not isinstance(peer_id, raw.types.PeerUser):
                continue
            key = reaction_key(getattr(item, "reaction", None))
            if not key:
                continue
            user_reactions = pending.setdefault(peer_id.user_id, {})
            user_reactions[key] = user_reactions.get(key, 0) + 1

        offset = getattr(result, "next_offset", None) or None
        if not offset:
            break
        if COMMENT_BATCH_SLEEP_SECONDS > 0:
            await asyncio.sleep(COMMENT_BATCH_SLEEP_SECONDS)

    if not pending:
        return reactions_processed

    missing_ids = [
        user_id
        for user_id in pending
        if user_id not in csv_rows
        and user_id not in activity_cache
        and user_id not in users_by_id
    ]
    if missing_ids:
        fetched = await fetch_users(bot, app, missing_ids)
        for user in fetched:
            users_by_id[user.id] = user

    for user_id, reaction_counts in pending.items():
        if user_id in csv_rows:
            merge_reactions(
                csv_rows[user_id].setdefault("_reactions", {}), reaction_counts
            )
            continue

        if user_id in activity_cache:
            if not activity_cache[user_id]:
                continue
            user = users_by_id.get(user_id)
            if user is None:
                fetched = await fetch_users(bot, app, [user_id])
                user = fetched[0] if fetched else None
            if user:
                await save_qualifying_user(
                    user, source_chat, source_post_link, csv_rows, reaction_counts
                )
            continue

        user = users_by_id.get(user_id)
        if user is None:
            fetched = await fetch_users(bot, app, [user_id])
            user = fetched[0] if fetched else None
            if user:
                users_by_id[user.id] = user

        active = is_active_last_4_days(user)
        activity_cache[user_id] = active
        if active and user:
            await save_qualifying_user(
                user, source_chat, source_post_link, csv_rows, reaction_counts
            )

    return reactions_processed
