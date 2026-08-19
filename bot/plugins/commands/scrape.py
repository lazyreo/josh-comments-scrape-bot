import asyncio
import logging
import re
from contextlib import suppress
from datetime import datetime, timedelta, timezone

from pyrogram import Client, filters
from pyrogram.enums import UserStatus
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, User
from pyromod.exceptions import ListenerStopped
from pyromod.types import ListenerTypes

from bot.config import settings
from bot.utils import (
    check_admin,
    get_link_parts,
    get_user_client,
    is_input_cancelled,
)
from bot.utils.chat_resolve import parse_chat_ref, resolve_chat
from database import db

logger = logging.getLogger(__name__)

COMMENT_BATCH_SIZE = 500
GET_USERS_LIMIT = 200
POST_SLEEP_SECONDS = 2
ACTIVE_WITHIN = timedelta(days=7)
_ACTIVE_STATUSES = {
    UserStatus.ONLINE,
    UserStatus.RECENTLY,
    UserStatus.LAST_WEEK,
}
_INACTIVE_STATUSES = {
    UserStatus.LAST_MONTH,
    UserStatus.LONG_AGO,
    UserStatus.OFFLINE,
}

_MODE_MARKUP = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("All", callback_data="scrape_mode_all"),
            InlineKeyboardButton("Selected", callback_data="scrape_mode_selected"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="scrape_mode_cancel")],
    ]
)


def _link_chat_matches(chat, link_chat_id) -> bool:
    if isinstance(link_chat_id, int):
        return chat.id == link_chat_id
    name = str(link_chat_id).lstrip("@").lower()
    username = (getattr(chat, "username", None) or "").lower()
    return bool(username) and username == name


def parse_post_tokens(text: str, chat) -> tuple[list[int], list[str]]:
    post_ids: list[int] = []
    invalid: list[str] = []
    seen: set[int] = set()

    for token in re.split(r"[\s,]+", text):
        if not token:
            continue
        if token.isdigit():
            post_id = int(token)
            if post_id not in seen:
                seen.add(post_id)
                post_ids.append(post_id)
            continue

        parts = get_link_parts(token)
        if parts and _link_chat_matches(chat, parts[0]):
            post_id = parts[1]
            if post_id not in seen:
                seen.add(post_id)
                post_ids.append(post_id)
            continue

        invalid.append(token)

    return post_ids, invalid


@Client.on_message(
    filters.command("scrape") & filters.private & filters.incoming
)
@check_admin
async def scrape(bot: Client, message: Message):
    user_id = message.from_user.id
    app = await get_user_client(user_id)

    if not app or not app.is_connected:
        settings.CLIENTS.pop(app.me.id, None) if app and app.me else None
        return await message.reply_text(
            "⚠️ You need to log in first to use this feature.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔗 Log in", callback_data="connect_account")]]
            ),
        )

    ask = await message.chat.ask(
        "Send the group or channel **id or username** to scrape comments from.\n\n"
        "Example:\n"
        "• `@channel`\n"
        "• `-1001234567890`\n\n"
        "/cancel to cancel ❌"
    )
    if await is_input_cancelled(ask):
        return

    chat_ref = parse_chat_ref(ask)
    if chat_ref is None:
        return await message.reply_text(
            "⚠️ Send a group or channel id, username, or forward a message from that chat."
        )

    chat = await resolve_chat(app, chat_ref)
    if not chat:
        return await message.reply_text(
            "⚠️ Could not access that chat.\n"
            "Join it with the connected account and try again."
        )

    try:
        choice = await message.chat.ask(
            "Choose what to scrape:\n\n"
            "• **All** — every post with comments\n"
            "• **Selected** — specific post ids or links",
            filters=filters.regex(r"^scrape_mode_(all|selected|cancel)$"),
            listener_type=ListenerTypes.CALLBACK_QUERY,
            user_id=user_id,
            reply_markup=_MODE_MARKUP,
        )
    except ListenerStopped:
        return await message.reply_text("❌ Operation cancelled.")
    except Exception as e:
        return await message.reply_text(f"🚫 Error: {e}")

    await choice.answer()
    if choice.data == "scrape_mode_cancel":
        await choice.message.edit_text("❌ Operation cancelled.")
        return

    mode = "all" if choice.data == "scrape_mode_all" else "selected"
    try:
        await choice.message.edit_reply_markup(None)
    except Exception:
        pass

    post_ids = None
    if mode == "selected":
        ask = await message.chat.ask(
            "Send post ids and/or links, separated by spaces or commas.\n\n"
            "Example:\n"
            "1 2 3\n"
            "https://t.me/channel/12, https://t.me/c/1234567890/45\n\n"
            "/cancel to cancel ❌"
        )
        if await is_input_cancelled(ask):
            return

        raw = (ask.text or "").strip()
        if not raw:
            return await message.reply_text(
                "⚠️ Send post ids and/or links, separated by spaces or commas."
            )

        post_ids, invalid = parse_post_tokens(raw, chat)
        if invalid:
            await message.reply_text(
                f"⚠️ Invalid tokens (skipped): {', '.join(invalid)}"
            )
        if not post_ids:
            return await message.reply_text("❌ No valid post ids found.")

    await run_scrape(bot, message, app, chat, post_ids)


def _post_replies(post):
    replies = getattr(post, "replies", None)
    if replies is None:
        raw = getattr(post, "raw", None)
        replies = getattr(raw, "replies", None) if raw else None
    return replies


def _has_comments(post) -> bool:
    replies = _post_replies(post)
    return bool(replies and getattr(replies, "replies", 0))


