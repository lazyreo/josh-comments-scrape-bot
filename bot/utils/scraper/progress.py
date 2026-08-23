import asyncio
from contextlib import suppress

from pyrogram.types import Message


def progress_text(
    processed: int,
    total: int,
    comments_processed: int,
    reactions_processed: int,
    qualifying: int,
) -> str:
    return "\n".join(
        [
            "Scraping started...",
            f"Posts processed: {processed} / {total}",
            f"Comments processed: {comments_processed:,}",
            f"Comment reactions processed: {reactions_processed:,}",
            f"Qualifying users: {qualifying:,}",
        ]
    )


async def edit_progress(
    status: Message,
    processed,
    total,
    comments_processed,
    reactions_processed,
    qualifying,
):
    with suppress(Exception):
        await asyncio.sleep(0.5)
        await status.edit_text(
            progress_text(
                processed,
                total,
                comments_processed,
                reactions_processed,
                qualifying,
            )
        )
