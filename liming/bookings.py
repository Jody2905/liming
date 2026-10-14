"""Booking what's in the plan: the stay, places on activities, and restaurant tables.

Flow (the same for all three)
    hold (space set aside for 15 minutes)  ->  confirm  ->  maybe cancel
                    |
                    +-> lapses if not confirmed: the space goes back on sale

Space is never stored as a counter that could drift. It's always counted from the
bookings still holding it (confirmed, or held and not yet lapsed):
    stays        rooms, night by night
    activities   places at each set start time
    tables       seats at each lunch or dinner sitting

Two people can't both take the last room: the row for the thing being booked is locked
first (SELECT ... FOR UPDATE on PostgreSQL; on SQLite every write transaction takes the
database's write lock up front), so the second waits and then sees the first's booking.

Cancelling
    stay      free until the stay's deadline before check-in (15:00); after that the first night is kept
    activity  free until 24 hours before it starts; after that non-refundable
    table     always free: there's no charge to book a table
Holding or booking an item locks it in the plan, so regenerating never drops it, and it can't be
moved or removed until the booking is cancelled.
"""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select

from . import planner
from .models import Activity, Booking, PlanItem, Restaurant, Stay
from .money import fmt
from .planner import Prefs, minutes
from .services import LimingError, NotFound, _get, _own_item, _own_trip, _tx, holding

HOLD_MINUTES = 15
ACTIVITY_FREE_CANCEL_HOURS = 24


class SoldOut(LimingError):
    """Not enough space left. (The API answers 409 Conflict for this one.)"""


# ======================================================================
# Holding
# ======================================================================

def hold_stay(db, user, trip_id, now=None):
    """Hold the trip's stay for every night, with enough rooms for everyone."""
    now = now or datetime.now()
    with _tx(db):
        trip = _own_trip(db, user, trip_id, lock=True)
        if trip.stay_id is None:
            raise LimingError("Build the plan first, so there's a stay to book")
        _no_live_booking(db, trip.id, now, kind="stay")
        stay = _get(db, Stay, trip.stay_id, lock=True)            # one booking at a time for this stay
        prefs = Prefs.from_trip(trip)
        rooms = planner.rooms_needed(stay, prefs)
        left = rooms_left(db, stay, trip.start_date, trip.end_date, now)
        if left < rooms:
            raise SoldOut(_sold_out(left, "room", stay.name, rooms))
        b = _new(db, trip, user, "stay", now, stay_id=stay.id, title=stay.name, start_date=trip.start_date,
                 end_date=trip.end_date,
                 starts_at=datetime.combine(trip.start_date, planner.to_time(planner.CHECK_IN[0])),
                 quantity=rooms, units=trip.nights, total_cents=planner.stay_cost(stay, prefs))
        trip.stay_locked = True                                     # a booked stay is the stay
    return b


def hold_item(db, user, item_id, now=None):
    """Hold places on a plan item's activity, or a table for its meal, for the whole group."""
    now = now or datetime.now()
    with _tx(db):
        item, trip = _own_item(db, user, item_id, lock_trip=True)
        _no_live_booking(db, trip.id, now, item_id=item.id)
        prefs = Prefs.from_trip(trip)
        starts_at = datetime.combine(item.day, item.starts)
        if starts_at <= now:
            raise LimingError("That's already started")
        if item.kind == "activity":
            a = _get(db, Activity, item.activity_id, lock=True)
            if a.capacity is None:
                raise LimingError(f"{a.name} doesn't need booking: just turn up")
            _check_activity(a, item, prefs)
            left = places_left(db, a, starts_at, now)
            if left < prefs.people:
                raise SoldOut(_sold_out(left, "place", f"{a.name} at {item.starts:%H:%M}", prefs.people))
            b = _new(db, trip, user, "activity", now, activity_id=a.id, plan_item_id=item.id, title=a.name,
                     start_date=item.day, end_date=item.day, starts_at=starts_at, quantity=prefs.people,
                     total_cents=planner.group_price(a, prefs))
        elif item.kind == "meal" and item.restaurant_id is not None:
            r = _get(db, Restaurant, item.restaurant_id, lock=True)
            sitting = _sitting(item)
            if planner.closed_on(r, item.day) or not (r.lunch if sitting == "lunch" else r.dinner):
                raise LimingError(f"{r.name} doesn't serve {sitting} on {item.day:%A}s")
            left = seats_left(db, r, item.day, sitting, now)
            if left < prefs.people:
                raise SoldOut(_sold_out(left, "seat", f"{r.name} for {sitting}", prefs.people))
            b = _new(db, trip, user, "table", now, restaurant_id=r.id, plan_item_id=item.id,
                     title=f"Table for {prefs.people} at {r.name}", start_date=item.day, end_date=item.day,
                     starts_at=starts_at, quantity=prefs.people, total_cents=0)
        else:
            raise LimingError("Only activities and restaurant meals can be booked here")
        item.locked = True                         # so regenerating during the hold can't drop it
    return b


