import asyncio

from pyrogram import Client

from bot.config import settings
from bot.utils.scraper.activity import is_active_last_4_days
from bot.utils.scraper.constants import COMMENT_BATCH_SLEEP_SECONDS
from bot.utils.scraper.helpers import floodwait_aiter
from bot.utils.scraper.reactions import message_has_reactions, scrape_message_reactions
from bot.utils.scraper.users import (
    fetch_users,
    resolve_comment_user,
    save_qualifying_user,
)
from database import db


async def process_comment_batch(
    bot: Client,
    app: Client,
    chat_id,
    post_id: int,
    comments: list,
    seen_on_post: set[int],
    activity_cache: dict[int, bool],
    csv_rows: dict,
    source_post_link: str,
    discussion_chat_id: int | None = None,
) -> int:
    new_ids: list[int] = []
    reactions_processed = 0

    for comment in comments:
        user = await resolve_comment_user(bot, app, comment, discussion_chat_id)
        if user:
            await db.comments.create(chat_id, comment.id, post_id, user.id)
            if user.id not in seen_on_post:
                seen_on_post.add(user.id)
                if user.id not in activity_cache:
                    new_ids.append(user.id)

        if not message_has_reactions(comment):
            continue

        reaction_chat_id = getattr(getattr(comment, "chat", None), "id", None)
        if reaction_chat_id is None:
            reaction_chat_id = discussion_chat_id
        if reaction_chat_id is None:
            continue

        reactions_processed += await scrape_message_reactions(
            bot,
            app,
            reaction_chat_id,
            comment.id,
            chat_id,
            activity_cache,
            csv_rows,
            source_post_link,
        )

    if new_ids:
        fetched = await fetch_users(bot, app, new_ids)
        by_id = {user.id: user for user in fetched}
        for user_id in new_ids:
            user = by_id.get(user_id)
            active = is_active_last_4_days(user)
            activity_cache[user_id] = active
            if active and user:
                await save_qualifying_user(user, chat_id, source_post_link, csv_rows)

    return reactions_processed


async def scrape_post_comments(
    bot: Client,
    app: Client,
    chat_id,
    post_id: int,
    activity_cache: dict[int, bool],
    csv_rows: dict,
    source_post_link: str,
    discussion_chat_id: int | None = None,
) -> tuple[int, int]:
    comment_batch_size = max(1, int(settings.SCRAPE_COMMENT_BATCH_SIZE))
    batch: list = []
    seen_on_post: set[int] = set()
    comments_processed = 0
    reactions_processed = 0

    async for comment in floodwait_aiter(
        bot, app.get_discussion_replies(chat_id, post_id)
    ):
        batch.append(comment)
        if len(batch) < comment_batch_size:
            continue
        comments_processed += len(batch)
        reactions_processed += await process_comment_batch(
            bot,
            app,
            chat_id,
            post_id,
            batch,
            seen_on_post,
            activity_cache,
            csv_rows,
            source_post_link,
            discussion_chat_id,
        )
        batch = []
        if COMMENT_BATCH_SLEEP_SECONDS > 0:
            await asyncio.sleep(COMMENT_BATCH_SLEEP_SECONDS)

    if batch:
        comments_processed += len(batch)
        reactions_processed += await process_comment_batch(
            bot,
            app,
            chat_id,
            post_id,
            batch,
            seen_on_post,
            activity_cache,
            csv_rows,
            source_post_link,
            discussion_chat_id,
        )

    return comments_processed, reactions_processed
