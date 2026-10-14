"""Changing the plan: lock, move, swap, add, remove, regenerate, and pick another stay."""

import threading

import pytest

from liming import services
from liming.models import User
from liming.services import LimingError

from .conftest import NOW, activity, answers, d, restaurant, stay


def day_items(db, jo, trip, day):
    return services.plan_for(db, jo, trip.id).days[day]


def first(db, jo, trip, day, kind):
    return next(i for i in day_items(db, jo, trip, day) if i.kind == kind)


def snapshot(db, jo, trip):
    return [(i.day, i.starts, i.title) for items in services.plan_for(db, jo, trip.id).days.values() for i in items]


# ---- Locking and regenerating ---------------------------------------------------------------------

def test_locked_items_survive_something_different(db, jo, trip):
    keep = first(db, jo, trip, d(11), "activity")
    services.set_locked(db, jo, keep.id, True)
    before = snapshot(db, jo, trip)
    services.generate(db, jo, trip.id, now=NOW, fresh=True)
    after = snapshot(db, jo, trip)
    assert after != before                                                     # something did change
    assert (keep.day, keep.starts, keep.title) in after                        # but not the locked item
    assert sum(1 for _, _, title in after if title == keep.title) == 1         # and it isn't added twice
    assert services.plan_for(db, jo, trip.id).issues == []


def test_regenerating_one_day_leaves_the_others_alone(db, jo, trip):
    before = snapshot(db, jo, trip)
    services.regenerate_day(db, jo, trip.id, d(12), now=NOW)
    after = snapshot(db, jo, trip)
    assert [x for x in after if x[0] != d(12)] == [x for x in before if x[0] != d(12)]
    assert [x for x in after if x[0] == d(12)] != [x for x in before if x[0] == d(12)]
    assert services.plan_for(db, jo, trip.id).issues == []


# ---- Moving and retiming --------------------------------------------------------------------------

def test_moving_an_item_locks_it_and_the_plan_fits_around_it(db, jo, trip):
    beach = first(db, jo, trip, d(10), "activity")
    moved = services.move_item(db, jo, beach.id, d(12), "15:00")
    assert (moved.day, moved.starts.hour, moved.locked) == (d(12), 15, True)
    assert moved.ends.hour * 60 + moved.ends.minute - 15 * 60 == beach.ends.hour * 60 + beach.ends.minute - (
        beach.starts.hour * 60 + beach.starts.minute)                         # same length
    services.generate(db, jo, trip.id, now=NOW)                               # replan around it
    assert (d(12), moved.starts, moved.title) in snapshot(db, jo, trip)
    assert services.plan_for(db, jo, trip.id).issues == []


def test_moves_that_break_a_rule_are_allowed_but_flagged(db, jo, trip):
    market = services.add_item(db, jo, trip.id, d(10), "10:00", activity_id=activity(db, "Kingstown market morning").id)
    services.move_item(db, jo, market.id, d(13), "16:00")                     # market closes at 14:00
    issues = [i.message for i in services.plan_for(db, jo, trip.id).issues]
    assert "Kingstown market morning is open 07:00 to 14:00." in issues


def test_moves_are_checked_for_sense(db, jo, trip):
    item = first(db, jo, trip, d(10), "activity")
    with pytest.raises(LimingError, match="isn't part of this trip"):
        services.move_item(db, jo, item.id, d(20), "10:00")
    with pytest.raises(LimingError, match="past midnight"):
        services.move_item(db, jo, item.id, d(10), "23:30")
    with pytest.raises(LimingError, match="Times look like 09:30"):
        services.move_item(db, jo, item.id, d(10), "half ten")
    check_in = first(db, jo, trip, d(9), "stay")
    with pytest.raises(LimingError, match="Change the stay instead"):
        services.move_item(db, jo, check_in.id, d(10), "10:00")
    with pytest.raises(LimingError, match="end after it starts"):
        services.retime_item(db, jo, item.id, "11:00", "10:00")


# ---- Swapping ------------------------------------------------------------------------------------------

def test_alternatives_fit_the_gap_and_say_why(db, jo, trip):
    target = first(db, jo, trip, d(11), "activity")
    options = services.alternatives(db, jo, target.id)
    assert 1 <= len(options) <= 5
    days = services.plan_for(db, jo, trip.id).days.values()
    planned = {i.activity_id for items in days for i in items if i.activity_id}
    for o in options:
        assert o.activity.id not in planned                                    # not something already in the plan
        assert o.reason and o.day == d(11)

    services.swap(db, jo, target.id, activity_id=options[0].activity.id)
    view = services.plan_for(db, jo, trip.id)
    swapped = next(i for i in view.days[d(11)] if i.id == target.id)
    assert (swapped.title, swapped.locked) == (options[0].title, True)
    assert view.issues == []                                                   # it fits where it went