def _check_activity(a, item, prefs):
    if not planner.suits_group(a, prefs):
        raise LimingError(f"{a.name} doesn't suit your group (ages {a.min_age}+"
                          f"{', step-free access' if prefs.step_free and not a.step_free else ''})")
    if planner.closed_on(a, item.day):
        raise LimingError(f"{a.name} doesn't run on {item.day:%A}s")
    if a.start_times and minutes(item.starts) not in [minutes(s.starts) for s in a.start_times]:
        times = ", ".join(f"{s.starts:%H:%M}" for s in a.start_times)
        raise LimingError(f"{a.name} starts at {times}. Move it to one of those times first.")


# ======================================================================
# Confirming and cancelling
# ======================================================================

def confirm(db, user, booking_id, now=None):
    """Confirm a hold. (A real system would take payment here.) Its plan item is locked."""
    now = now or datetime.now()
    with _tx(db):
        b = _own_booking(db, user, booking_id, lock=True)
        lapsed = b.status == "held" and b.held_until <= now
        if lapsed:
            b.status = "expired"                                  # saved, then reported below
        elif b.status != "held":
            raise LimingError(f"This booking is {b.status}, so it can't be confirmed")
        else:
            b.status, b.confirmed_at = "confirmed", now
            if b.plan_item_id is not None:
                item = db.get(PlanItem, b.plan_item_id)
                if item is not None:
                    item.locked = True
    if lapsed:
        raise LimingError("This hold has run out, so the space was released. Please book it again.")
    return b


@dataclass
class Refund:
    cents: int
    reason: str


