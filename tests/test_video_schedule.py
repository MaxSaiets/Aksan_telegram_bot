import random
from datetime import datetime

from app.services.video_schedule import KYIV, plan_publication_times


def test_schedule_uses_three_random_daytime_slots_with_safe_gaps():
    slots = plan_publication_times(
        3,
        now=datetime(2026, 9, 23, 8, 0, tzinfo=KYIV),
        rng=random.Random(7),
    )

    assert len(slots) == 3
    assert all(slot.tzinfo == KYIV for slot in slots)
    assert 9 <= slots[0].hour <= 9
    assert slots[1].hour in {14, 15}
    assert 20 <= slots[2].hour <= 20
    assert all((later - earlier).total_seconds() >= 5 * 60 * 60 for earlier, later in zip(slots, slots[1:]))


def test_schedule_moves_the_fourth_video_to_the_next_day():
    slots = plan_publication_times(
        4,
        now=datetime(2026, 9, 23, 8, 0, tzinfo=KYIV),
        rng=random.Random(3),
    )

    assert len(slots) == 4
    assert len({slot.date() for slot in slots[:3]}) == 1
    assert slots[3].date() > slots[2].date()
