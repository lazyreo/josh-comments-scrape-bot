import asyncio
import random
import traceback

from pyrogram import Client, errors, filters, types

from bot.config import settings
from bot.enums import TransferStatus
from bot.exceptions import CancelledError
from bot.utils import (
    add_transfer_to_queue,
    forward_message,
    get_config_from_dest_link,
    get_link_parts,
    get_user_client,
    is_transfer_cancelled,
    is_valid_link,
    remove_transfer_from_queue,
)
from database import db


def CANCEL_MARKUP(download_id):
    return types.InlineKeyboardMarkup(
        [
            [
                types.InlineKeyboardButton(
                    "Cancel transfer", callback_data=f"cancel {download_id}"
                )
            ]
        ]
    )


@Client.on_message(
    filters.text
    & filters.private
    & filters.incoming
    & (filters.regex(r"^https?://") | filters.regex(r"^tg://"))
    & filters.user(settings.OWNER_ID)
)
async def on_https_message(bot: Client, message: types.Message, **kwargs):
    user_message = message
    is_batch = kwargs.get("is_batch", False)
    config = kwargs.get("config")

    # If config not provided, ask user for destination link
    if not config:
        config = await get_config_from_dest_link(message, message.text)
        if not config:
            return


    if not is_valid_link(message):
        return await message.reply_text("Invalid link.")

    user_id = message.from_user.id

    # for download_id, transfer in settings.TRANSFERS.items():
    #     if (
    #         transfer["user_id"] == user_id
    #         and transfer["status"] == TransferStatus.IN_PROGRESS.value
    #     ):
    #         return await message.reply_text(
    #             "You have a transfer in progress. Please wait for it to complete."
    #         )

    app = await get_user_client(user_id)

    if not app:
        return await bot.floodwait_handler(
            bot.send_message,
            user_id,
            "You need to log in first to use this bot.",
            reply_markup=types.InlineKeyboardMarkup(
                [
                    [
                        types.InlineKeyboardButton(
                            "Log in", callback_data="connect_account"
                        )
                    ],
                ]
            ),
        )

    links = message.text.split()
    if not links:
        return await message.reply_text("No links found.")

    success, failed = 0, 0
    out = await bot.floodwait_handler(
        bot.send_message, user_id, f"Processing {len(links)} links..."
    )
    await (await out.pin(both_sides=True)).delete()

    for i, link in enumerate(links, 1):
        parts = get_link_parts(link)

        if not parts:
            failed += 1
            await bot.floodwait_handler(
                bot.send_message, user_id, f"Invalid link - {link}"
            )
            continue

        chat_id, message_id, topic_id = parts

        try:
            error_message = ""
            chat = None
            try:
                chat = await app.get_chat(chat_id)
            except Exception as e:
                error_message += f"Error: {e}\n"
                continue

            if chat is None:
                try:
                    chat = await app.get_users(chat_id)
                except Exception as e:
                    error_message += f"Error: {e}\n"
                    continue

            if chat is None:
                raise Exception(f"Could not access chat {chat_id} {error_message}")
        except errors.AuthKeyDuplicated:
            await db.users.remove_session(user_id)
            await out.unpin()
            return await out.edit(
                "Your session expired. Log in again.",
                reply_markup=types.InlineKeyboardMarkup(
                    [
                        [
                            types.InlineKeyboardButton(
                                "Log in", callback_data="connected_account"
                            )
                        ]
                    ]
                ),
            )
        except Exception as e:
            failed += 1
            print(e)
            text = "⚠️ Could not access the content!\n\n"
            text += "🔹 Join the channel first and try again\n"
            text += "🔹 For private chats:\n"
            text += "- First time: use the @username\n"
            text += "- Later: you can use the user ID\n"
            text += "🔹 Confirm that you have access to this chat"
            text += f"\n\n💡 Chat: {chat_id}\n\n💡 Error: {error_message}"

            await bot.floodwait_handler(bot.send_message, user_id, text)
            if is_batch:
                break
            continue

        if topic_id:
            message_ids = topic_id
        else:
            message_ids = message_id

        try:
            message = await bot.floodwait_handler(
                app.get_messages, chat_id, message_ids
            )
        except Exception as e:
            failed += 1
            print(e)
            await bot.floodwait_handler(
                bot.send_message, user_id, f"Message not found - {link}"
            )
            continue

        if message.empty or message.sticker:
            print("Empty or sticker message not allowed")
            failed += 1
            continue

        download_id = random.randint(100000, 999999)
        message.download_id = download_id
        message.index = f"{i} of {len(links)}"

        await add_transfer_to_queue(
            user_id=user_id,
            download_id=download_id,
            links=links,
            link_index=i - 1,
            status=TransferStatus.IN_PROGRESS.value,
            user_message_id=user_message.id,
            user_message_chat_id=user_message.chat.id,
        )

        progress_text = f"Downloading: {i} of {len(links)}\n"
        progress_text += f"Success: {success}\n"
        progress_text += f"Failed: {failed}"
        progress_text += f"\n\nIn progress: {message.link}"

        await bot.floodwait_handler(
            out.edit_text, progress_text, reply_markup=CANCEL_MARKUP(download_id)
        )

        try:
            await forward_message(bot, app, message, user_id, config)
        except CancelledError:
            await remove_transfer_from_queue(download_id)
            break
        except Exception as e:
            failed += 1
            traceback.print_exc()
            await remove_transfer_from_queue(download_id)
            await bot.floodwait_handler(bot.send_message, user_id, f"Error: {e}")
            continue

        if is_transfer_cancelled(message.download_id):
            break

        await remove_transfer_from_queue(download_id)
        success += 1

        await asyncio.sleep(settings.SLEEP_TIME)

    await out.delete()
    await bot.floodwait_handler(
        bot.send_message,
        user_id,
        f"Downloaded {i} of {len(links)} links\nSuccess: {success}\nFailed: {failed}",
    )
