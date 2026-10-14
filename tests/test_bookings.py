"""Booking the stay, activities and tables: holds, capacity, confirming, cancelling, and the plan's guards."""

import threading
from datetime import datetime, timedelta

import pytest

from liming import bookings, services
from liming.bookings import SoldOut
from liming.models import Booking, User
from liming.services import LimingError, NotFound

from .conftest import NOW, PASSWORD, activity, answers, d, restaurant, stay

LATER = NOW + timedelta(minutes=2)


def add(db, user, trip, name, day, at):
    return services.add_item(db, user, trip.id, day, at, activity_id=activity(db, name).id)


def lunch(db, user, trip, name, day, at="12:30"):
    return services.add_item(db, user, trip.id, day, at, restaurant_id=restaurant(db, name).id)


# ---- Activities ----------------------------------------------------------------------------------------

def test_hold_then_confirm_an_activity(db, jo, trip):
    paddle = add(db, jo, trip, "Stand-up paddleboard lesson", d(10), "09:00")
    b = bookings.hold_item(db, jo, paddle.id, now=NOW)
    assert (b.kind, b.status, b.quantity, b.total_cents) == ("activity", "held", 2, 9000)
    assert b.reference.startswith("LIM-") and b.held_until == NOW + timedelta(minutes=15)
    assert bookings.places_left(db, activity(db, "Stand-up paddleboard lesson"), datetime(2026, 11, 10, 9), NOW) == 6
    bookings.confirm(db, jo, b.id, now=LATER)
    assert db.get(Booking, b.id).status == "confirmed"
    assert bookings.booked_cents(db, trip.id) == 9000


def test_activities_are_booked_at_their_set_times(db, jo, trip):
    wrong = add(db, jo, trip, "Stand-up paddleboard lesson", d(10), "10:00")
    with pytest.raises(LimingError, match=r"starts at 09:00, 14:00\. Move it"):
        bookings.hold_item(db, jo, wrong.id, now=NOW)
    beach = add(db, jo, trip, "Owia salt pond swim", d(11), "14:00")
    with pytest.raises(LimingError, match="doesn't need booking: just turn up"):
        bookings.hold_item(db, jo, beach.id, now=NOW)
    sunday = add(db, jo, trip, "Vincy cooking class", d(9), "14:00")                    # closed Mondays
    with pytest.raises(LimingError, match="doesn't run on Mondays"):
        bookings.hold_item(db, jo, sunday.id, now=NOW)


def test_an_activity_fills_up(db, jo, friend, dest, trip):
    big = services.create_trip(db, friend, now=NOW, **answers(dest, adults=7, budget_cents=900000))
    mine = add(db, jo, trip, "Stand-up paddleboard lesson", d(10), "09:00")
    theirs = add(db, friend, big, "Stand-up paddleboard lesson", d(10), "09:00")
    bookings.hold_item(db, jo, mine.id, now=NOW)                                          # 2 of 8 places
    with pytest.raises(SoldOut, match="Only 6 places left at Stand-up paddleboard lesson at 09:00, and you need 7"):
        bookings.hold_item(db, friend, theirs.id, now=NOW)


def test_a_lapsed_hold_frees_the_space_and_cannot_be_confirmed(db, jo, friend, dest, trip):
    big = services.create_trip(db, friend, now=NOW, **answers(dest, adults=7, budget_cents=900000))
    mine = add(db, jo, trip, "Stand-up paddleboard lesson", d(10), "09:00")
    b = bookings.hold_item(db, jo, mine.id, now=NOW)
    after = NOW + timedelta(minutes=15)
    theirs = add(db, friend, big, "Stand-up paddleboard lesson", d(10), "09:00")
    bookings.hold_item(db, friend, theirs.id, now=after)                                  # space was released
    with pytest.raises(LimingError, match="run out"):
        bookings.confirm(db, jo, b.id, now=after)
    assert db.get(Booking, b.id).status == "expired"


# ---- Tables and the stay ------------------------------------------------------------------------------------

