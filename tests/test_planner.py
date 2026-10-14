"""The planner on its own: the rules every plan must keep, and how answers shape the plan."""

import random
from datetime import timedelta

import pytest

from liming import planner, services
from liming.models import INTERESTS
from liming.planner import Prefs, minutes, travel

from .conftest import d

COUNTRIES = ("VC", "BB", "LC", "GD", "DM")


def prefs(**changes):
    base = dict(start=d(9), end=d(14), adults=2, children=0, youngest_age=None, budget_cents=400000,
                pace="balanced", stay_style="hotel", dining_style="mix", transport="taxi", day_start="normal",
                step_free=False, interests={"beaches": 2, "nature": 1}, diets=frozenset())
    base.update(changes)
    return Prefs(**base)


@pytest.fixture
def cats(db, dest):
    return {code: services.load_catalogue(db, dest[code]) for code in COUNTRIES}


def random_prefs(rng):
    nights = rng.randint(1, 9)
    start = d(rng.randint(3, 20))
    children = rng.choice([0, 0, 0, 1, 2, 3])
    adults = rng.randint(1, 4)
    people = adults + children
    picked = rng.sample(sorted(INTERESTS), rng.randint(1, 4))
    return prefs(start=start, end=start + timedelta(days=nights), adults=adults, children=children,
                 youngest_age=rng.randint(0, 15) if children else None,
                 budget_cents=rng.choice([60, 120, 250, 500]) * 100 * people * nights,
                 pace=rng.choice(["relaxed", "balanced", "packed"]),
                 stay_style=rng.choice(["guesthouse", "hotel", "boutique", "resort", "villa"]),
                 dining_style=rng.choice(["local", "mix", "treat"]),
                 transport=rng.choice(["taxi", "hire_car", "bus"]),
                 day_start=rng.choice(["early", "normal", "late"]), step_free=rng.random() < 0.15,
                 interests={t: rng.choice([1, 2]) for t in picked},
                 diets=frozenset(rng.sample(["vegetarian", "vegan", "gluten_free"], rng.choice([0, 0, 0, 1, 2]))),
                 variety=rng.choice([0, 0, 1, 2]))


# ---- The rules every plan keeps, checked on 150 random travellers ------------------------------------

def test_every_plan_keeps_the_rules(cats):
    rng = random.Random(2026)
    checked = 0
    for n in range(150):
        p = random_prefs(rng)
        code = COUNTRIES[n % len(COUNTRIES)]
        try:
            plan = planner.plan_trip(p, cats[code])
        except planner.PlanError:
            continue                                         # e.g. no stay sleeps this group step-free
        checked += 1
        label = f"#{n} {code} {p}"
        items = plan.items
        stay = plan.stay

        # The planner's own checker finds nothing wrong (apart from money, checked separately)
        problems = [i.message for i in planner.check(p, stay, items) if i.day is not None]
        assert problems == [], label

        # The stay suits the group
        assert planner.rooms_needed(stay, p) <= min(stay.rooms_total, 4), label
        assert stay.kid_friendly or not p.children, label
        assert stay.step_free or not p.step_free, label

        acts = [i for i in items if i.activity]
        for i in acts:
            a = i.activity
            assert planner.suits_group(a, p), (label, a.name)
            assert planner.interest_points(a, p) or a.highlight, (label, a.name, "nobody asked for this")
        assert len({i.activity.id for i in acts}) == len(acts), label           # nothing twice

        for i in items:
            assert i.reason, (label, i.title)
            if i.restaurant:
                assert planner.suits_diets(i.restaurant, p.diets), (label, i.title)
                assert i.restaurant.price_band in planner.BANDS[p.dining_style], (label, i.title)
            if i.area is not None and i.area.island != stay.area.island:
                back = i.ends + travel(i.area, stay.area, p.transport)
                assert back <= planner.LAST_FERRY and i.starts < 18 * 60, (label, i.title, "stranded")

        for k in range(1, p.nights):                           # every full day
            day = p.start + timedelta(days=k)
            today = [i for i in items if i.day == day]
            main = [i for i in today if i.activity and not i.activity.includes_dinner and i.starts < 18 * 60]
            assert len(main) <= {"relaxed": 1, "balanced": 2, "packed": 3}[p.pace], (label, day)
            lunch = any(i.kind == "meal" and i.starts < 16 * 60 for i in today) or any(
                i.activity and i.activity.includes_lunch for i in today)
            dinner = any(i.kind == "meal" and i.starts >= 16 * 60 for i in today) or any(
                i.activity and i.activity.includes_dinner for i in today)
            assert lunch and dinner, (label, day)
        assert [i.title for i in items if i.kind == "stay"] == [f"Check in at {stay.name}",
                                                                 f"Check out of {stay.name}"], label
    assert checked >= 120


