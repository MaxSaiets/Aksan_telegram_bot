"""YouTube publication slots: two videos per day, starting today.

Every video is posted to the Telegram group immediately, while the YouTube copy
is uploaded privately and published at the next free slot. Slots are kept in
Redis so videos sent at different times still share the same two-per-day plan.
"""
from __future__ import annotations

import random
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

KYIV = ZoneInfo("Europe/Kyiv")
VIDEOS_PER_DAY = 2
_MIN_GAP = timedelta(hours=3)
_ASAP_SPREAD_MINUTES = 30
# First daily slot (or "as soon as possible" when today's morning already passed)
# and a second evening slot. Hour-wide ranges avoid a clockwork-looking pattern.
_FIRST_WINDOW = (time(9, 0), time(11, 0))
_SECOND_WINDOW = (time(18, 30), time(21, 30))
_REDIS_KEY = "aksan:yt_publish_slots"
_REDIS_LOCK = "aksan:yt_publish_slots:lock"


def _evening_cutoff(day) -> datetime:
    return datetime.combine(day, time(20, 0), tzinfo=KYIV)


def pick_publication_slot(
    taken: list[datetime],
    now: datetime | None = None,
    rng: random.Random | None = None,
) -> datetime:
    """Return the next free slot given already reserved ones (max 2 per Kyiv day)."""
    generator = rng or random.SystemRandom()
    earliest = (now or datetime.now(KYIV)).astimezone(KYIV) + timedelta(minutes=15)
    taken_local = sorted(t.astimezone(KYIV) for t in taken)
    day = earliest.date()

    for _ in range(366):
        day_taken = [t for t in taken_local if t.date() == day]
        if len(day_taken) < VIDEOS_PER_DAY:
            first = len(day_taken) == 0
            w_start, w_end = _FIRST_WINDOW if first else _SECOND_WINDOW
            start = datetime.combine(day, w_start, tzinfo=KYIV)
            end = datetime.combine(day, w_end, tzinfo=KYIV)
            if first and day == earliest.date() and end <= earliest < _evening_cutoff(day):
                # Morning already passed today: publish the first one right away.
                start, end = earliest, earliest + timedelta(minutes=_ASAP_SPREAD_MINUTES)
            start = max(start, earliest)
            if day_taken:
                start = max(start, day_taken[-1] + _MIN_GAP)
            if start < end:
                span = int((end - start).total_seconds() // 60)
                return start + timedelta(minutes=generator.randint(0, span))
        day += timedelta(days=1)
    raise RuntimeError("No free YouTube publication slot found")


def reserve_publication_slot(now: datetime | None = None) -> datetime:
    """Pick the next free slot and persist the reservation in Redis."""
    import redis

    from config import settings

    client = redis.from_url(settings.REDIS_URL)
    with client.lock(_REDIS_LOCK, timeout=15, blocking_timeout=15):
        current = (now or datetime.now(KYIV)).timestamp()
        client.zremrangebyscore(_REDIS_KEY, "-inf", current - 86400)
        taken = [
            datetime.fromisoformat(member.decode())
            for member in client.zrange(_REDIS_KEY, 0, -1)
        ]
        slot = pick_publication_slot(taken, now=now)
        client.zadd(_REDIS_KEY, {slot.isoformat(): slot.timestamp()})
    return slot


def release_publication_slot(slot: datetime) -> None:
    """Free a reserved slot (e.g. when the YouTube upload failed)."""
    import redis

    from config import settings

    try:
        redis.from_url(settings.REDIS_URL).zrem(_REDIS_KEY, slot.isoformat())
    except Exception:
        pass
