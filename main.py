import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot import Bot

if __name__ == "__main__":
    os.makedirs("downloads", exist_ok=True)
    app = Bot()
    app.sc = AsyncIOScheduler()
    app.run()
