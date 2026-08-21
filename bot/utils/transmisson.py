import os
import time
from contextlib import suppress

from pyrogram import Client, types

from bot.config import settings
from bot.enums import TransferStatus
from bot.exceptions import CancelledError
from bot.utils.ffmpeg import get_video_details
from bot.utils.helpers import (
    get_thumbnail,
    get_title,
    get_upload_function,
    is_transfer_cancelled,
    progress_for_pyrogram,
)
from bot.utils.text_replacements import apply_text_replacements
from database import db


async def forward_message(
    bot: Client, app: Client, message: types.Message, user_id: int, config: dict
):
    """Copy a message to config['dest'] using the session client only."""
    dest = config["dest"]
    rules = config.get("text_replacements") or []
    log = None
    file_path = None

    raw = message.text or message.caption
    if rules and raw:
        new_text = apply_text_replacements(str(raw), rules)
        if message.media:
            with suppress(Exception):
                log = await message.copy(chat_id=dest, caption=new_text)
            if not log:
                file_path = await download_media(bot, user_id, message)
                if file_path:
                    log, file_path = await upload_media(
                        user_id,
                        bot,
                        app,
                        file_path,
                        message,
                        config,
                        caption=new_text,
                    )
        else:
            with suppress(Exception):
                log = await app.send_message(chat_id=dest, text=new_text)
    else:
        with suppress(Exception):
            sent = await app.copy_message(dest, message.chat.id, message.id)
            log = sent[0] if isinstance(sent, list) else sent

        if not log:
            with suppress(Exception):
                log = await message.copy(chat_id=dest)

        if not log:
            if message.text:
                log = await app.send_message(chat_id=dest, text=message.text.html)
            else:
                file_path = await download_media(bot, user_id, message)
                if file_path:
                    log, file_path = await upload_media(
                        user_id, bot, app, file_path, message, config
                    )
                else:
                    return

    if not log:
        return await bot.send_message(
            user_id, "Failed to copy the message. Try again."
        )

    if file_path:
        with suppress(Exception):
            os.remove(file_path)

    if getattr(message, "download_id", None) and is_transfer_cancelled(
        message.download_id
    ):
        raise CancelledError


async def download_media(bot, user_id, message: types.Message):
    download_id = message.download_id

    media = message.document or message.video or message.photo or message.audio
    if not media:
        return None

    out = await bot.floodwait_handler(
        bot.send_message, user_id, f"Downloading ({message.index})"
    )
    start = time.time()

    filename = get_file_name(message)

    if not filename:
        await out.delete()
        await bot.send_message(user_id, "No file name found.")
        return None

    file_path = await bot.floodwait_handler(
        message.download,
        file_name=filename,
        progress=progress_for_pyrogram,
        progress_args=(
            start,
            message,
            out.edit,
            download_id,
            f"Downloading ({message.index})",
        ),
    )
    await out.delete()
    if not file_path:
        raise CancelledError
    return file_path


async def upload_media(
    user_id: int,
    bot: Client,
    app: Client,
    file_path: str,
    message: types.Message,
    config: dict,
    caption: str | None = None,
):
    out = await bot.floodwait_handler(bot.send_message, user_id, "Starting upload...")
    target_channel = config["dest"]

    thumbnail = await get_thumbnail(file_path)

    function, kwargs = await get_upload_function(message, app, file_path)

    if not function:
        await out.delete()
        return await bot.send_message(
            user_id, "Invalid send mode. Select a valid mode."
        )

    if function == app.send_video:
        width, height, duration = await get_video_details(file_path)
        kwargs["duration"] = duration
        kwargs["width"] = width
        kwargs["height"] = height

    kwargs["chat_id"] = target_channel

    media = ["audio", "document", "video", "photo"]
    if any(media_type in kwargs for media_type in media) and thumbnail:
        kwargs["thumb"] = thumbnail

    title = get_title(message)

    if title:
        kwargs["file_name"] = title

    kwargs["progress"] = progress_for_pyrogram
    kwargs["progress_args"] = (
        time.time(),
        message,
        out.edit,
        message.download_id,
        f"Uploading ({message.index})",
    )

    if caption is not None:
        kwargs["caption"] = caption
    else:
        original = message.text or message.caption
        rules = config.get("text_replacements") or []
        if original and rules:
            kwargs["caption"] = apply_text_replacements(str(original), rules)
        elif original:
            kwargs["caption"] = (
                original.html if hasattr(original, "html") else original
            )
        else:
            kwargs["caption"] = None

    await bot.floodwait_handler(out.edit, "Uploading...")

    log = await bot.floodwait_handler(function, **kwargs)
    await out.delete()
    if thumbnail:
        with suppress(Exception):
            os.remove(thumbnail)
    if not log:
        raise CancelledError

    return log, file_path


async def resume_transfers(bot: Client):
    transfers = await db.transfers.filter_documents(
        {
            "status": {
                "$in": [TransferStatus.SLEEPING.value, TransferStatus.IN_PROGRESS.value]
            }
        }
    )
    for transfer in transfers:
        user_id = transfer["user_id"]
        text = (
            f"**The bot restarted. You can resume transfers from "
            f"{transfer['link_index']} to {len(transfer['links'])}.**"
        )
        markup = types.InlineKeyboardMarkup(
            [
                [
                    types.InlineKeyboardButton(
                        "Resume transfers",
                        callback_data=f"resume_transfers {transfer['_id']}",
                    )
                ]
            ]
        )
        try:
            await bot.send_message(user_id, text, reply_markup=markup)
        except Exception as e:
            print(e)

        await update_transfer(transfer["_id"], status=None)


async def add_transfer_to_queue(
    user_id, download_id, links, link_index, status, **kwargs
):
    settings.TRANSFERS[download_id] = {
        "user_id": user_id,
        "links": links,
        "link_index": link_index,
        "status": status,
    }

    return await db.transfers.create(
        user_id, download_id, links, link_index, status, **kwargs
    )


async def remove_transfer_from_queue(download_id):
    settings.TRANSFERS.pop(download_id, None)
    return await db.transfers.delete(download_id)


async def update_transfer(download_id, **kwargs):
    if download_id in settings.TRANSFERS:
        settings.TRANSFERS[download_id].update(kwargs)
    return await db.transfers.update(download_id, kwargs)


def get_file_name(message: types.Message):
    if not message.media:
        return None

    media = getattr(message, message.media.value, None)
    if not media:
        return None

    file_name = getattr(media, "file_name", None)

    if file_name:
        return file_name

    media_extensions = {"photo": ".jpg", "video": ".mp4", "audio": ".mp3"}

    media_type = message.media.value
    if media_type in media_extensions:
        return f"{media.file_id}{media_extensions[media_type]}"

    return None


def get_extension(file_name):
    return file_name.split(".")[-1]
