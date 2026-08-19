import re

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from pyromod.exceptions import ListenerStopped
from pyromod.types import ListenerTypes

from bot.config import settings
from bot.utils import (
    check_admin,
    get_link_parts,
    get_user_client,
    is_input_cancelled,
)
from bot.utils.chat_resolve import chat_title, parse_chat_ref, resolve_chat

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


async def run_scrape(
    bot: Client,
    message: Message,
    app: Client,
    chat,
    post_ids: list[int] | None,
):
    title = chat_title(chat)
    if post_ids is None:
        await message.reply_text(
            f"Scraping **{title}** (`{chat.id}`): all posts with comments."
        )
        return
    await message.reply_text(
        f"Scraping **{title}** (`{chat.id}`): {len(post_ids)} selected post(s)."
    )
