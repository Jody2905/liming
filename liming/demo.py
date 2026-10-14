"""A printed walkthrough: three travellers answer the questions and get very different plans,
then one of them edits theirs.

    python -m liming demo

It uses a throwaway database and a pretend "today" (Monday 2 November 2026), so the
output is the same every time.
"""

import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from . import services
from .catalogue import seed_catalogue
from .db import create_tables, make_engine, session_factory
from .models import DIETS, INTERESTS, STAY_STYLES, Activity
from .money import fmt
from .services import LimingError

TODAY = datetime(2026, 11, 2, 10, 0)
PASSWORD = "Demo-password-2026"  # noqa: S105 - throwaway demo account


def run(out=print):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        engine = make_engine(f"sqlite:///{Path(folder) / 'demo.db'}")
        create_tables(engine)
        db = session_factory(engine)()
        try:
            _walkthrough(db, out)
        finally:
            db.close()
            engine.dispose()


def show_plan(db, user, trip_id, out, reasons=True):
    view = services.plan_for(db, user, trip_id)
    t = view.trip
    out(f"   Stay: {t.stay.name} ({t.stay.area.name}). {view.stay_reason}")
    for day, items in view.days.items():
        out(f"   {day:%a %d %b}")
        for i in items:
            lock = " [locked]" if i.locked else ""
            out(f"      {i.starts:%H:%M}-{i.ends:%H:%M}  {i.title}{lock}"
                + (f"   {fmt(i.cost_cents)}" if i.cost_cents else ""))
            if reasons and i.kind in ("activity", "meal"):
                out(f"                   why: {i.reason}")
    totals = view.totals
    out(f"   Costs: stay {fmt(totals['stay_cents'])}, activities {fmt(totals['activities_cents'])}, "
        f"meals {fmt(totals['meals_cents'])}, getting around {fmt(totals['transport_cents'])}")
    out(f"   Total about {fmt(totals['total_cents'])} of a {fmt(totals['budget_cents'])} budget "
        f"({fmt(totals['left_cents'])} to spare)")
    for issue in view.issues:
        out(f"   WARNING: {issue.message}")
    return view


def _walkthrough(db, out):
    def step(title):
        out("")
        out(f"== {title} " + "=" * max(0, 76 - len(title)))

    def describe(a):
        loves = [INTERESTS[t] for t, w in a["interests"].items() if w == 2]
        likes = [INTERESTS[t] for t, w in a["interests"].items() if w == 1]
        people = f"{a['adults']} adult{'s' if a['adults'] > 1 else ''}" + (
            f" and {a['children']} children (youngest {a['youngest_age']})" if a.get("children") else "")
        out(f"   Answers: {people}, {(a['end_date'] - a['start_date']).days} nights from {a['start_date']:%a %d %b}, "
            f"budget {fmt(a['budget_cents'])}")
        out(f"            {a['pace']} pace, a {STAY_STYLES[a['stay_style']]}, {a['dining_style']} dining, "
            f"getting around by {a['transport'].replace('_', ' ')}"
            + (", " + " and ".join(DIETS[x] for x in sorted(a.get("diets", ()))) if a.get("diets") else ""))
        out(f"            loves {', '.join(loves) or 'nothing in particular'}"
            + (f"; likes {', '.join(likes)}" if likes else ""))

    dests = seed_catalogue(db)
    db.commit()
    jo = services.create_user(db, "jo@example.test", "Jo", PASSWORD, now=TODAY)
    start = date(2026, 11, 9)

    travellers = [
        ("Jo and Sam: beaches and nature, St Vincent", dict(
            title="Beach and rainforest week", destination_id=dests["VC"].id, start_date=start,
            end_date=start + timedelta(days=4), adults=2, budget_cents=350000, pace="balanced", stay_style="hotel",
            dining_style="mix", transport="taxi", interests={"beaches": 2, "nature": 2, "hiking": 1})),
        ("The Browne family: two kids, a villa, Grenada", dict(
            title="Family spice island", destination_id=dests["GD"].id, start_date=start,
            end_date=start + timedelta(days=4), adults=2, children=2, youngest_age=5, budget_cents=450000,
            pace="relaxed", stay_style="villa", dining_style="local", transport="hire_car",
            interests={"beaches": 2, "food": 1, "nature": 1})),
        ("Kemar: food and nightlife, vegetarian, Barbados", dict(
            title="Bajan food weekend", destination_id=dests["BB"].id, start_date=start + timedelta(days=2),
            end_date=start + timedelta(days=5), adults=1, budget_cents=200000, pace="packed", stay_style="boutique",
            dining_style="treat", transport="taxi", diets={"vegetarian"},
            interests={"food": 2, "nightlife": 2, "culture": 1})),
    ]
    trips = []
    for title, answers in travellers:
        step(title)
        describe(answers)
        trip = services.create_trip(db, jo, now=TODAY, **answers)
        trips.append(trip)
        show_plan(db, jo, trip.id, out, reasons=(len(trips) == 1))

    trip = trips[0]
    step("Rule: answers are checked before anything is planned")
    for change, label in (({"budget_cents": 20000}, "US$200 for two people, four nights"),
                          ({"interests": {}}, "no interests picked"),
                          ({"children": 1, "youngest_age": None}, "a child, but no age given")):
        try:
            services.create_trip(db, jo, now=TODAY, **{**travellers[0][1], **change})
            out(f"   !! expected {label} to be refused")
        except LimingError as e:
            out(f"   {label}: REFUSED: {e}")

    step("Editing: lock a favourite, then ask for something different")
    view = services.plan_for(db, jo, trip.id)
    keep = next(i for i in view.days[start + timedelta(days=1)] if i.kind == "activity")
    services.set_locked(db, jo, keep.id, True)
    out(f"   Locked: {keep.title} ({keep.day:%a} {keep.starts:%H:%M})")
    services.generate(db, jo, trip.id, now=TODAY, fresh=True)
    out("   Regenerated with 'something different'. The locked item stays put; the rest is new:")
    show_plan(db, jo, trip.id, out, reasons=False)

    step("Editing: swap an activity for one of the suggested alternatives")
    view = services.plan_for(db, jo, trip.id)
    target = next(i for i in view.days[start + timedelta(days=2)] if i.kind == "activity" and not i.locked)
    options = services.alternatives(db, jo, target.id)
    out(f"   Instead of {target.title}, these would fit the same gap:")
    for o in options:
        out(f"      {o.start_time:%H:%M}  {o.title}  ({o.reason})")
    services.swap(db, jo, target.id, activity_id=options[0].activity.id)
    out(f"   Swapped in {options[0].title}. It's locked now, so regenerating keeps it.")

    step("Editing: you're in charge, so a questionable move is allowed but flagged")
    market = db.scalar(select(Activity).where(Activity.name == "Kingstown market morning"))
    added = services.add_item(db, jo, trip.id, start + timedelta(days=3), "16:00", activity_id=market.id)
    out(f"   Added {added.title} at 16:00 on {added.day:%a}.")
    for issue in services.plan_for(db, jo, trip.id).issues:
        out(f"   WARNING: {issue.message}")
