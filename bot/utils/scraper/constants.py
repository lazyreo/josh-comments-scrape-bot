from bot.config import settings

COMMENT_BATCH_SLEEP_SECONDS = max(
    0.0, float(settings.SCRAPE_COMMENT_BATCH_SLEEP_SECONDS)
)
