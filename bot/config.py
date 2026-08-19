from typing import Any, Dict, List, Optional, Set

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pyrogram.client import Client

from bot.enums import CaptionVariables


class Config(BaseSettings):
    """Application configuration from environment variables / .env."""

    model_config = SettingsConfigDict(
        env_file=(".env", "config.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    API_ID: int
    API_HASH: str
    BOT_TOKEN: str

    DATABASE_NAME: str = "tg_bot"
    DATABASE_URL: Optional[str] = None
    OWNER_ID: int

    SLEEP_TIME: int = 10

    CLIENTS: Dict[Any, Any] = Field(default_factory=dict, exclude=True)
    TRANSFERS: Dict[Any, Any] = Field(default_factory=dict, exclude=True)
    ACTIVE_SOURCE_IDS: Set[int] = Field(default_factory=set, exclude=True)


settings = Config()  # type: ignore


class ContextVariables(object):
    BOT: Client | None = None


class Script(object):
    START_MESSAGE = """💾 **Welcome!**

This bot forwards messages from a **Source** chat to a **Destination** chat using your connected Telegram account.

**Simple steps:**
1. **Log in** — tap Account (or /account)
2. **Add a forward** — tap Forwards → choose Source and Destination
3. New messages from the Source are copied to the Destination with your account

You can also paste a `t.me` link to forward that message (if that Source has a forward configured)."""

    RESTART_MESSAGE = "🔄 **The bot is restarting. Re-download your in-progress files in a few seconds.**"

    HELP_MESSAGE_1 = """**💡 Help**

1. **/account** — Log in with the Telegram account that can see the Source and post to the Destination.

2. **Forwards** — tap Forwards → Add.
   Send the Source (@username, id, or a forwarded message), then the Destination the same way.

3. **Paste a link** — Send a `https://t.me/...` link to forward that message through an existing Source → Destination forward.

4. **/scrape** — Collect the users who commented on a specific post, or collect commenters from all posts in a channel.
 - **Specific post:** Send the post link when prompted.
  - **All posts:** Choose the option to scrape commenters from all available posts.


Need help? Contact support.
"""

    DEFAULT_CAPTION = "{%s}" % CaptionVariables.CAPTION.value
    PROGRESS_MESSAGE = """**╔══❰ {mode} ❱══❍
║╭━➣
║┣⪼ 📊 **Progress:** {percentage}%
║┣
║┣⪼ {progress}
║┣
║┣⪼ **Done:** {finished} of {total}
║┣
║┣⪼ ⚡ **Speed:** {speed}/s
║┣
║┣⪼ ⏰ **Time left:** {eta}
║╰━➣
╚════════════════❍**"""