def refund_for(db, b, now):
    """What cancelling now would give back, and why. Changes nothing."""
    if b.status == "held":
        return Refund(0, "Nothing was charged for a hold")
    if b.status != "confirmed":
        raise LimingError(f"This booking is {b.status}")
    if now >= b.starts_at:
        raise LimingError("This has already started, so it can't be cancelled")
    if b.kind == "table":
        return Refund(0, "There's no charge to book a table")
    if b.kind == "stay":
        hours = db.scalar(select(Stay.free_cancel_hours).where(Stay.id == b.stay_id))
        if now <= b.starts_at - timedelta(hours=hours):
            return Refund(b.total_cents, f"Free cancellation until {hours} hours before check-in")
        kept = min(b.total_cents, b.total_cents // b.units)
        return Refund(b.total_cents - kept, f"Less than {hours} hours before check-in: the first night "
                                            f"({fmt(kept)}) is kept")
    if now <= b.starts_at - timedelta(hours=ACTIVITY_FREE_CANCEL_HOURS):
        return Refund(b.total_cents, f"Free cancellation until {ACTIVITY_FREE_CANCEL_HOURS} hours before")
    return Refund(0, f"Less than {ACTIVITY_FREE_CANCEL_HOURS} hours to go: non-refundable")


def refund_quote(db, user, booking_id, now=None):
    return refund_for(db, _own_booking(db, user, booking_id), now or datetime.now())


def cancel(db, user, booking_id, now=None):
    now = now or datetime.now()
    with _tx(db):
        b = _own_booking(db, user, booking_id, lock=True)
        if b.status == "held" and b.held_until <= now:
            raise LimingError("This hold has already run out")
        refund = refund_for(db, b, now)
        b.refund_cents = refund.cents if b.status == "confirmed" else 0
        b.status, b.cancelled_at = "cancelled", now
    return b, refund


def bookings_for_trip(db, user, trip_id):
    trip = _own_trip(db, user, trip_id)
    return db.scalars(select(Booking).where(Booking.trip_id == trip.id).order_by(Booking.starts_at, Booking.id)).all()


def live_bookings(db, trip_id, now):
    return db.scalars(select(Booking).where(Booking.trip_id == trip_id, holding(now))).all()


def booked_cents(db, trip_id):
    """What's been committed so far: confirmed bookings, plus whatever was kept on cancelled ones."""
    total = 0
    for b in db.scalars(select(Booking).where(Booking.trip_id == trip_id, Booking.confirmed_at.is_not(None))):
        total += b.total_cents if b.status == "confirmed" else b.total_cents - b.refund_cents
    return total


# ======================================================================
# Counting what's left
# ======================================================================

def rooms_left(db, stay, check_in, check_out, now):
    """The fewest rooms free on any one night of the stay."""
    overlapping = db.execute(select(Booking.start_date, Booking.end_date, Booking.quantity).where(
        Booking.stay_id == stay.id, holding(now),
        Booking.start_date < check_out, Booking.end_date > check_in)).all()
    worst, night = 0, check_in
    while night < check_out:
        worst = max(worst, sum(q for start, end, q in overlapping if start <= night < end))
        night += timedelta(days=1)
    return stay.rooms_total - worst


def places_left(db, activity, starts_at, now):
    taken = db.scalar(select(func.coalesce(func.sum(Booking.quantity), 0)).where(
        Booking.activity_id == activity.id, Booking.starts_at == starts_at, holding(now)))
    return activity.capacity - taken


def seats_left(db, restaurant, day, sitting, now):
    """Seats left at a lunch or dinner sitting (bookings before 16:00 are lunch)."""
    split = datetime.combine(day, planner.to_time(16 * 60))
    in_sitting = Booking.starts_at < split if sitting == "lunch" else Booking.starts_at >= split
    taken = db.scalar(select(func.coalesce(func.sum(Booking.quantity), 0)).where(
        Booking.restaurant_id == restaurant.id, Booking.start_date == day, in_sitting, holding(now)))
    return restaurant.covers - taken


# ======================================================================
# Helpers
# ======================================================================

def live_booking_for_item(db, item_id, now):
    return db.scalar(select(Booking).where(Booking.plan_item_id == item_id, holding(now)))


def _no_live_booking(db, trip_id, now, kind=None, item_id=None):
    q = select(Booking).where(Booking.trip_id == trip_id, holding(now))
    q = q.where(Booking.kind == kind) if kind else q.where(Booking.plan_item_id == item_id)
    existing = db.scalar(q)
    if existing:
        raise LimingError(f"Already booked: {existing.reference} ({existing.status})")


def _sitting(item):
    return "lunch" if minutes(item.starts) < 16 * 60 else "dinner"


def _sold_out(left, unit, name, wanted):
    if left <= 0:
        return f"Sorry, {name} is fully booked"
    return f"Only {left} {unit}{'s' if left != 1 else ''} left at {name}, and you need {wanted}"


def _reference():
    """'LIM-7KQ2XM': easy to read out, random so it can't be guessed. No 0/O or 1/I."""
    return "LIM-" + "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))


def _new(db, trip, user, kind, now, **fields):
    b = Booking(reference=_reference(), trip_id=trip.id, user_id=user.id, kind=kind, status="held", created_at=now,
                held_until=now + timedelta(minutes=HOLD_MINUTES), **fields)
    db.add(b)
    db.flush()
    return b


def _own_booking(db, user, booking_id, lock=False):
    b = _get(db, Booking, booking_id, lock=lock)
    if b.user_id != user.id:
        raise NotFound("Booking not found")
    return b
