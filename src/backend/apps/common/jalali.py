import jdatetime
from datetime import datetime
from typing import NamedTuple


class JalaliDate(NamedTuple):
    year: int
    month: int


def get_current_jalali() -> JalaliDate:
    """Return current Jalali year and month."""
    now = jdatetime.datetime.now()
    return JalaliDate(year=now.year, month=now.month)


def gregorian_to_jalali(dt: datetime) -> JalaliDate:
    """Convert a Gregorian datetime to Jalali year/month."""
    jdt = jdatetime.datetime.fromgregorian(datetime=dt)
    return JalaliDate(year=jdt.year, month=jdt.month)
