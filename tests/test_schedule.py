import asyncio
from datetime import datetime, time

import pytest

from bot import compute_next_slot, SLOTS


def test_compute_next_slot_before_first():
    dt = datetime(2025, 10, 18, 9, 0)
    next_dt = asyncio.get_event_loop().run_until_complete(compute_next_slot(dt))
    assert next_dt.time() == SLOTS[0]


def test_compute_next_slot_between_slots():
    dt = datetime(2025, 10, 18, 12, 0)
    next_dt = asyncio.get_event_loop().run_until_complete(compute_next_slot(dt))
    assert next_dt.time() == SLOTS[1]


def test_compute_next_slot_after_last():
    dt = datetime(2025, 10, 18, 22, 0)
    next_dt = asyncio.get_event_loop().run_until_complete(compute_next_slot(dt))
    assert next_dt.time() == SLOTS[0]
    assert next_dt.date().day == 19
