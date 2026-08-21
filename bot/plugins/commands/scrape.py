import asyncio
import csv
import logging
import os
import re
from contextlib import suppress
from datetime import datetime, timedelta, timezone

from bson import int64
from pyrogram import Client, filters, raw
from pyrogram.enums import ChatType, UserStatus
from pyrogram.errors import MsgIdInvalid
from pyrogram.types import (
    Chat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    User,
)
from pyromod.exceptions import ListenerStopped
from pyromod.types import ListenerTypes

from bot.config import settings
from bot.utils import (
    check_admin,
    get_link_parts,
    get_user_client,
    is_input_cancelled,
)
from bot.utils.chat_resolve import forward_post_ref, parse_chat_input, resolve_chat
from database import db

logger = logging.getLogger(__name__)

COMMENT_BATCH_SIZE = max(1, int(settings.SCRAPE_COMMENT_BATCH_SIZE))
COMMENT_BATCH_SLEEP_SECONDS = max(0.0, float(settings.SCRAPE_COMMENT_BATCH_SLEEP_SECONDS))
GET_USERS_LIMIT = 200
POST_SLEEP_SECONDS = max(0.0, float(settings.SCRAPE_POST_SLEEP_SECONDS))
ACTIVE_WITHIN = timedelta(days=4)
CSV_COLUMNS = [
    "telegram_id",
    "username",
    "first_name",
    "last_name",
    "is_premium",
    "source_chat",
    "source_post_link",
    "reaction",
    "count",
]
REACTION_LIST_LIMIT = 100
_ACTIVE_STATUSES = {
    UserStatus.ONLINE,
    UserStatus.RECENTLY,
}
_INACTIVE_STATUSES = {
    UserStatus.LAST_WEEK,
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

_SELECT_DONE = "✅ Done"
_SELECT_CANCEL = "❌ Cancel"
_SELECT_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton(_SELECT_DONE), KeyboardButton(_SELECT_CANCEL)]],
    resize_keyboard=True,
)

_POST_LINK_RE = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me|telegram\.dog)/[^\s,]+",
    re.IGNORECASE,
)


def _normalize_post_link(link: str) -> str:
    link = link.strip().rstrip(".,;)")
    if link.startswith(("http://", "https://", "tg://")):
        return link
    return f"https://{link}"


def _private_chat_slug(chat_id: int) -> str:
    text = str(chat_id)
    if text.startswith("-100"):
        return text[4:]
    if text.startswith("-"):
        return text[1:]
    return text


def build_post_link(chat_or_id, post_id: int) -> str:
    """Build a t.me post link for public or private channels/groups."""
    if isinstance(chat_or_id, int):
        return f"https://t.me/c/{_private_chat_slug(chat_or_id)}/{post_id}"

    username = getattr(chat_or_id, "username", None)
    if username:
        return f"https://t.me/{username}/{post_id}"

    return f"https://t.me/c/{_private_chat_slug(chat_or_id.id)}/{post_id}"


def _discussion_chat_id(chat) -> int | None:
    linked = getattr(chat, "linked_chat", None)
    if linked is not None:
        return linked.id
    return getattr(chat, "linked_chat_id", None)


def _message_has_reactions(message: Message | None) -> bool:
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


async def _resolve_reaction_target(
    bot: Client,
    app: Client,
    chat: Chat,
    post_id: int,
) -> tuple[int, int] | None | str:
    """Return (chat_id, message_id), None if unavailable, or 'no_reactions' to skip."""
    if chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}:
        try:
            message = await bot.floodwait_handler(app.get_messages, chat.id, post_id)
        except Exception as e:
            logger.debug(
                "Could not fetch group post %s in %s for reactions: %s",
                post_id,
                chat.id,
                e,
            )
            return None
        if isinstance(message, list):
            message = message[0] if message else None
        if not message:
            return None
        if not _message_has_reactions(message):
            return "no_reactions"
        return chat.id, post_id

    if chat.type != ChatType.CHANNEL:
        return None

    try:
        discussion = await bot.floodwait_handler(
            app.get_discussion_message, chat.id, post_id
        )
    except Exception as e:
        logger.debug(
            "No discussion message for channel %s post %s: %s",
            chat.id,
            post_id,
            e,
        )
        return None

    if not discussion or not getattr(discussion, "chat", None):
        return None
    if not _message_has_reactions(discussion):
        return "no_reactions"
    return discussion.chat.id, discussion.id


