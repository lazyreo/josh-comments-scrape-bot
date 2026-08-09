import os
from contextlib import suppress

if os.name != "nt":
    from uvloop import install

    install()

import asyncio
import logging
import logging.config
from typing import Any, Iterable, List, Union

import pyromod
from pyrogram import Client, errors, raw, types

from bot.config import ContextVariables, settings
from bot.utils import add_admin, set_commands
from database import db

# Get logging configurations

logging.getLogger().setLevel(logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.ERROR)
logging.getLogger("apscheduler").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.ERROR)

class User(Client):
    def __init__(self, session_string: str, **kwargs):
        name = kwargs.get("name", "user")
        kwargs.pop("name", None)
        super().__init__(
            name,
            api_id=settings.API_ID,
            api_hash=settings.API_HASH,
            session_string=session_string,
            plugins=dict(root="user/plugins"),
            **kwargs,
        )

    async def start(self, *args, **kwargs):
        try:
            await super().start(*args, **kwargs)
        except Exception:
            user = await db.users.filter_document(
                {"session.string": self.session_string}
            )
            session_username = user["session"]["username"]
            await db.users.remove_session(user["_id"])
            with suppress(Exception):
                await self.send_message(
                    int(user["_id"]),
                    f"Falha ao iniciar sua conta: @{session_username}",
                )
            return

        me = await self.get_me()
        self.username = f"@{me.username}"
        settings.CLIENTS[me.id] = self
        logging.info(f"User {self.username} started")
        logging.info(f"Owner: {settings.OWNER_ID}")
        return self

    async def stop(self, *args):
        await super().stop()
        logging.info(f"User {self.me.id} stopped")


class Bot(Client):
    def __init__(self):
        super().__init__(
            "bot",
            api_id=settings.API_ID,
            api_hash=settings.API_HASH,
            bot_token=settings.BOT_TOKEN,
            plugins=dict(root="bot/plugins"),
        )

    async def start(self, *args, **kwargs):
        await super().start(*args, **kwargs)

        me = await self.get_me()

        self.username = f"@{me.username}"

        logging.info(f"Bot started as {self.username}")
        # self.owner = await self.get_users(int(Config.OWNER_ID))
        # logging.info(f"Owner: {self.owner.full_name}")

        await add_admin(settings.OWNER_ID)
        await set_commands(self)

        clients_to_start = []
        for client in await db.users.filter_documents({}):
            if client.get("session") is None or client["session"].get("string") is None:
                continue

            c = User(client["session"]["string"], name=f"user_{client['_id']}")
            clients_to_start.append(c)

        await asyncio.gather(*[c.start() for c in clients_to_start])
        logging.info(f"Started {len(clients_to_start)} users")

        from bot.utils.forward_sources import refresh_active_sources

        sources = await refresh_active_sources()
        logging.info(f"Active forward sources: {len(sources)} → {sources}")

        ContextVariables.BOT = self

        if hasattr(self, "sc") and not self.sc.running:
            from bot.utils import resume_transfers

            self.sc.start()
            self.sc.add_job(resume_transfers, args=[self])

    async def stop(self, *args):
        if hasattr(self, "sc") and self.sc.running:
            self.sc.shutdown(wait=False)
        await asyncio.gather(
            *[self.suppress(c.stop) for c in settings.CLIENTS.values()]
        )
        await super().stop()

    async def get_users(
        self: "Client",
        user_ids: Union[int, str, Iterable[Union[int, str]]],
        raise_error: bool = True,
        limit: int = 200,
    ) -> Union["types.User", List["types.User"]]:
        """Get information about a user.
        You can retrieve up to 200 users at once.

        Parameters:
            user_ids (``int`` | ``str`` | Iterable of ``int`` or ``str``):
                A list of User identifiers (id or username) or a single user id/username.
                For a contact that exists in your Telegram address book you can use his phone number (str).
            raise_error (``bool``, *optional*):
                If ``True``, an error will be raised if a user_id is invalid or not found.
                If ``False``, the function will continue to the next user_id if one is invalid or not found.
            limit (``int``, *optional*):
                The maximum number of users to retrieve per request. Must be a value between 1 and 200.

        Returns:
            :obj:`~pyrogram.types.User` | List of :obj:`~pyrogram.types.User`: In case *user_ids* was not a list,
            a single user is returned, otherwise a list of users is returned.

        Example:
            .. code-block:: python

                # Get information about one user
                await app.get_users("me")

                # Get information about multiple users at once
                await app.get_users([user_id1, user_id2, user_id3])
        """
        is_iterable = not isinstance(user_ids, (int, str))
        user_ids = list(user_ids) if is_iterable else [user_ids]

        users = types.List()
        user_ids_chunks = [
            user_ids[i : i + limit] for i in range(0, len(user_ids), limit)
        ]

        # Define the `resolve` function with error handling based on the `raise_error` parameter
        async def resolve(user_id):
            try:
                return await self.resolve_peer(user_id)
            except Exception:
                if raise_error:
                    raise
                else:
                    return user_id

        for chunk in user_ids_chunks:
            chunk_resolved = await asyncio.gather(
                *[resolve(i) for i in chunk if i is not None]
            )

            # Remove any `None` values from the resolved user_ids list
            blocked_accounts = [i for i in chunk_resolved if isinstance(i, int)]
            chunk_resolved = list(filter(None, chunk_resolved))
            chunk_resolved = [i for i in chunk_resolved if not isinstance(i, int)]

            r = await self.invoke(raw.functions.users.GetUsers(id=chunk_resolved))

            for i in r:
                users.append(types.User._parse(self, i))

            for i in blocked_accounts:
                users.append(i)

        return users if is_iterable else users[0]

    async def reply(
        self, message: types.Message | types.CallbackQuery | Any, *args, **kwargs
    ):
        """
        Reply to a message or callback query with the given text or media.

        Parameters:
        - message: The message or callback query to reply to.
        - args: Additional positional arguments.
        - kwargs: Additional keyword arguments.

        Returns:
        None
        """
        key = kwargs.pop("key", None)
        if isinstance(message, types.Message):
            await message.reply(*args, **kwargs)
        elif isinstance(message, types.CallbackQuery):
            await message.edit_message_text(*args, **kwargs)

    async def floodwait_handler(self, func, *args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except errors.FloodWait as e:
            logging.warning(f"Floodwait for {e.value} seconds")
            await asyncio.sleep(e.value)
            return await self.floodwait_handler(func, *args, **kwargs)

    async def suppress(self, func, *args, **kwargs):
        with suppress(Exception):
            return await func(*args, **kwargs)