def test_a_comfortable_budget_is_not_overspent(cats):
    rng = random.Random(7)
    for n in range(40):
        p = random_prefs(rng)
        p.budget_cents = 30000 * p.people * p.nights           # US$300 a person a night
        try:
            plan = planner.plan_trip(p, cats[COUNTRIES[n % 5]])
        except planner.PlanError:
            continue
        totals = planner.summarise(p, plan.stay, plan.items)
        assert totals["total_cents"] <= p.budget_cents, (n, totals)


# ---- How the answers shape the plan ------------------------------------------------------------------

def tags_in(plan):
    return [t for i in plan.items if i.activity for t in i.activity.tag_names]


def test_interests_steer_the_plan(cats):
    beach = planner.plan_trip(prefs(interests={"beaches": 2}), cats["GD"])
    hikes = planner.plan_trip(prefs(interests={"hiking": 2}, pace="packed"), cats["DM"])
    every_beach = {a.name for a in cats["GD"].activities if "beaches" in a.tag_names}
    assert every_beach <= {i.activity.name for i in beach.items if i.activity}          # a beach lover gets them all
    assert tags_in(hikes).count("hiking") >= 3
    boiling = next(i for i in hikes.items if i.title == "Boiling Lake hike")
    assert boiling.start_time.hour == 7 and boiling.reason.startswith("An early start (07:00), but worth it.")
    assert all("You love" in i.reason or "local favourite" in i.reason for i in beach.items if i.activity)


def test_children_never_get_activities_they_are_too_young_for(cats):
    family = planner.plan_trip(prefs(children=2, youngest_age=5, interests={"hiking": 2, "nightlife": 2},
                                     pace="packed"), cats["VC"])
    names = {i.activity.name for i in family.items if i.activity}
    assert "La Soufrière volcano hike" not in names                     # ages 10+
    assert all(i.activity.min_age <= 5 for i in family.items if i.activity)
    assert family.stay.kid_friendly
    assert "Fine for" in next(i.reason for i in family.items if i.activity)


def test_step_free_trips_only_get_step_free_places(cats):
    p = prefs(step_free=True, interests={"culture": 2, "food": 2, "shopping": 1})
    plan = planner.plan_trip(p, cats["BB"])
    assert plan.stay.step_free
    assert all(i.activity.step_free for i in plan.items if i.activity)
    assert all(i.restaurant.step_free for i in plan.items if i.restaurant)


def test_vegan_meals(cats):
    plan = planner.plan_trip(prefs(diets=frozenset({"vegan"}), dining_style="mix"), cats["DM"])
    meals = [i for i in plan.items if i.kind == "meal"]
    assert meals and all(i.restaurant is None or i.restaurant.vegan for i in meals)
    assert any("vegan options" in i.reason for i in meals)


def test_a_friday_fish_fry_is_dinner_for_food_lovers(cats):
    plan = planner.plan_trip(prefs(interests={"food": 2, "nightlife": 1}), cats["BB"])
    friday = [i for i in plan.items if i.day == d(13)]                 # 13 November 2026 is a Friday
    fry = next(i for i in friday if i.activity and i.activity.includes_dinner)
    assert fry.title == "Oistins Friday fish fry" and "It's dinner too" in fry.reason
    assert not any(i.kind == "meal" and i.starts >= 16 * 60 for i in friday)
    assert not any(i.activity and i.activity.name == "Oistins Friday fish fry" for i in plan.items if i.day != d(13))


