"""Resolve the bot DB user for a logged-in session client."""

from pyrogram import Client

from database import db


async def session_user_id(client: Client) -> int | None:
    me = client.me or await client.get_me()
    user = await db.users.filter_document({"session.id": me.id})
    if not user:
        return None
    return user["_id"]
