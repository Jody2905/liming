"""Money is whole cents (int), never float. Prices are in US dollars, as most travel is."""

from decimal import ROUND_HALF_UP, Decimal


def fmt(cents):
    """123456 -> 'US$1,234.56'; whole dollars drop the cents: 12300 -> 'US$123' (as the front end does)."""
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}US${cents // 100:,}" + (f".{cents % 100:02d}" if cents % 100 else "")


def percent_of(cents, percent):
    return int((Decimal(cents) * percent / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
