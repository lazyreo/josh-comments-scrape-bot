from datetime import datetime, timedelta, timezone

from pyrogram.enums import UserStatus
from pyrogram.types import User


def _as_utc(value: int | float | datetime | UserStatus | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if getattr(value, "tzinfo", None) is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def is_active_last_4_days(user: User | None) -> bool:
    if not user:
        return False

    status = getattr(user, "status", None)
    if status is None:
        return False
    if status in {
        UserStatus.LAST_WEEK,
        UserStatus.LAST_MONTH,
        UserStatus.LONG_AGO,
        UserStatus.OFFLINE,
    }:
        return False
    if status in {UserStatus.ONLINE, UserStatus.RECENTLY}:
        return True

    was_online = getattr(user, "last_online_date", None)
    was_online = _as_utc(was_online)
    if not was_online:
        return False
    return was_online >= datetime.now(timezone.utc) - timedelta(days=4)