def test_swap_a_meal(db, jo, trip):
    lunch = first(db, jo, trip, d(10), "meal")
    options = services.alternatives(db, jo, lunch.id)
    assert options and all(o.kind == "meal" and o.restaurant for o in options)
    services.swap(db, jo, lunch.id, restaurant_id=options[0].restaurant.id)
    assert first(db, jo, trip, d(10), "meal").restaurant_id == options[0].restaurant.id
    with pytest.raises(LimingError, match="a meal for a meal"):
        services.swap(db, jo, lunch.id, activity_id=activity(db, "Botanic Gardens").id)


def test_swapping_in_anything_from_the_country(db, jo, dest, trip):
    item = first(db, jo, trip, d(10), "activity")
    services.swap(db, jo, item.id, activity_id=activity(db, "La Soufrière volcano hike").id)   # an odd fit
    swapped = next(i for i in day_items(db, jo, trip, d(10)) if i.id == item.id)
    assert swapped.title == "La Soufrière volcano hike" and swapped.reason == "You chose this."
    with pytest.raises(services.NotFound, match="isn't in this country"):
        services.swap(db, jo, item.id, activity_id=activity(db, "Grand Anse Beach").id)       # that's Grenada


# ---- Adding and removing --------------------------------------------------------------------------------

def test_add_your_own_things(db, jo, trip):
    mine = services.add_item(db, jo, trip.id, d(12), "16:00", "17:30", title="Call home", cost_cents=0)
    dinner = services.add_item(db, jo, trip.id, d(13), "19:30", restaurant_id=restaurant(db, "Bayview Kitchen").id)
    falls = services.add_item(db, jo, trip.id, d(11), "14:00", activity_id=activity(db, "Dark View Falls").id)
    assert (mine.kind, mine.added_by, mine.locked) == ("custom", "you", True)
    assert (dinner.title, dinner.ends.hour) == ("Dinner at Bayview Kitchen", 21)
    assert falls.cost_cents == 2 * 500 and (falls.ends.hour, falls.ends.minute) == (16, 0)
    services.generate(db, jo, trip.id, now=NOW, fresh=True)
    titles = [t for _, _, t in snapshot(db, jo, trip)]
    assert {"Call home", "Dinner at Bayview Kitchen", "Dark View Falls"} <= set(titles)
    assert titles.count("Dark View Falls") == 1                                # the planner won't add it again
    with pytest.raises(LimingError, match="say what it is"):
        services.add_item(db, jo, trip.id, d(12), "16:00", "17:00", title=" ")


def test_remove(db, jo, trip):
    item = first(db, jo, trip, d(10), "activity")
    services.remove_item(db, jo, item.id)
    assert item.id not in [i.id for i in day_items(db, jo, trip, d(10))]
    with pytest.raises(LimingError, match="Change the stay instead"):
        services.remove_item(db, jo, first(db, jo, trip, d(14), "stay").id)


# ---- Choosing a different stay ------------------------------------------------------------------------

def test_choose_another_stay(db, jo, trip):
    choices = services.stay_choices(db, jo, trip.id)
    assert choices[0][0].id == trip.stay_id and all(why for _, _, why in choices)
    guesthouse = stay(db, "Breadfruit Guesthouse")
    services.choose_stay(db, jo, trip.id, guesthouse.id)
    assert first(db, jo, trip, d(9), "stay").title == "Check in at Breadfruit Guesthouse"
    assert first(db, jo, trip, d(14), "stay").title == "Check out of Breadfruit Guesthouse"
    services.generate(db, jo, trip.id, now=NOW)
    assert services.get_trip(db, jo, trip.id).stay.name == "Breadfruit Guesthouse"   # your choice is kept


def test_a_stay_that_does_not_suit_the_group_is_refused(db, jo, dest):
    family = services.create_trip(db, jo, now=NOW, **answers(dest, children=1, youngest_age=4))
    with pytest.raises(LimingError, match="doesn't fit your group"):
        services.choose_stay(db, jo, family.id, stay(db, "Blue Lantern House").id)      # adults only


# ---- Two regenerations at once ---------------------------------------------------------------------------

def test_two_regenerations_at_once_do_not_double_the_plan(Session, db, jo, trip):
    count = services.count_items(db, trip.id)
    jo_id, trip_id = jo.id, trip.id                  # plain ids: the test's own objects must not be touched
    db.rollback()                                    # (touching them would re-open a transaction and hold a lock)
    start = threading.Barrier(2, timeout=30)
    errors = []

    def regenerate():
        session = Session()
        me = session.get(User, jo_id)                # each thread loads its own copy of the user...
        session.expunge(me)
        session.rollback()                           # ...and ends that read before the race starts
        start.wait()
        try:
            services.generate(session, me, trip_id, now=NOW, fresh=True)
        except Exception as e:                       # pragma: no cover - reported below
            errors.append(e)
        finally:
            session.close()

    threads = [threading.Thread(target=regenerate) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    view = services.plan_for(db, jo, trip.id)
    assert abs(services.count_items(db, trip.id) - count) <= 4                # same shape of plan, not doubled
    assert [i.title for items in view.days.values() for i in items if i.kind == "stay"] == [
        f"Check in at {view.trip.stay.name}", f"Check out of {view.trip.stay.name}"]
    assert view.issues == []