def _user_id_from_raw(message: Message) -> int | None:
    raw_msg = getattr(message, "raw", None)
    from_id = getattr(raw_msg, "from_id", None) if raw_msg else None
    if isinstance(from_id, raw.types.PeerUser):
        return from_id.user_id
    return None


async def _resolve_comment_user(
    bot: Client,
    app: Client,
    comment: Message,
    discussion_chat_id: int | None,
) -> User | None:
    if comment.from_user:
        return comment.from_user

    user_id = _user_id_from_raw(comment)
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

    user_id = _user_id_from_raw(refetched)
    if not user_id:
        return None
    try:
        user = await bot.floodwait_handler(app.get_users, user_id)
        return user if isinstance(user, User) else None
    except Exception:
        return None


def _chat_peer_id(peer) -> int | None:
    if peer is None:
        return None
    if isinstance(peer, int):
        return peer
    return getattr(peer, "id", None)


def _chat_username(peer) -> str:
    if peer is None or isinstance(peer, int):
        return ""
    return (getattr(peer, "username", None) or "").lower()


def _link_chat_matches(chat, link_chat_id) -> bool:
    other_id = _chat_peer_id(link_chat_id)
    if other_id is not None and chat.id == other_id:
        return True

    linked_id = getattr(chat, "linked_chat_id", None)
    if other_id is not None and linked_id is not None and linked_id == other_id:
        return True

    if not isinstance(link_chat_id, int):
        other_linked_id = getattr(link_chat_id, "linked_chat_id", None)
        if other_linked_id is not None and other_linked_id == chat.id:
            return True

    chat_username = _chat_username(chat)
    other_username = _chat_username(link_chat_id)
    if other_username and chat_username and other_username == chat_username:
        return True

    if isinstance(link_chat_id, str):
        name = link_chat_id.lstrip("@").lower()
        return bool(chat_username) and chat_username == name

    return False