def _as_utc(value: int | float | datetime | UserStatus | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if getattr(value, "tzinfo", None) is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def is_active_last_7_days(user: User | None) -> bool:
    if not user:
        return False

    status = getattr(user, "status", None)
    if status is None:
        return False
    if status in _INACTIVE_STATUSES:
        return False
    if status in _ACTIVE_STATUSES:
        return True

    was_online = getattr(user, "last_online_date", None)
    was_online = _as_utc(was_online)
    if not was_online:
        return False
    return was_online >= datetime.now(timezone.utc) - ACTIVE_WITHIN


def _progress_text(processed: int, total: int, comments_processed: int, qualifying: int) -> str:
    return (
        "Scraping started...\n"
        f"Posts processed: {processed} / {total}\n"
        f"Comments processed: {comments_processed:,}\n"
        f"Qualifying users: {qualifying:,}"
    )


async def _edit_progress(status: Message, processed, total, comments_processed, qualifying):
    with suppress(Exception):
        await status.edit_text(
            _progress_text(processed, total, comments_processed, qualifying)
        )


async def collect_commented_posts(app: Client, chat) -> list[int]:
    post_ids: list[int] = []
    async for post in app.get_chat_history(chat.id):
        if not _has_comments(post):
            continue
        post_ids.append(post.id)
        await db.posts.create(chat.id, post.id)
    return post_ids


async def fetch_users(app: Client, user_ids: list[int]) -> list[User]:
    users: list[User] = []
    for i in range(0, len(user_ids), GET_USERS_LIMIT):
        chunk = user_ids[i : i + GET_USERS_LIMIT]
        try:
            result = await app.get_users(chunk)
            if isinstance(result, User):
                result = [result]
            users.extend(u for u in result if isinstance(u, User))
        except Exception as e:
            logger.warning("Batch get_users failed (%s), retrying one by one", e)
            for user_id in chunk:
                try:
                    user = await app.get_users(user_id)
                    if isinstance(user, User):
                        users.append(user)
                except Exception as err:
                    logger.debug("get_users(%s) failed: %s", user_id, err)
    return users


async def save_qualifying_user(user: User, source_chat, csv_rows: dict):
    if user.id in csv_rows:
        return
    await db.commented_users.upsert_user(
        user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        is_premium=bool(user.is_premium),
        source_chat=source_chat,
    )
    csv_rows[user.id] = {
        "telegram_id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_bot": bool(user.is_bot),
        "is_premium": bool(user.is_premium),
        "source_chat": source_chat,
    }


async def process_comment_batch(
    app: Client,
    chat_id,
    post_id: int,
    comments: list,
    seen_on_post: set[int],
    activity_cache: dict[int, bool],
    csv_rows: dict,
):
    new_ids: list[int] = []
    for comment in comments:
        user = comment.from_user
        if not user:
            continue
        await db.comments.create(chat_id, comment.id, post_id, user.id)
        if user.id in seen_on_post:
            continue
        seen_on_post.add(user.id)
        if user.id not in activity_cache:
            new_ids.append(user.id)

    if not new_ids:
        return

    fetched = await fetch_users(app, new_ids)
    by_id = {user.id: user for user in fetched}
    for user_id in new_ids:
        user = by_id.get(user_id)
        active = is_active_last_7_days(user)
        activity_cache[user_id] = active
        if active and user:
            await save_qualifying_user(user, chat_id, csv_rows)


async def scrape_post_comments(
    app: Client,
    chat_id,
    post_id: int,
    activity_cache: dict[int, bool],
    csv_rows: dict,
) -> int:
    batch: list = []
    seen_on_post: set[int] = set()
    comments_processed = 0

    async for comment in app.get_discussion_replies(chat_id, post_id):
        batch.append(comment)
        if len(batch) < COMMENT_BATCH_SIZE:
            continue
        comments_processed += len(batch)
        await process_comment_batch(
            app, chat_id, post_id, batch, seen_on_post, activity_cache, csv_rows
        )
        batch = []

    if batch:
        comments_processed += len(batch)
        await process_comment_batch(
            app, chat_id, post_id, batch, seen_on_post, activity_cache, csv_rows
        )

    return comments_processed


async def run_scrape(
    bot: Client,
    message: Message,
    app: Client,
    chat,
    post_ids: list[int] | None,
):
    status = await message.reply_text("Scraping started...")
    chat_id = chat.id

    if post_ids is None:
        try:
            post_ids = await collect_commented_posts(app, chat)
        except Exception as e:
            logger.exception("Failed to collect posts from %s", chat_id)
            with suppress(Exception):
                await status.edit_text(f"⚠️ Failed to fetch posts: {e}")
            return
    else:
        for post_id in post_ids:
            await db.posts.create(chat_id, post_id)

    total = len(post_ids)
    comments_processed = 0
    csv_rows: dict = {}
    activity_cache: dict[int, bool] = {}
    failed: list[dict] = []

    await _edit_progress(status, 0, total, 0, 0)

    for index, post_id in enumerate(post_ids, start=1):
        try:
            comments_processed += await scrape_post_comments(
                app, chat_id, post_id, activity_cache, csv_rows
            )
        except Exception as e:
            logger.exception("Failed to scrape post %s in chat %s", post_id, chat_id)
            failed.append({"post_id": post_id, "error": str(e)})

        await _edit_progress(
            status, index, total, comments_processed, len(csv_rows)
        )
        if index < total:
            await asyncio.sleep(POST_SLEEP_SECONDS)

    logger.info(
        "Scrape of %s finished: %s qualifying users, failed posts %s",
        chat_id,
        len(csv_rows),
        [item["post_id"] for item in failed],
    )
