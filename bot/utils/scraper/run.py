import asyncio
import logging
from contextlib import suppress

from pyrogram import Client
from pyrogram.types import Chat, Message

from bot.config import settings
from bot.utils.scraper.comments import scrape_post_comments
from bot.utils.scraper.export import finish_scrape
from bot.utils.scraper.links import build_post_link
from bot.utils.scraper.posts import collect_commented_posts, discussion_chat_id
from bot.utils.scraper.progress import edit_progress
from database import db

logger = logging.getLogger(__name__)


async def run_scrape(
    bot: Client,
    message: Message,
    app: Client,
    chat: Chat,
    post_ids: list[int] | None,
    post_link_by_id: dict[int, str] | None = None,
):
    post_sleep_seconds = max(0.0, float(settings.SCRAPE_POST_SLEEP_SECONDS))
    status = await message.reply_text("Scraping started...")
    chat_id = chat.id
    linked_discussion_id = discussion_chat_id(chat)
    post_links = post_link_by_id or {}

    if post_ids is None:
        try:
            post_ids = await collect_commented_posts(bot, app, chat)
        except Exception as e:
            logger.exception("Failed to collect posts from %s", chat_id)
            with suppress(Exception):
                await bot.floodwait_handler(
                    status.edit_text, f"⚠️ Failed to fetch posts: {e}"
                )
            return
    else:
        for post_id in post_ids:
            await db.posts.create(chat_id, post_id)

    total = len(post_ids)
    comments_processed = 0
    reactions_processed = 0
    csv_rows: dict = {}
    activity_cache: dict[int, bool] = {}
    failed: list[dict] = []
    await asyncio.sleep(0.5)
    await bot.floodwait_handler(edit_progress, status, 0, total, 0, 0, 0)

    for index, post_id in enumerate(post_ids, start=1):
        source_post_link = post_links.get(post_id) or build_post_link(chat, post_id)
        try:
            post_comments, post_reactions = await scrape_post_comments(
                bot,
                app,
                chat_id,
                post_id,
                activity_cache,
                csv_rows,
                source_post_link,
                linked_discussion_id,
            )
            comments_processed += post_comments
            reactions_processed += post_reactions
        except Exception as e:
            logger.exception(
                "Failed to scrape comments for post %s in chat %s", post_id, chat_id
            )
            failed.append({"post_id": post_id, "error": str(e)})

        await bot.floodwait_handler(
            edit_progress,
            status,
            index,
            total,
            comments_processed,
            reactions_processed,
            len(csv_rows),
        )
        if index < total:
            await asyncio.sleep(post_sleep_seconds)

    logger.info(
        "Scrape of %s finished: %s qualifying users, %s comment reactions, failed posts %s",
        chat_id,
        len(csv_rows),
        reactions_processed,
        [item["post_id"] for item in failed],
    )
    await finish_scrape(bot, message, status, csv_rows, failed)