def test_pace_sets_how_full_the_days_are(cats):
    """Across many trips, packed days hold more than balanced ones, and balanced more than relaxed."""
    rng = random.Random(11)
    totals = {"relaxed": [0, 0], "balanced": [0, 0], "packed": [0, 0]}
    for n in range(60):
        base = random_prefs(rng)
        for pace in totals:
            base.pace = pace
            try:
                plan = planner.plan_trip(base, cats[COUNTRIES[n % 5]])
            except planner.PlanError:
                continue
            totals[pace][0] += len([i for i in plan.items if i.activity and i.day not in (base.start, base.end)])
            totals[pace][1] += base.nights - 1
    per_day = {pace: done / max(days, 1) for pace, (done, days) in totals.items()}
    assert per_day["relaxed"] < per_day["balanced"] < per_day["packed"], per_day


def test_a_tight_budget_sticks_to_free_things(cats):
    p = prefs(budget_cents=6000 * 2 * 5, stay_style="guesthouse", dining_style="local")
    plan = planner.plan_trip(p, cats["VC"])
    assert any("free things to do" in n for n in plan.notes)
    assert all(i.cost_cents == 0 for i in plan.items if i.activity)


def test_the_stay_matches_the_style_and_says_why(cats):
    p = prefs(stay_style="villa", adults=5)
    plan = planner.plan_trip(p, cats["GD"])
    assert plan.stay.style == "villa"
    assert "A villa with a kitchen, as you asked" in plan.stay_reason
    assert "% of your budget" in plan.stay_reason
    big = planner.plan_trip(prefs(stay_style="boutique", adults=6), cats["LC"])        # boutiques sleep 2
    assert planner.rooms_needed(big.stay, prefs(adults=6)) <= 4


def test_same_answers_same_plan_and_something_different_on_request(cats):
    a = planner.plan_trip(prefs(), cats["LC"])
    b = planner.plan_trip(prefs(), cats["LC"])
    c = planner.plan_trip(prefs(variety=1), cats["LC"])
    titles = lambda plan: [(i.day, i.starts, i.title) for i in plan.items]  # noqa: E731
    assert titles(a) == titles(b)
    assert titles(a) != titles(c)


def test_nobody_is_stranded_on_another_island(cats):
    # Staying on Bequia, everything on mainland St Vincent is a day trip
    bequia = next(s for s in cats["VC"].stays if s.name == "Admiralty Sands Resort")
    plan = planner.plan_trip(prefs(stay_style="resort", interests={"hiking": 2, "nature": 2}, pace="packed"),
                             cats["VC"], stay=bequia)
    away = [i for i in plan.items if i.area and i.area.island != "Bequia"]
    assert away, "expected at least one day trip to St Vincent"
    assert all(i.starts < 18 * 60 for i in away)
    assert any("ferry" in i.reason for i in away)


def test_travel_times():
    class A:
        def __init__(self, id, island, lat, lng):
            self.id, self.island, self.lat, self.lng = id, island, lat, lng
    town, beach, other = A(1, "X", 13.10, -61.20), A(2, "X", 13.20, -61.20), A(3, "Y", 13.10, -61.20)
    assert travel(town, town, "taxi") == 10
    by_car, by_bus = travel(town, beach, "taxi"), travel(town, beach, "bus")
    assert 25 <= by_car <= 35 and by_bus > by_car
    assert travel(town, other, "taxi") >= planner.FERRY_MINUTES


# ---- The catalogue itself makes sense -----------------------------------------------------------------

def test_catalogue_times_add_up(cats):
    for code, cat in cats.items():
        for a in cat.activities:
            assert minutes(a.opens) + a.minutes <= minutes(a.closes), (code, a.name, "can't fit in a day")
            for s in a.start_times:
                assert minutes(a.opens) <= minutes(s.starts), (code, a.name, "starts before opening")
                assert minutes(s.starts) + a.minutes <= minutes(a.closes), (code, a.name, "runs past closing")
        styles = {s.style for s in cat.stays}
        assert styles == {"guesthouse", "hotel", "boutique", "resort", "villa"}, code
        assert any(r.lunch for r in cat.restaurants) and any(r.dinner for r in cat.restaurants), code
        assert any(a.highlight for a in cat.activities), code
