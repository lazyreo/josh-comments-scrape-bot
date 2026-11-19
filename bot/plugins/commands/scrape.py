from contextlib import suppress

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from pyromod.exceptions import ListenerStopped
from pyromod.types import ListenerTypes

from bot.config import settings
from bot.utils import check_admin, get_user_client, is_input_cancelled
from bot.utils.chat_resolve import forward_post_ref, parse_chat_input, resolve_chat
from bot.utils.scraper import (
    build_post_link,
    link_chat_matches,
    parse_post_tokens,
    run_scrape,
)

_MODE_MARKUP = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("All", callback_data="scrape_mode_all"),
            InlineKeyboardButton("Selected", callback_data="scrape_mode_selected"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="scrape_mode_cancel")],
    ]
)

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

    chat, _ = await bot.floodwait_handler(resolve_chat, app, chat_ref)
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
            "You can also send post IDs, links, or a **range**:\n"
            "• `328910-328920`\n"
            "• `https://t.me/channel/328910 - 328920`\n"
            "• `https://t.me/channel/328910 - https://t.me/channel/328920`\n\n"
            "Press ✅ Done when finished, or ❌ Cancel to abort."
        )
        first_ask = True
        while True:
            try:
                ask = await message.chat.ask(
                    prompt if first_ask else (
                        "Copy another post, or press ✅ Done / ❌ Cancel.\n"
                        f"Selected so far: **{len(post_ids)}**"
                    ),
                    reply_markup=ReplyKeyboardMarkup(
                        [[KeyboardButton("✅ Done"), KeyboardButton("❌ Cancel")]],
                        resize_keyboard=True,
                    ),
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
            if text in {"❌ Cancel", "Cancel", "/cancel"}:
                await message.reply_text(
                    "❌ Operation cancelled.",
                    reply_markup=ReplyKeyboardRemove(),
                )
                return
            if text in {"✅ Done", "Done"}:
                break

            new_ids: list[int] = []
            new_links: dict[int, str] = {}
            forwarded_chat, forwarded_message_id = forward_post_ref(ask)
            has_forward = (
                forwarded_chat is not None and forwarded_message_id is not None
            )
            if has_forward:
                if link_chat_matches(chat, forwarded_chat):
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
                        f"⚠️ Invalid tokens (skipped): {', '.join(invalid)}\n"
                        "Tip: ranges must match this chat and be at most 500 posts."
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
                    "or press ✅ Done / ❌ Cancel."
                )
                continue

            if len(noted) > 20 and noted == list(range(noted[0], noted[-1] + 1)):
                noted_text = f"`{noted[0]}`–`{noted[-1]}` ({len(noted)} posts)"
            else:
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
