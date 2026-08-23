import csv
import logging
import os
from contextlib import suppress

from pyrogram import Client
from pyrogram.types import Message

logger = logging.getLogger(__name__)


def csv_row(row: dict) -> dict:
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


def write_users_csv(path: str, csv_rows: dict) -> None:
    csv_columns = [
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
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_columns)
        writer.writeheader()
        writer.writerows(csv_row(row) for row in csv_rows.values())


def finish_text(
    qualifying: int,
    failed: list[dict],
) -> str:
    if qualifying:
        lines = ["Scrape finished.", f"Qualifying users: {qualifying:,}"]
    else:
        lines = ["Scrape finished.", "No qualifying users found."]
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
):
    if csv_rows:
        admin_id = message.from_user.id
        file_path = os.path.join("downloads", f"{admin_id}_users.csv")
        try:
            write_users_csv(file_path, csv_rows)
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
            finish_text(len(csv_rows), failed),
        )