def parse_post_tokens(
    text: str, chat
) -> tuple[list[int], list[str], dict[int, str]]:
    post_ids: list[int] = []
    invalid: list[str] = []
    post_links: dict[int, str] = {}
    seen: set[int] = set()

    links = _POST_LINK_RE.findall(text)
    remainder = _POST_LINK_RE.sub(" ", text)

    for raw_link in links:
        link = _normalize_post_link(raw_link)
        parts = get_link_parts(link)
        if not parts or not _link_chat_matches(chat, parts[0]):
            invalid.append(raw_link)
            continue
        post_id = parts[1]
        if post_id in seen:
            continue
        seen.add(post_id)
        post_ids.append(post_id)
        post_links[post_id] = link

    for token in re.split(r"[\s,]+", remainder):
        token = token.strip()
        if not token:
            continue
        if token.isdigit():
            post_id = int(token)
            if post_id not in seen:
                seen.add(post_id)
                post_ids.append(post_id)
            continue
        invalid.append(token)

    return post_ids, invalid, post_links


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
        "Send the group or channel **id or username** or **copy a message from that chat** to scrape comments from.\n\n"
        "Example:\n"
        "• `@channel`\n"
        "• `-1001234567890`\n\n"
        "• `copy a message from that chat`\n"
        "/cancel to cancel ❌"
    )
    if await is_input_cancelled(ask):
        return

    chat_ref, _ = parse_chat_input(ask)
    if chat_ref is None:
        return await message.reply_text(
            "⚠️ Send a group or channel id, username, or copy a message from that chat."
        )

    # chat = await resolve_chat(app, chat_ref)
    chat = await bot.floodwait_handler(resolve_chat, app, chat_ref)
    if not chat:        
        return await message.reply_text(
            "⚠️ Could not access that chat.\n"
            "Join it with the connected account and try again."
        )

    mode_text = (
        "Choose what to scrape:\n\n"
        "• **All** — every post with comments\n"
        "• **Selected** — specific posts, post ids or links"
    )

    try:
        choice = await message.chat.ask(
            mode_text,
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
    post_link_by_id: dict[int, str] = {}
    if mode == "selected":
        post_ids = []
        seen_post_ids: set[int] = set()
        prompt = (
            "Copy posts from this channel/group here.\n\n"
            "You can also send post IDs or links (spaces/commas OK).\n\n"
            f"Press {_SELECT_DONE} when finished, or {_SELECT_CANCEL} to abort."
        )
        first_ask = True
        while True:
            try:
                ask = await message.chat.ask(
                    prompt if first_ask else (
                        f"Copy another post, or press {_SELECT_DONE} / {_SELECT_CANCEL}.\n"
                        f"Selected so far: **{len(post_ids)}**"
                    ),
                    reply_markup=_SELECT_KEYBOARD,
                    disable_web_page_preview=True,
                )
            except ListenerStopped:
                await message.reply_text(
                    "❌ Operation cancelled.",
                    reply_markup=ReplyKeyboardRemove(),
                )
                return
            except Exception as e:
                await message.reply_text(
                    f"🚫 Error: {e}",
                    reply_markup=ReplyKeyboardRemove(),
                )
                return
            first_ask = False

            text = (ask.text or "").strip()
            if text in {_SELECT_CANCEL, "Cancel", "/cancel"}:
                await message.reply_text(
                    "❌ Operation cancelled.",
                    reply_markup=ReplyKeyboardRemove(),
                )
                return
            if text in {_SELECT_DONE, "Done"}:
                break

            new_ids: list[int] = []
            new_links: dict[int, str] = {}
            forwarded_chat, forwarded_message_id = forward_post_ref(ask)
            has_forward = (
                forwarded_chat is not None and forwarded_message_id is not None
            )
            if has_forward:
                if _link_chat_matches(chat, forwarded_chat):
                    new_ids.append(forwarded_message_id)
                    new_links[forwarded_message_id] = build_post_link(
                        forwarded_chat, forwarded_message_id
                    )
                else:
                    await message.reply_text(
                        "⚠️ That copied post is not from the selected channel/group."
                    )
                    continue

            if text and not has_forward:
                parsed_ids, invalid, parsed_links = parse_post_tokens(text, chat)
                new_ids.extend(parsed_ids)
                new_links.update(parsed_links)
                if invalid:
                    await message.reply_text(
                        f"⚠️ Invalid tokens (skipped): {', '.join(invalid)}"
                    )
                    continue
                

            added_now = 0
            noted: list[int] = []
            for post_id in new_ids:
                if post_id in seen_post_ids:
                    continue
                seen_post_ids.add(post_id)
                post_ids.append(post_id)
                post_link_by_id[post_id] = new_links.get(
                    post_id, build_post_link(chat, post_id)
                )
                noted.append(post_id)
                added_now += 1

            if not added_now:
                await message.reply_text(
                    "⚠️ No valid new post found. Copy a post from this chat, "
                    f"or press {_SELECT_DONE} / {_SELECT_CANCEL}."
                )
                continue

            noted_text = ", ".join(f"`{pid}`" for pid in noted)
            await message.reply_text(
                f"✅ Noted post(s): {noted_text}\n"
                f"Total selected: **{len(post_ids)}**",
            )

        with suppress(Exception):
            await message.reply_text(
                "Selection complete.",
                reply_markup=ReplyKeyboardRemove(),
            )
        if not post_ids:
            return await message.reply_text("❌ No valid post ids found.")

    await run_scrape(bot, message, app, chat, post_ids, post_link_by_id)


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


def is_active_last_4_days(user: User | None) -> bool:
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


def _progress_text(
    processed: int,
    total: int,
    comments_processed: int,
    reactions_processed: int,
    qualifying: int,
    reactions_skipped: int = 0,
) -> str:
    lines = [
        "Scraping started...",
        f"Posts processed: {processed} / {total}",
        f"Comments processed: {comments_processed:,}",
        f"Reactions processed: {reactions_processed:,}",
        f"Qualifying users: {qualifying:,}",
    ]
    if reactions_skipped:
        lines.append(
            f"Posts whose reactions could not be fetched: {reactions_skipped:,}"
        )
    return "\n".join(lines)


def _reaction_key(reaction) -> str | None:
    if isinstance(reaction, raw.types.ReactionEmoji):
        return reaction.emoticon
    if isinstance(reaction, raw.types.ReactionCustomEmoji):
        return f"custom:{reaction.document_id}"
    if isinstance(reaction, raw.types.ReactionPaid):
        return "paid"
    return None


def _merge_reactions(target: dict[str, int], incoming: dict[str, int]) -> None:
    for key, count in incoming.items():
        target[key] = target.get(key, 0) + count


def _csv_row(row: dict) -> dict:
    reactions = row.get("_reactions") or {}
    return {
        "telegram_id": row.get("telegram_id"),
        "username": row.get("username"),
        "first_name": row.get("first_name"),
        "last_name": row.get("last_name"),
        "is_premium": row.get("is_premium"),
        "source_chat": row.get("source_chat"),
        "source_post_link": row.get("source_post_link"),
        "reaction": ",".join(reactions.keys()),
        "count": ",".join(str(v) for v in reactions.values()),
    }


async def _floodwait_aiter(bot: Client, aiter):
    it = aiter.__aiter__()
    while True:
        try:
            yield await bot.floodwait_handler(it.__anext__)
        except StopAsyncIteration:
            break


async def _edit_progress(
    status: Message,
    processed,
    total,
    comments_processed,
    reactions_processed,
    qualifying,
    reactions_skipped=0,
):
    with suppress(Exception):
        await asyncio.sleep(0.5)
        await status.edit_text(
            _progress_text(
                processed,
                total,
                comments_processed,
                reactions_processed,
                qualifying,
                reactions_skipped,
            )
        )


async def collect_commented_posts(bot: Client, app: Client, chat) -> list[int]:
    post_ids: list[int] = []
    async for post in _floodwait_aiter(bot, app.get_chat_history(chat.id)):
        if not _has_comments(post):
            continue
        post_ids.append(post.id)
        await db.posts.create(chat.id, post.id)
    return post_ids


async def fetch_users(bot: Client, app: Client, user_ids: list[int]) -> list[User]:
    users: list[User] = []
    for i in range(0, len(user_ids), GET_USERS_LIMIT):
        chunk = user_ids[i : i + GET_USERS_LIMIT]
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
            _merge_reactions(csv_rows[user.id].setdefault("_reactions", {}), reactions)
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
):
    new_ids: list[int] = []
    for comment in comments:
        user = await _resolve_comment_user(bot, app, comment, discussion_chat_id)
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

    fetched = await fetch_users(bot, app, new_ids)
    by_id = {user.id: user for user in fetched}
    for user_id in new_ids:
        user = by_id.get(user_id)
        active = is_active_last_4_days(user)
        activity_cache[user_id] = active
        if active and user:
            await save_qualifying_user(user, chat_id, source_post_link, csv_rows)


