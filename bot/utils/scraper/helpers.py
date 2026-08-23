from pyrogram import Client


async def floodwait_aiter(bot: Client, aiter):
    it = aiter.__aiter__()
    while True:
        try:
            yield await bot.floodwait_handler(it.__anext__)
        except StopAsyncIteration:
            break
