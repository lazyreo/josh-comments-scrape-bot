import asyncio
import datetime
import logging
import time
from contextlib import suppress

from pyrogram import Client, errors, filters, types

from bot.config import settings
from database import db


@Client.on_message(
    filters.command("broadcast") & filters.user(settings.OWNER_ID) & filters.incoming
)
async def b_handler(bot, message: types.Message):
    try:
        ask: types.Message = await message.chat.ask(
            "Send the message you want to broadcast.\n\n/cancel to cancel."
        )
    except Exception as e:
        await message.reply_text(str(e))
        return

    if ask.text and ask.text.lower() == "/cancel":
        await message.reply_text("Broadcast Cancelled.")
        return

    b_msg = ask

    users = await db.users.filter_documents({})
    sts = await message.reply_text(text="Broadcasting your messages...")

    start_time = time.time()
    total_users = len(users)
    done = 0
    blocked = 0
    deleted = 0
    failed = 0

    success = 0

    sem = asyncio.Semaphore(25)  # limit the number of concurrent tasks to 100

    async def run_task(user):
        async with sem:
            res = await broadcast_func(user, b_msg)
            return res

    tasks = []

    for user in users:
        task = asyncio.ensure_future(run_task(user))
        tasks.append(task)

    for res in await asyncio.gather(*tasks):
        success1, blocked1, deleted1, failed1, done1 = res
        done += done1
        blocked += blocked1
        deleted += deleted1
        failed += failed1
        success += success1

        if not done % 50 and done != 0:
            text = "Broadcast Completed:\n\n"
            text += f"Total Users {total_users}\n"
            text += f"Completed: {done} / {total_users}\n"
            text += f"Success: {success}\n"
            text += f"Blocked: {blocked}\n"
            text += f"Deleted: {deleted}\n"
            text += f"Failed: {failed}"
            with suppress(Exception):
                await sts.edit(text)

    time_taken = datetime.timedelta(seconds=int(time.time() - start_time))
    with suppress(Exception):
        text = "Broadcast Completed:\n"
        text += f"Completed in {time_taken} seconds.\n\n"
        text += f"Total Users {total_users}\n"
        text += f"Completed: {done} / {total_users}\n"
        text += f"Success: {success}\n"
        text += f"Blocked: {blocked}\n"
        text += f"Deleted: {deleted}\n"
        text += f"Failed: {failed}"
        await sts.edit(text)


async def broadcast_func(user, b_msg):
    success, blocked, deleted, failed, done = 0, 0, 0, 0, 0
    pti, sh = await broadcast_messages(int(user["_id"]), b_msg)
    if pti:
        success = 1
    elif pti is False:
        if sh == "Blocked":
            blocked = 1
        elif sh == "Deleted":
            deleted = 1
        elif sh == "Error":
            failed = 1
    done = 1
    return success, blocked, deleted, failed, done


async def broadcast_messages(user_id, message):
    try:
        await message.copy(chat_id=user_id)
        return True, "Success"
    except errors.FloodWait as e:
        await asyncio.sleep(e.value)
        return await broadcast_messages(user_id, message)
    except errors.InputUserDeactivated:
        logging.info(f"{user_id} - Removed from Database, since deleted account.")
        return False, "Deleted"
    except errors.UserIsBlocked:
        logging.info(f"{user_id} -Blocked the bot.")
        return False, "Blocked"
    except errors.PeerIdInvalid:
        logging.info(f"{user_id} - PeerIdInvalid")
        return False, "Blocked"
    except Exception as e:
        logging.exception(f"Error in Broadcasting to {user_id} - {e}")
        return False, "Error"