def test_tables_are_free_and_counted_per_sitting(db, jo, trip):
    meal = lunch(db, jo, trip, "Bayview Kitchen", d(10))
    b = bookings.hold_item(db, jo, meal.id, now=NOW)
    assert (b.kind, b.total_cents, b.title) == ("table", 0, "Table for 2 at Bayview Kitchen")
    bayview = restaurant(db, "Bayview Kitchen")
    assert bookings.seats_left(db, bayview, d(10), "lunch", NOW) == 38
    assert bookings.seats_left(db, bayview, d(10), "dinner", NOW) == 40                  # a different sitting
    bookings.confirm(db, jo, b.id, now=LATER)
    assert bookings.refund_quote(db, jo, b.id, now=LATER).reason == "There's no charge to book a table"


def test_book_the_stay_for_every_night(db, jo, trip):
    b = bookings.hold_stay(db, jo, trip.id, now=NOW)
    inn = services.get_trip(db, jo, trip.id).stay
    assert (b.kind, b.quantity, b.units, b.total_cents) == ("stay", 1, 5, inn.nightly_cents * 5)
    assert services.get_trip(db, jo, trip.id).stay_locked
    with pytest.raises(LimingError, match="Already booked"):
        bookings.hold_stay(db, jo, trip.id, now=NOW)


def test_rooms_run_out_night_by_night(db, jo, friend, dest):
    first = services.create_trip(db, jo, now=NOW, **answers(dest, adults=8, stay_style="guesthouse",
                                                             budget_cents=900000))
    services.choose_stay(db, jo, first.id, stay(db, "Breadfruit Guesthouse").id)          # 6 rooms; 8 people need 4
    bookings.hold_stay(db, jo, first.id, now=NOW)
    second = services.create_trip(db, friend, now=NOW, **answers(dest, adults=8, stay_style="guesthouse",
                                                                 start_date=d(13), end_date=d(16),
                                                                 budget_cents=900000))
    services.choose_stay(db, friend, second.id, stay(db, "Breadfruit Guesthouse").id)
    with pytest.raises(SoldOut, match="Only 2 rooms left at Breadfruit Guesthouse, and you need 4"):
        bookings.hold_stay(db, friend, second.id, now=NOW)                                # 13 Nov overlaps
    services.update_answers(db, friend, second.id, now=NOW, start_date=d(14), end_date=d(17))
    services.generate(db, friend, second.id, now=NOW)
    services.choose_stay(db, friend, second.id, stay(db, "Breadfruit Guesthouse").id)
    assert bookings.hold_stay(db, friend, second.id, now=NOW).quantity == 4              # check-out day is free


# ---- Refunds -------------------------------------------------------------------------------------------------

def test_cancellation_policies(db, jo, trip):
    s = bookings.hold_stay(db, jo, trip.id, now=NOW)
    bookings.confirm(db, jo, s.id, now=NOW)
    nightly = s.total_cents // 5
    checkin = datetime(2026, 11, 9, 15, 0)
    assert bookings.refund_quote(db, jo, s.id, now=checkin - timedelta(hours=49)).cents == s.total_cents
    late = bookings.refund_quote(db, jo, s.id, now=checkin - timedelta(hours=20))
    assert late.cents == s.total_cents - nightly and "first night" in late.reason

    paddle = add(db, jo, trip, "Stand-up paddleboard lesson", d(10), "09:00")
    a = bookings.hold_item(db, jo, paddle.id, now=NOW)
    bookings.confirm(db, jo, a.id, now=NOW)
    starts = datetime(2026, 11, 10, 9, 0)
    assert bookings.refund_quote(db, jo, a.id, now=starts - timedelta(hours=25)).cents == 9000
    assert bookings.refund_quote(db, jo, a.id, now=starts - timedelta(hours=2)).cents == 0
    with pytest.raises(LimingError, match="already started"):
        bookings.refund_quote(db, jo, a.id, now=starts)

    done, refund = bookings.cancel(db, jo, s.id, now=checkin - timedelta(hours=20))
    assert (done.status, done.refund_cents) == ("cancelled", s.total_cents - nightly)
    assert bookings.booked_cents(db, trip.id) == nightly + 9000                           # the kept night + the lesson


# ---- The plan respects bookings ------------------------------------------------------------------------

