"""Create safe, daytime YouTube publication schedules for video batches."""
from __future__ import annotations

import random
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


KYIV = ZoneInfo("Europe/Kyiv")
# Three broad windows preserve a minimum five-hour gap without publishing at night.
# The hour-wide ranges prevent a repetitive, clockwork-looking upload pattern.
_DAILY_WINDOWS = (
    (time(8, 30), time(9, 30)),
    (time(14, 30), time(15, 30)),
    (time(20, 30), time(21, 30)),
)


def plan_publication_times(
    count: int,
    now: datetime | None = None,
    rng: random.Random | None = None,
) -> list[datetime]:
    """Return random Kyiv daytime slots, at most three per calendar day."""
    if count < 1:
        return []

    generator = rng or random.SystemRandom()
    local_now = (now or datetime.now(KYIV)).astimezone(KYIV)
    # YouTube needs a little processing margin before a scheduled publication.
    earliest = local_now + timedelta(minutes=15)
    result: list[datetime] = []
    day = earliest.date()

    while len(result) < count:
        for start, end in _DAILY_WINDOWS:
            minutes = int((datetime.combine(day, end) - datetime.combine(day, start)).total_seconds() // 60)
            candidate = datetime.combine(day, start, tzinfo=KYIV) + timedelta(
                minutes=generator.randint(0, minutes)
            )
            if candidate < earliest:
                continue
            result.append(candidate)
            if len(result) == count:
                break
        day += timedelta(days=1)

    return result