async def scrape_post_comments(
    bot: Client,
    app: Client,
    chat_id,
    post_id: int,
    activity_cache: dict[int, bool],
    csv_rows: dict,
    source_post_link: str,
    discussion_chat_id: int | None = None,
) -> int:
    batch: list = []
    seen_on_post: set[int] = set()
    comments_processed = 0

    async for comment in _floodwait_aiter(
        bot, app.get_discussion_replies(chat_id, post_id)
    ):
        batch.append(comment)
        if len(batch) < COMMENT_BATCH_SIZE:
            continue
        comments_processed += len(batch)
        await process_comment_batch(
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
        await process_comment_batch(
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

    return comments_processed


async def scrape_post_reactions(
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
    # user_id -> {reaction_key: count} gathered on this post before activity filter
    pending: dict[int, dict[str, int]] = {}
    users_by_id: dict[int, User] = {}

    while True:
        logger.info(
            "Scraping reactions for post %s in chat %s",
            reaction_message_id,
            reaction_chat_id,
        )
        try:
            result = await bot.floodwait_handler(
                app.invoke,
                raw.functions.messages.GetMessageReactionsList(
                    peer=peer,
                    id=reaction_message_id,
                    limit=REACTION_LIST_LIMIT,
                    offset=offset,
                ),
            )
        except MsgIdInvalid:
            # Telegram uses this when the message has no listable reactions.
            logger.info(
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
            key = _reaction_key(getattr(item, "reaction", None))
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
            _merge_reactions(
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


async def run_scrape(
    bot: Client,
    message: Message,
    app: Client,
    chat: Chat,
    post_ids: list[int] | None,
    post_link_by_id: dict[int, str] | None = None,
):
    status = await message.reply_text("Scraping started...")
    chat_id = chat.id
    discussion_chat_id = _discussion_chat_id(chat)
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
    reactions_skipped: list[int] = []
    csv_rows: dict = {}
    activity_cache: dict[int, bool] = {}
    failed: list[dict] = []
    await asyncio.sleep(0.5)
    await bot.floodwait_handler(_edit_progress, status, 0, total, 0, 0, 0, 0)

    for index, post_id in enumerate(post_ids, start=1):
        source_post_link = post_links.get(post_id) or build_post_link(chat, post_id)
        try:
            comments_processed += await scrape_post_comments(
                bot,
                app,
                chat_id,
                post_id,
                activity_cache,
                csv_rows,
                source_post_link,
                discussion_chat_id,
            )
        except Exception as e:
            logger.exception("Failed to scrape comments for post %s in chat %s", post_id, chat_id)
            failed.append({"post_id": post_id, "error": str(e)})
        else:
            try:
                reaction_target = await _resolve_reaction_target(
                    bot, app, chat, post_id
                )
                if reaction_target == "no_reactions":
                    reactions_skipped.append(post_id)
                    logger.info("No reactions for post %s; skipping reaction scrape", post_id)
                elif reaction_target:
                    reaction_chat_id, reaction_message_id = reaction_target
                    count = await scrape_post_reactions(
                        bot,
                        app,
                        reaction_chat_id,
                        reaction_message_id,
                        chat_id,
                        activity_cache,
                        csv_rows,
                        source_post_link,
                    )
                    if count:
                        reactions_processed += count
                    else:
                        reactions_skipped.append(post_id)
                        logger.info(
                            "No reaction users for post %s; skipping", post_id
                        )
            except Exception as e:
                logger.exception(
                    "Failed to scrape reactions for post %s in chat %s", post_id, chat_id
                )
                failed.append({"post_id": post_id, "error": f"reactions: {e}"})

        await bot.floodwait_handler(
            _edit_progress,
            status,
            index,
            total,
            comments_processed,
            reactions_processed,
            len(csv_rows),
            len(reactions_skipped),
        )
        if index < total:
            await asyncio.sleep(POST_SLEEP_SECONDS)

    logger.info(
        "Scrape of %s finished: %s qualifying users, failed posts %s, no-reaction posts %s",
        chat_id,
        len(csv_rows),
        [item["post_id"] for item in failed],
        reactions_skipped,
    )
    await finish_scrape(bot, message, status, csv_rows, failed, reactions_skipped)


def _write_users_csv(path: str, csv_rows: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(_csv_row(row) for row in csv_rows.values())


def _finish_text(
    qualifying: int,
    failed: list[dict],
    reactions_skipped: list[int] | None = None,
) -> str:
    if qualifying:
        lines = ["Scrape finished.", f"Qualifying users: {qualifying:,}"]
    else:
        lines = ["Scrape finished.", "No qualifying users found."]
    if reactions_skipped:
        lines.append(
            f"Posts whose reactions could not be fetched: {len(reactions_skipped)}"
        )
    if failed:
        ids = ", ".join(str(item["post_id"]) for item in failed)
        lines.append(f"Failed posts: {ids}")
    return "\n".join(lines)


async def finish_scrape(
    bot: Client,
    message: Message,
    status: Message,
    csv_rows: dict,
    failed: list[dict],
    reactions_skipped: list[int] | None = None,
):
    if csv_rows:
        admin_id = message.from_user.id
        file_path = os.path.join("downloads", f"{admin_id}_users.csv")
        try:
            _write_users_csv(file_path, csv_rows)
            await bot.floodwait_handler(
                bot.send_document,
                chat_id=message.chat.id,
                document=file_path,
                file_name="users.csv",
            )
        except Exception as e:
            logger.exception("Failed to send users.csv")
            with suppress(Exception):
                await message.reply_text(f"⚠️ Failed to send users.csv: {e}")
        finally:
            with suppress(OSError):
                os.remove(file_path)

    with suppress(Exception):
        await bot.floodwait_handler(
            status.edit_text,
            _finish_text(len(csv_rows), failed, reactions_skipped),
        )