def test_booked_items_stay_put(db, jo, trip):
    paddle = add(db, jo, trip, "Stand-up paddleboard lesson", d(10), "09:00")
    services.set_locked(db, jo, paddle.id, False)                                         # unlocked before booking
    b = bookings.hold_item(db, jo, paddle.id, now=NOW)
    assert db.get(type(paddle), paddle.id).locked                                         # holding locks it
    for action in (lambda: services.move_item(db, jo, paddle.id, d(11), "09:00", now=NOW),
                   lambda: services.remove_item(db, jo, paddle.id, now=NOW),
                   lambda: services.retime_item(db, jo, paddle.id, "09:00", "11:00", now=NOW),
                   lambda: services.set_locked(db, jo, paddle.id, False, now=NOW),
                   lambda: services.swap(db, jo, paddle.id, activity_id=activity(db, "Botanic Gardens").id,
                                         now=NOW)):
        with pytest.raises(LimingError, match=f"is booked \\({b.reference}\\). Cancel the booking first"):
            action()
    services.generate(db, jo, trip.id, now=NOW, fresh=True)
    assert paddle.id in [i.id for i in services.plan_for(db, jo, trip.id).days[d(10)]]
    bookings.cancel(db, jo, b.id, now=LATER)
    services.move_item(db, jo, paddle.id, d(11), "14:00", now=LATER)                     # free to move again


def test_bookings_hold_the_trip_in_place(db, jo, dest, trip):
    s = bookings.hold_stay(db, jo, trip.id, now=NOW)
    with pytest.raises(LimingError, match="Cancel that booking before choosing another"):
        services.choose_stay(db, jo, trip.id, stay(db, "Breadfruit Guesthouse").id, now=NOW)
    with pytest.raises(LimingError, match="Cancel them before changing"):
        services.update_answers(db, jo, trip.id, now=NOW, end_date=d(12))
    services.update_answers(db, jo, trip.id, now=NOW, title="Renamed is fine", pace="packed")
    with pytest.raises(LimingError, match="Cancel this trip's bookings"):
        services.delete_trip(db, jo, trip.id, now=NOW)
    bookings.cancel(db, jo, s.id, now=NOW)
    services.delete_trip(db, jo, trip.id, now=NOW)
    assert db.query(Booking).count() == 0


def test_someone_elses_booking_looks_missing(db, jo, friend, trip):
    b = bookings.hold_stay(db, jo, trip.id, now=NOW)
    for action in (lambda: bookings.confirm(db, friend, b.id, now=NOW),
                   lambda: bookings.cancel(db, friend, b.id, now=NOW),
                   lambda: bookings.refund_quote(db, friend, b.id, now=NOW),
                   lambda: bookings.hold_stay(db, friend, trip.id, now=NOW)):
        with pytest.raises(NotFound):
            action()


# ---- Two groups grab the last places at once --------------------------------------------------------------

def test_the_last_places_go_to_exactly_one_group(Session, db, dest, monkeypatch):
    """Five groups of five press Book on an 8-place lesson at the same instant: exactly one gets in.

    To force the worst timing every run, each booking pauses right after counting the places left,
    waiting (up to a second) for the others to count too. Without the row lock they'd all see 8 free
    places and all get in. With it, each waits its turn and sees the places already taken.
    """
    groups = []
    for n in range(5):
        u = services.create_user(db, f"g{n}@example.test", f"G{n}", PASSWORD, now=NOW)
        t = services.create_trip(db, u, now=NOW, **answers(dest, adults=5, budget_cents=900000))
        item = add(db, u, t, "Stand-up paddleboard lesson", d(10), "09:00")
        groups.append((u.id, item.id))
    db.rollback()
    start = threading.Barrier(len(groups), timeout=30)
    all_counted = threading.Barrier(len(groups), timeout=1)
    outcomes = []
    count = bookings.places_left

    def count_then_pause(*args):
        left = count(*args)
        try:
            all_counted.wait()
        except threading.BrokenBarrierError:
            pass                                       # the others are (correctly) waiting for the lock
        return left

    monkeypatch.setattr(bookings, "places_left", count_then_pause)

    def book(user_id, item_id):
        session = Session()
        me = session.get(User, user_id)
        session.expunge(me)
        session.rollback()
        start.wait()
        try:
            bookings.hold_item(session, me, item_id, now=NOW)
            outcomes.append("booked")
        except SoldOut:
            outcomes.append("sold out")
        finally:
            session.close()

    threads = [threading.Thread(target=book, args=g) for g in groups]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(outcomes) == ["booked"] + ["sold out"] * 4
