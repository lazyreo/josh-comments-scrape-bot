import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot import Bot
from bot.utils import resume_transfers

if __name__ == "__main__":
    os.makedirs("downloads", exist_ok=True)
    sc = AsyncIOScheduler()
    sc.start()
    app = Bot()
    app.sc = sc

    sc.add_job(resume_transfers, args=[app])

    app.run()
