import random
from datetime import datetime, timedelta

from app.services.video_schedule import KYIV, pick_publication_slot


def _fill(now, count, seed=1):
    rng = random.Random(seed)
    taken = []
    for _ in range(count):
        taken.append(pick_publication_slot(taken, now=now, rng=rng))
    return taken


def test_two_videos_per_day_starting_today():
    now = datetime(2026, 11, 4, 8, 0, tzinfo=KYIV)
    slots = _fill(now, 5)
    days = [slot.date() for slot in slots]
    assert days[:2] == [now.date()] * 2
    assert [days.count(d) for d in sorted(set(days))] == [2, 2, 1]
    assert all(s >= now + timedelta(minutes=15) for s in slots)


def test_afternoon_request_still_gets_two_slots_today():
    now = datetime(2026, 11, 4, 14, 50, tzinfo=KYIV)
    first, second = _fill(now, 2)
    assert first.date() == second.date() == now.date()
    assert first - now <= timedelta(minutes=50)
    assert second - first >= timedelta(hours=3)
    assert (18, 30) <= (second.hour, second.minute) <= (21, 30)


def test_late_evening_moves_to_next_day():
    now = datetime(2026, 11, 4, 22, 30, tzinfo=KYIV)
    slots = _fill(now, 2)
    assert all(s.date() > now.date() for s in slots)
