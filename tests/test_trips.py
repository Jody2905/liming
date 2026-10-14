"""Accounts, the questions a traveller answers, and generating the first plan."""

import pytest
from sqlalchemy.exc import IntegrityError

from liming import services
from liming.models import Trip
from liming.services import LimingError, NotFound

from .conftest import NOW, PASSWORD, answers, d


def test_accounts(db):
    services.create_user(db, "Jo@Example.test", "Jo", PASSWORD, now=NOW)
    with pytest.raises(LimingError, match="already an account"):
        services.create_user(db, "jo@example.TEST", "Jo again", PASSWORD, now=NOW)
    assert services.authenticate(db, "JO@example.test", PASSWORD).name == "Jo"
    assert services.authenticate(db, "jo@example.test", "wrong-password") is None
    with pytest.raises(LimingError, match="at least 10"):
        services.create_user(db, "x@example.test", "X", "short", now=NOW)


def test_answering_the_questions_builds_a_plan(db, jo, trip):
    view = services.plan_for(db, jo, trip.id)
    assert list(view.days) == [d(n) for n in range(9, 15)]              # every day, arrival to departure
    assert view.days[d(9)][0].title.startswith("Check in at")
    assert view.days[d(14)][-1].title.startswith("Check out of")
    assert all(view.days[d(n)] for n in range(10, 14))
    assert view.issues == []
    assert view.stay_reason.startswith("A comfortable hotel, as you asked.")
    t = view.totals
    assert t["total_cents"] == t["stay_cents"] + t["activities_cents"] + t["meals_cents"] + t["transport_cents"]
    assert t["left_cents"] == 400000 - t["total_cents"] > 0
    assert trip.planned_at == NOW


@pytest.mark.parametrize("change, message", [
    ({"title": "  "}, "give the trip a name"),
    ({"destination_id": 999}, "choose where you're going"),
    ({"start_date": d(1)}, "can't start in the past"),
    ({"end_date": d(9)}, "last day must be after the first"),
    ({"end_date": d(30)}, "up to 14 nights"),
    ({"adults": 0}, "Adults must be between 1 and 8"),
    ({"children": 2, "youngest_age": None}, "youngest child's age"),
    ({"budget_cents": 40000}, r"at least US\$500\.00"),                   # 2 people x 5 nights x US$50
    ({"pace": "frantic"}, "choose a pace"),
    ({"interests": {}}, "at least one thing"),
    ({"interests": {"beaches": 3}}, "1 \\(like\\) or 2 \\(love\\)"),
    ({"diets": {"carnivore"}}, "Unknown food need"),
])
def test_answers_are_checked(db, jo, dest, change, message):
    with pytest.raises(LimingError, match=message):
        services.create_trip(db, jo, now=NOW, **answers(dest, **change))


def test_youngest_age_is_dropped_when_there_are_no_children(db, jo, dest):
    trip = services.create_trip(db, jo, now=NOW, **answers(dest, children=0, youngest_age=7))
    assert trip.youngest_age is None


def test_someone_elses_trip_looks_missing(db, jo, friend, trip):
    for action in (lambda: services.plan_for(db, friend, trip.id),
                   lambda: services.generate(db, friend, trip.id, now=NOW),
                   lambda: services.update_answers(db, friend, trip.id, now=NOW, pace="packed"),
                   lambda: services.delete_trip(db, friend, trip.id),
                   lambda: services.add_item(db, friend, trip.id, d(10), "15:00", "16:00", title="Sneaky")):
        with pytest.raises(NotFound, match="Trip not found"):
            action()
    item = services.plan_for(db, jo, trip.id).days[d(10)][0]
    for action in (lambda: services.remove_item(db, friend, item.id),
                   lambda: services.alternatives(db, friend, item.id),
                   lambda: services.set_locked(db, friend, item.id, True)):
        with pytest.raises(NotFound):
            action()


def test_changing_answers_and_replanning(db, jo, dest, trip):
    services.update_answers(db, jo, trip.id, now=NOW, end_date=d(12), pace="relaxed")
    view = services.plan_for(db, jo, trip.id)
    assert max(i.day for items in view.days.values() for i in items) <= d(12)      # days past the end are gone
    services.generate(db, jo, trip.id, now=NOW)
    view = services.plan_for(db, jo, trip.id)
    assert list(view.days) == [d(9), d(10), d(11), d(12)]
    assert view.days[d(12)][-1].title.startswith("Check out of")
    assert len([i for i in view.days[d(10)] if i.kind == "activity"]) <= 1          # relaxed now

    services.update_answers(db, jo, trip.id, now=NOW, destination_id=dest["BB"])
    assert services.count_items(db, trip.id) == 0                                    # a new country starts fresh
    services.generate(db, jo, trip.id, now=NOW)
    assert services.plan_for(db, jo, trip.id).trip.stay.area.destination.code == "BB"


def test_database_backs_up_the_rules(db, jo, trip):
    with pytest.raises(IntegrityError):
        db.query(Trip).filter_by(id=trip.id).update({"children": 1})                 # no youngest age given
        db.commit()
    db.rollback()
    with pytest.raises(IntegrityError):
        db.query(Trip).filter_by(id=trip.id).update({"pace": "frantic"})
        db.commit()
    db.rollback()
