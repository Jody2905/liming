"""The rule-based planner: turns a traveller's answers into a timed, day-by-day plan.

It never guesses at random. Every choice is the best-scoring option that passes the
hard rules, and every item carries a plain-English reason, so the plan can always say
why it looks the way it does. (Asking for "something different" adds a small, repeatable
nudge to the scores, so the next-best options get a turn.)

How a plan is built
  1. Choose a stay: matches the style asked for, sleeps everyone, fits the budget, and is
     close to the things this traveller will enjoy.
  2. Split the budget: the stay, an estimate for meals and getting around, and the rest
     for activities.
  3. Fill each day in order: morning activity, lunch, afternoon activity, dinner, evening.
     A slot takes the best candidate that is open that day, fits the time (travel
     included), suits the youngest traveller and any access needs, and is affordable.
     Being near the previous stop scores well, so each day stays in one part of the island.
  4. Items the traveller locked or added are kept exactly where they are, and the plan is
     built around them.

The planner works on plain objects and has no database code, so it's quick to test.
Times are minutes after midnight inside this module (12:30 -> 750).
"""

import math
from dataclasses import dataclass, field
from datetime import date, time, timedelta

from .models import DIETS as DIET_WORDS
from .models import INTERESTS, STAY_STYLES
from .money import fmt

DAY_START = {"early": 8 * 60, "normal": 9 * 60, "late": 10 * 60}
DINNER_FROM = {"early": 18 * 60 + 45, "normal": 19 * 60, "late": 19 * 60 + 30}
MORNING_ENDS = 13 * 60 + 15
LUNCH_FROM, LUNCH_LATEST, LUNCH_MINUTES = 12 * 60 + 15, 14 * 60, 75
AFTERNOON_ENDS = 18 * 60 + 30
DINNER_LATEST, DINNER_MINUTES = 20 * 60 + 45, 90
EVENING_LATEST = 21 * 60 + 15
LAST_FERRY = 18 * 60                     # be back on your own island by then
DAY_ENDS = 23 * 60 + 59
CHECK_IN, CHECK_OUT = (15 * 60, 15 * 60 + 30), (10 * 60 + 30, 11 * 60)
ARRIVAL_FREE_FROM = 15 * 60 + 45
EARLIEST_EARLY_START = 6 * 60 + 30

BANDS = {"local": {1, 2}, "mix": {1, 2, 3}, "treat": {2, 3, 4}}
IDEAL_BAND = {"local": 1, "mix": 2, "treat": 3}
MEAL_GUESS = {"local": 1800, "mix": 3000, "treat": 5500}        # cents a head, for the first budget split
SPEED_KMH = {"taxi": 35, "hire_car": 35, "bus": 22}
FERRY_MINUTES, FERRY_CENTS = 60, 2500                          # per crossing; cents per person
NEAR_STYLES = {("guesthouse", "hotel"), ("hotel", "boutique"), ("boutique", "resort"), ("hotel", "villa"),
               ("hotel", "resort")}
CHILD_MEAL_SHARE = 0.6
AVOID_PENALTY = 40                         # "something different": last time's picks only if nothing else fits
TAXI_DAY_GUESS = 15000                     # cents per taxi per day, for the first budget split


class PlanError(Exception):
    """The answers can't produce a plan (for example, nowhere to stay fits). Safe to show."""


# ======================================================================
# Inputs and outputs
# ======================================================================

@dataclass
class Prefs:
    start: date
    end: date
    adults: int
    children: int
    youngest_age: int | None
    budget_cents: int
    pace: str
    stay_style: str
    dining_style: str
    transport: str
    day_start: str
    step_free: bool
    interests: dict                       # tag -> 1 (like) or 2 (love)
    diets: frozenset
    variety: int = 0

    @property
    def people(self):
        return self.adults + self.children

    @property
    def nights(self):
        return (self.end - self.start).days

    @classmethod
    def from_trip(cls, trip):
        return cls(start=trip.start_date, end=trip.end_date, adults=trip.adults, children=trip.children,
                   youngest_age=trip.youngest_age, budget_cents=trip.budget_cents, pace=trip.pace,
                   stay_style=trip.stay_style, dining_style=trip.dining_style, transport=trip.transport,
                   day_start=trip.day_start, step_free=trip.step_free,
                   interests={i.tag: i.weight for i in trip.interests}, diets=frozenset(d.diet for d in trip.diets),
                   variety=trip.variety)


@dataclass
class Catalogue:
    areas: list
    stays: list
    activities: list
    restaurants: list


@dataclass
class Planned:
    """One item of a plan. `id` is set for items that already exist (kept ones)."""
    day: date
    starts: int
    ends: int
    kind: str
    title: str
    area: object = None
    cost_cents: int = 0
    reason: str = ""
    activity: object = None
    restaurant: object = None
    locked: bool = False
    added_by: str = "planner"
    notes: str = ""
    id: int | None = None

    @property
    def start_time(self):
        return to_time(self.starts)

    @property
    def end_time(self):
        return to_time(self.ends)


@dataclass
class Plan:
    stay: object
    stay_reason: str
    items: list
    notes: list = field(default_factory=list)


@dataclass
class Issue:
    day: date | None
    item_id: int | None
    message: str


# ======================================================================
# Small helpers
# ======================================================================

def minutes(t):
    return t.hour * 60 + t.minute


def to_time(m):
    return time(min(m, DAY_ENDS) // 60, min(m, DAY_ENDS) % 60)


def up15(m):
    return -(-m // 15) * 15


def clock(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def closed_on(thing, day):
    return str(day.weekday()) in (thing.closed_days or "")


def travel(a, b, transport):
    """Minutes to get from area a to area b. Same area: a short hop."""
    if a is None or b is None:
        return 0
    if a.id == b.id:
        return 10
    lat = math.radians((a.lat + b.lat) / 2)
    km = math.hypot((a.lat - b.lat) * 111, (a.lng - b.lng) * 111 * math.cos(lat)) * 1.35   # roads wind
    mins = 5 + km / SPEED_KMH[transport] * 60 + (10 if transport == "bus" else 0)
    if a.island != b.island:
        mins += FERRY_MINUTES
    return int(-(-round(mins) // 5) * 5)                 # to the next 5 minutes


def group_price(activity, prefs):
    return activity.price_cents * prefs.adults + activity.child_price_cents * prefs.children


def meal_price(restaurant, prefs):
    child = round(restaurant.avg_cents * CHILD_MEAL_SHARE / 100) * 100          # whole dollars
    return restaurant.avg_cents * prefs.adults + child * prefs.children


def interest_points(activity, prefs):
    return sum(prefs.interests.get(tag, 0) for tag in activity.tag_names)


def jitter(thing_id, variety):
    """A small, repeatable nudge used for "show me something different"."""
    if not variety:
        return 0.0
    return ((thing_id * 2654435761 + variety * 40503) % 1000) / 1000 * 6


def rooms_needed(stay, prefs):
    return math.ceil(prefs.people / stay.sleeps)


def stay_cost(stay, prefs):
    return stay.nightly_cents * rooms_needed(stay, prefs) * prefs.nights


def suits_group(activity, prefs):
    """Hard rules about who can do an activity."""
    if prefs.children and (activity.min_age >= 18 or activity.min_age > (prefs.youngest_age or 0)):
        return False
    if prefs.step_free and not activity.step_free:
        return False
    if activity.capacity is not None and activity.capacity < prefs.people:
        return False
    return True


def suits_diets(restaurant, diets):
    for diet in diets:
        if diet == "vegan" and not restaurant.vegan:
            return False
        if diet == "vegetarian" and not (restaurant.vegetarian or restaurant.vegan):
            return False
        if diet == "gluten_free" and not restaurant.gluten_free:
            return False
    return True


def suits_table(restaurant, prefs):
    return (suits_diets(restaurant, prefs.diets) and restaurant.price_band in BANDS[prefs.dining_style]
            and (restaurant.kid_friendly or not prefs.children) and (restaurant.step_free or not prefs.step_free)
            and restaurant.covers >= prefs.people)


def strongest_interest(activity, prefs):
    matched = sorted(((prefs.interests[t], t) for t in activity.tag_names if t in prefs.interests), reverse=True)
    if not matched:
        return None
    weight, tag = matched[0]
    return f"You {'love' if weight == 2 else 'like'} {INTERESTS[tag]}."


def place_name(item_or_stay):
    return getattr(item_or_stay, "name", None) or getattr(item_or_stay, "title", "your stay")


# ======================================================================
# Choosing a stay
# ======================================================================

def stay_options(prefs, cat):
    """Every stay that fits the group, best first, with the reason for each."""
    liked = [a for a in cat.activities if interest_points(a, prefs) and suits_group(a, prefs)]
    options = []
    for s in cat.stays:
        if prefs.children and not s.kid_friendly:
            continue
        if prefs.step_free and not s.step_free:
            continue
        if rooms_needed(s, prefs) > min(s.rooms_total, 4):
            continue
        cost = stay_cost(s, prefs)
        share = cost / prefs.budget_cents
        score = 30 if s.style == prefs.stay_style else 10 if tuple(sorted((s.style, prefs.stay_style))) in {
            tuple(sorted(p)) for p in NEAR_STYLES} else 0
        score += 12 if share <= 0.4 else 4 if share <= 0.55 else -10 if share <= 0.7 else -40
        nearby = sum(interest_points(a, prefs) * 10 / (1 + travel(s.area, a.area, prefs.transport) / 20)
                     for a in liked)
        score += nearby / 10
        why = []
        why.append(f"A {STAY_STYLES[s.style]}, as you asked." if s.style == prefs.stay_style
                   else f"A {STAY_STYLES[s.style]}, the closest fit to what you asked for.")
        rooms = rooms_needed(s, prefs)
        unit = "villa" if s.style == "villa" else "room"
        why.append(f"{prefs.nights} nights in {rooms} {unit}{'s' if rooms > 1 else ''} for {fmt(cost)}, "
                   f"{round(share * 100)}% of your budget.")
        if liked:
            close = sum(1 for a in liked if travel(s.area, a.area, prefs.transport) <= 30)
            why.append(f"{close} of the {len(liked)} things you'd enjoy are within 30 minutes.")
        options.append((score, s.id, s, " ".join(why)))
    options.sort(key=lambda o: (-o[0], o[1]))
    return [(s, why) for _, _, s, why in options]


# ======================================================================
# Building the plan
# ======================================================================

class _Day:
    """The timeline of one day while it's being filled."""

    def __init__(self, day, stay_area, fixed):
        self.day = day
        self.t = 0
        self.loc = stay_area
        self.fixed = sorted(fixed, key=lambda f: f.starts)
        self.items = []


def _island_ok(prefs, stay, area, end, block):
    """Another island is a day trip: daytime only, back on your own island before the last ferry."""
    if area is None or area.island == stay.area.island:
        return True
    return block not in ("dinner", "evening") and end + travel(area, stay.area, prefs.transport) <= LAST_FERRY


def _apart(f, start, end, area, transport):
    """True if [start, end] at `area` leaves time to travel to and from fixed item f."""
    return end + travel(area, f.area, transport) <= f.starts or f.ends + travel(f.area, area, transport) <= start


def _fit(prefs, d, area, length, lo, latest_start, latest_end, set_starts=(), opens=0, closes=DAY_ENDS):
    """The earliest (start, end) for something at `area` in this window, or None."""
    start = up15(max(lo, d.t + travel(d.loc, area, prefs.transport), opens))
    for _ in range(10):
        if set_starts:
            later = [s for s in set_starts if s >= start]
            if not later:
                return None
            start = later[0]
        end = start + length
        if start > latest_start or end > min(latest_end, closes):
            return None
        clash = next((f for f in d.fixed if not _apart(f, start, end, area, prefs.transport)), None)
        if clash is None:
            return start, end
        start = up15(max(start + 15, clash.ends + travel(clash.area, area, prefs.transport)))
    return None


def _block_of(item):
    if item.kind == "meal":
        return "lunch" if item.starts < 16 * 60 else "dinner"
    if item.activity is not None and item.activity.includes_dinner:
        return "dinner"
    if item.starts < 12 * 60:
        return "morning"
    if item.starts < 18 * 60:
        return "afternoon"
    return "evening"


class _Planner:
    def __init__(self, prefs, cat, stay, kept):
        self.prefs, self.cat, self.stay = prefs, cat, stay
        self.kept = kept
        self.notes = []
        self.used_activities = {k.activity.id for k in kept if k.activity is not None}
        self.used_restaurants = {k.restaurant.id: 1 for k in kept if k.restaurant is not None}
        self.cuisines = {k.restaurant.cuisine for k in kept if k.restaurant is not None}
        self.had_special = any(k.restaurant is not None and k.restaurant.price_band == 4 for k in kept)
        self.avoid_activities, self.avoid_restaurants = set(), set()
        self.tag_uses = {}
        # Things that match none of the traveller's interests only appear if they're a local favourite
        self.candidates = [a for a in cat.activities if suits_group(a, prefs)
                           and (interest_points(a, prefs) or a.highlight)]
        self.tables = [r for r in cat.restaurants if suits_table(r, prefs)]
        full_days = max(1, prefs.nights - 1)
        meals = MEAL_GUESS[prefs.dining_style] * prefs.people * 2 * prefs.nights
        per_day = {"taxi": TAXI_DAY_GUESS * math.ceil(prefs.people / 4),
                   "hire_car": 6000 * math.ceil(prefs.people / 5), "bus": 800 * prefs.people}
        getting_around = per_day[prefs.transport] * full_days
        kept_costs = sum(k.cost_cents for k in kept if k.kind == "activity" or k.kind == "custom")
        self.fun_budget = prefs.budget_cents - stay_cost(stay, prefs) - meals - getting_around - kept_costs
        if self.fun_budget <= 0:
            self.notes.append("Your budget covers the stay, meals and getting around, but not much more, "
                              "so the plan sticks to free things to do.")
            self.fun_budget = 0
        self.per_day = self.fun_budget / full_days

    # ---- scoring -----------------------------------------------------------------

    def _score_activity(self, a, block, d, start):
        p = self.prefs
        points = interest_points(a, p)
        score = points * 10 if points else 2
        score += 6 if a.highlight else 0
        score += 3 if a.best_time == {"morning": "morning", "afternoon": "afternoon"}.get(block, "evening") else (
            1 if a.best_time == "any" else 0)
        if a.energy == 3:
            hiker = p.interests.get("hiking", 0) == 2
            score -= {"relaxed": 3 if hiker else 15, "balanced": 0 if hiker else 4, "packed": 0}[p.pace]
        for tag in a.tag_names:
            score -= self.tag_uses.get(tag, 0) * (1 if p.interests.get(tag) == 2 else 3)
        score -= travel(d.loc, a.area, p.transport) / 4
        price = group_price(a, p)
        if self.per_day and price > self.per_day * 1.5:
            score -= 8
        if p.children and a.min_age <= (p.youngest_age or 0) and a.energy < 3:
            score += 2 if {"beaches", "nature", "water"} & a.tag_names else 0
        if a.id in self.avoid_activities:
            score -= AVOID_PENALTY
        return score + jitter(a.id, p.variety)

    def _activity_reason(self, a, d, came_from):
        p = self.prefs
        why = [strongest_interest(a, p) or ("Not on your list, but a local favourite worth seeing." if a.highlight
                                            else "Not one of your interests, but it fits this gap.")]
        if a.highlight and strongest_interest(a, p):
            why.append("A local favourite.")
        if a.includes_lunch:
            why.append("Lunch is included.")
        if a.includes_dinner:
            why.append("It's dinner too.")
        if p.children:
            why.append(f"Fine for children aged {a.min_age}+." if a.min_age else "Fine for all ages.")
        price = group_price(a, p)
        why.append("Free." if price == 0 else f"About {fmt(price)} for your group.")
        why.append(self._distance_words(d.loc, a.area, came_from))
        return " ".join(why)

    def _distance_words(self, from_area, to_area, came_from):
        mins = travel(from_area, to_area, self.prefs.transport)
        if from_area is None or to_area is None:
            return ""
        if from_area.island != to_area.island:
            return f"Includes the ferry from {from_area.island} (about {mins} minutes)."
        if from_area.id == to_area.id:
            return f"Close to {came_from}."
        return f"About {mins} minutes from {came_from}."

    # ---- filling the slots ---------------------------------------------------------------

    def _activity(self, d, block, lo, latest_end, came_from, need=lambda a: True):
        p = self.prefs
        best = None
        for a in self.candidates:
            if a.id in self.used_activities or closed_on(a, d.day) or a.includes_dinner or not need(a):
                continue
            if block == "evening" and a.best_time != "evening":
                continue
            if block != "morning" and a.includes_lunch:
                continue
            price = group_price(a, p)
            if price > self.fun_budget:
                continue
            end_limit = 17 * 60 + 30 if (block == "morning" and a.includes_lunch) else latest_end
            latest_start = (EVENING_LATEST if block == "evening" else end_limit - a.minutes)
            set_starts = [minutes(s.starts) for s in a.start_times]
            normal = max(lo, DAY_START[p.day_start]) if block == "morning" else lo
            when = _fit(p, d, a.area, a.minutes, normal, latest_start, end_limit, set_starts,
                        minutes(a.opens), minutes(a.closes))
            if when is None and block == "morning" and any(p.interests.get(t) == 2 for t in a.tag_names):
                # Only if it can't fit otherwise: something you love is worth an early start
                when = _fit(p, d, a.area, a.minutes, max(EARLIEST_EARLY_START, normal - 120), latest_start,
                            end_limit, set_starts, minutes(a.opens), minutes(a.closes))
            if when is None or not _island_ok(p, self.stay, a.area, when[1], block):
                continue
            score = self._score_activity(a, block, d, when[0])
            if best is None or (score, -a.id) > (best[0], -best[1].id):
                best = (score, a, when)
        if best is None:
            return None
        _, a, (start, end) = best
        reason = self._activity_reason(a, d, came_from)
        if block == "morning" and start < DAY_START[p.day_start]:
            reason = f"An early start ({clock(start)}), but worth it. " + reason
        item = Planned(d.day, start, end, "activity", a.name, a.area, group_price(a, p), reason, activity=a)
        self._take(d, item)
        self.used_activities.add(a.id)
        self.fun_budget -= item.cost_cents
        for tag in a.tag_names:
            self.tag_uses[tag] = self.tag_uses.get(tag, 0) + 1
        return item

    def _meal(self, d, which, came_from, lo, latest_start):
        p = self.prefs
        best = None
        for r in self.tables:
            if closed_on(r, d.day) or not (r.lunch if which == "lunch" else r.dinner):
                continue
            length = LUNCH_MINUTES if which == "lunch" else DINNER_MINUTES
            serves_until = 15 * 60 + 30 if which == "lunch" else 22 * 60 + 30
            if any(i.restaurant is not None and i.restaurant.id == r.id for i in d.items + d.fixed):
                continue                            # not lunch and dinner at the same place
            when = _fit(p, d, r.area, length, lo, latest_start, serves_until)
            if when is None or not _island_ok(p, self.stay, r.area, when[1], which):
                continue
            here = travel(d.loc, r.area, p.transport)
            home = travel(r.area, self.stay.area, p.transport) if which == "dinner" else 0
            score = -(here + home) / 2              # lunch near where you are; dinner on the way home
            score += 6 if r.id not in self.used_restaurants else -8 * self.used_restaurants[r.id]
            score -= AVOID_PENALTY if r.id in self.avoid_restaurants else 0
            score += 3 if r.cuisine not in self.cuisines else 0
            score -= abs(r.price_band - IDEAL_BAND[p.dining_style]) * 2
            if p.dining_style == "treat" and which == "dinner" and r.price_band == 4 and not self.had_special:
                score += 6                          # one special dinner on a "treat ourselves" trip
            score += jitter(r.id, p.variety) / 2
            if best is None or (score, -r.id) > (best[0], -best[1].id):
                best = (score, r, when)
        if best is None:
            return self._no_meal(d, which, came_from, lo, latest_start)
        _, r, (start, end) = best
        why = []
        if p.diets:
            needs = " and ".join(DIET_WORDS[x] for x in sorted(p.diets))
            why.append(f"Has {needs} options.")
        why.append(f"{r.cuisine}, about {fmt(r.avg_cents)} a head.")
        if r.id in self.used_restaurants:
            why.append("Worth a second visit: it's the best fit nearby.")
        why.append(self._distance_words(d.loc, r.area, came_from))
        item = Planned(d.day, start, end, "meal", f"{which.title()} at {r.name}", r.area, meal_price(r, p),
                       " ".join(why), restaurant=r)
        self._take(d, item)
        self.used_restaurants[r.id] = self.used_restaurants.get(r.id, 0) + 1
        self.cuisines.add(r.cuisine)
        self.had_special = self.had_special or r.price_band == 4
        return item

    def _no_meal(self, d, which, came_from, lo, latest_start):
        # Lunch: a picnic wherever you are. Dinner: back at (or near) your stay.
        area = d.loc if which == "lunch" else self.stay.area
        start = up15(max(lo, d.t + travel(d.loc, area, self.prefs.transport)))
        if start > latest_start:
            return None
        length = LUNCH_MINUTES if which == "lunch" else DINNER_MINUTES
        if self.stay.style == "villa" and which == "dinner":
            title, why = "Dinner at your villa", "Nothing nearby fits tonight, and the villa has a kitchen."
        elif which == "dinner":
            title = "Dinner near your stay"
            why = f"No restaurant on the list fits your needs on {d.day:%A}s; ask at {self.stay.name}."
        else:
            title = "Picnic lunch"
            why = f"No restaurant nearby fits your needs for lunch on {d.day:%A}s, so bring something along."
        self.notes.append(f"{d.day:%a %d %b}: no restaurant fits {which}, so we've suggested {title.lower()}.")
        item = Planned(d.day, start, start + length, "meal", title, area,
                       MEAL_GUESS["local"] * self.prefs.people, why)
        self._take(d, item)
        return item

    def _take(self, d, item):
        d.items.append(item)
        d.t, d.loc = item.ends, item.area

    # ---- the days ---------------------------------------------------------------------

    def run(self, days_to_plan):
        p = self.prefs
        out = []
        for n in range(p.nights + 1):
            day = p.start + timedelta(days=n)
            if day not in days_to_plan:
                continue
            fixed = [k for k in self.kept if k.day == day]
            d = _Day(day, self.stay.area, fixed)
            if n == 0:
                self._arrival(d)
            elif day == p.end:
                self._departure(d)
            else:
                self._full_day(d)
            out.extend(d.items)
        return out

    def _stay_item(self, d, which):
        s = self.stay
        if which == "in":
            return Planned(d.day, *CHECK_IN, "stay", f"Check in at {s.name}", s.area, 0,
                           "Rooms are usually ready from 3pm.")
        return Planned(d.day, *CHECK_OUT, "stay", f"Check out of {s.name}", s.area, 0,
                       "Leaves the rest of the day for getting to your flight.")

    def _covered(self, d, block):
        """Kept items that already fill this part of the day; moves the clock past them."""
        hits = [f for f in d.fixed if _block_of(f) == block]
        for f in hits:
            if f.ends > d.t:
                d.t, d.loc = f.ends, f.area
        return bool(hits)

    def _arrival(self, d):
        self._take(d, self._stay_item(d, "in"))
        name = self.stay.name
        if self.prefs.pace != "relaxed" and not self._covered(d, "afternoon"):
            self._activity(d, "afternoon", ARRIVAL_FREE_FROM, AFTERNOON_ENDS, name,
                           need=lambda a: a.energy == 1 and travel(self.stay.area, a.area, self.prefs.transport) <= 30)
        self._dinner(d)

    def _departure(self, d):
        self._take(d, self._stay_item(d, "out"))

    def _full_day(self, d):
        p = self.prefs
        d.t = EARLIEST_EARLY_START                 # the clock starts early; only loved things may use it
        start_name = self.stay.name
        morning = None
        if not self._covered(d, "morning"):
            morning = self._activity(d, "morning", DAY_START[p.day_start], MORNING_ENDS, start_name)
        lunch_included = (morning and morning.activity.includes_lunch) or any(
            f.activity is not None and f.activity.includes_lunch for f in d.fixed)
        if not lunch_included and not self._covered(d, "lunch"):
            self._meal(d, "lunch", self._last_name(d), LUNCH_FROM, LUNCH_LATEST)
        long_day = d.t > 15 * 60 + 30
        want_afternoon = p.pace != "relaxed" or morning is None
        if want_afternoon and not long_day and not self._covered(d, "afternoon"):
            self._activity(d, "afternoon", d.t, AFTERNOON_ENDS, self._last_name(d))
            if p.pace == "packed" and d.t <= 16 * 60 + 30:            # packed days fit one more if there's time
                self._activity(d, "afternoon", d.t, AFTERNOON_ENDS, self._last_name(d))
        self._dinner(d)
        evening_wanted = p.pace == "packed" or (p.pace == "balanced" and p.interests.get("nightlife"))
        if evening_wanted and not self._covered(d, "evening") and not self._event_tonight(d):
            self._activity(d, "evening", d.t, DAY_ENDS, self._last_name(d))

    def _event_tonight(self, d):
        return any(i.activity is not None and i.activity.includes_dinner for i in d.items + d.fixed)

    def _dinner(self, d):
        if self._covered(d, "dinner"):
            return
        p = self.prefs
        # A Friday fish fry or street party is dinner and the evening in one, if it suits the traveller
        events = [a for a in self.candidates if a.includes_dinner and a.id not in self.used_activities
                  and not closed_on(a, d.day)]
        for a in sorted(events, key=lambda a: (-interest_points(a, p), a.id)):
            if interest_points(a, p) * 10 + (6 if a.highlight else 0) < 10:
                continue
            when = _fit(p, d, a.area, a.minutes, 18 * 60, 20 * 60 + 30, DAY_ENDS, (), minutes(a.opens),
                        minutes(a.closes))
            if when and _island_ok(p, self.stay, a.area, when[1], "dinner"):
                item = Planned(d.day, when[0], when[1], "activity", a.name, a.area, group_price(a, p),
                               self._activity_reason(a, d, self._last_name(d)), activity=a)
                self._take(d, item)
                self.used_activities.add(a.id)
                return
        self._meal(d, "dinner", self._last_name(d), DINNER_FROM[p.day_start], DINNER_LATEST)

    def _last_name(self, d):
        if d.items and d.items[-1].kind != "stay":
            last = d.items[-1]
            return last.activity.name if last.activity else (last.restaurant.name if last.restaurant else last.title)
        return self.stay.name


def plan_trip(prefs, cat, stay=None, kept=(), days=None, avoid=()):
    """Build a plan. `stay`: keep this stay (else the best is chosen). `kept`: items to plan around.
    `days`: only (re)plan these days (default: all). `avoid`: activity and restaurant ids to leave out
    if possible (used when redoing a day, so it comes back different)."""
    if prefs.nights < 1:
        raise PlanError("A trip needs at least one night")
    options = stay_options(prefs, cat)
    if stay is None:
        if not options:
            raise PlanError("Nowhere to stay fits your group. Try fewer people or another style of stay.")
        stay, stay_reason = options[0]
    else:
        stay_reason = next((why for s, why in options if s.id == stay.id), "")
    all_days = {prefs.start + timedelta(days=n) for n in range(prefs.nights + 1)}
    planner = _Planner(prefs, cat, stay, list(kept))
    # "Something different" is a strong preference, not a ban: last time's picks only come back
    # if nothing else fits, so a day is never left empty just to be different
    planner.avoid_activities = {thing_id for kind, thing_id in avoid if kind == "activity"}
    planner.avoid_restaurants = {thing_id for kind, thing_id in avoid if kind == "restaurant"}
    items = planner.run(set(days) if days is not None else all_days)
    return Plan(stay=stay, stay_reason=stay_reason, items=items, notes=planner.notes)


# ======================================================================
# Alternatives for one item ("swap this")
# ======================================================================

def alternatives(prefs, cat, stay, items, target, limit=5):
    """Other activities (or restaurants) that would fit in `target`'s place, best first."""
    others = [i for i in items if i is not target and i.day == target.day]
    used_a = {i.activity.id for i in items if i.activity is not None}
    used_r = {i.restaurant.id for i in items if i.restaurant is not None}
    before = [i for i in others if i.ends <= target.starts]
    after = [i for i in others if i.starts >= target.ends]
    prev = max(before, key=lambda i: i.ends, default=None)
    nxt = min(after, key=lambda i: i.starts, default=None)
    d = _Day(target.day, stay.area, [])
    d.t = prev.ends if prev else DAY_START[prefs.day_start]
    d.loc = prev.area if prev else stay.area
    latest_end = target.ends + 60 if nxt is None else nxt.starts
    planner = _Planner(prefs, cat, stay, [i for i in items if i is not target])
    came_from = place_name(prev.activity or prev.restaurant or prev) if prev else stay.name
    results = []
    if target.kind == "meal":
        which = "lunch" if target.starts < 16 * 60 else "dinner"
        for r in planner.tables:
            if r.id in used_r or closed_on(r, target.day) or not (r.lunch if which == "lunch" else r.dinner):
                continue
            length = target.ends - target.starts
            when = _fit(prefs, d, r.area, length, target.starts - 60, target.starts + 60,
                        latest_end - (travel(r.area, nxt.area, prefs.transport) if nxt else 0))
            if when is None:
                continue
            score = -travel(d.loc, r.area, prefs.transport) / 4 - abs(r.price_band - IDEAL_BAND[prefs.dining_style])
            why = f"{r.cuisine}, about {fmt(r.avg_cents)} a head. " + planner._distance_words(d.loc, r.area, came_from)
            results.append((score, r.id, Planned(target.day, *when, "meal", f"{which.title()} at {r.name}", r.area,
                                                 meal_price(r, prefs), why, restaurant=r)))
    else:
        # Wider than the planner's own picks: when swapping, anything that suits the group is worth showing
        for a in (a for a in cat.activities if suits_group(a, prefs)):
            if a.id in used_a or closed_on(a, target.day) or a.includes_dinner:
                continue
            end_limit = latest_end - (travel(a.area, nxt.area, prefs.transport) if nxt else 0)
            when = _fit(prefs, d, a.area, a.minutes, d.t, end_limit - a.minutes, end_limit,
                        [minutes(s.starts) for s in a.start_times], minutes(a.opens), minutes(a.closes))
            if when is None:
                continue
            block = _block_of(Planned(target.day, when[0], when[1], "activity", a.name, activity=a))
            score = planner._score_activity(a, block, d, when[0])
            results.append((score, a.id, Planned(target.day, *when, "activity", a.name, a.area, group_price(a, prefs),
                                                 planner._activity_reason(a, d, came_from), activity=a)))
    results.sort(key=lambda r: (-r[0], r[1]))
    return [p for _, _, p in results[:limit]]


# ======================================================================
# Checking a plan after edits, and adding it up
# ======================================================================

def check(prefs, stay, items):
    """Everything that doesn't work in the plan as it stands. The traveller is in charge, so these are
    warnings to show, not reasons to refuse an edit."""
    issues = []
    by_day = {}
    for i in items:
        by_day.setdefault(i.day, []).append(i)
    seen = {}
    for day in sorted(by_day):
        row = sorted(by_day[day], key=lambda i: (i.starts, i.ends))
        for a, b in zip(row, row[1:], strict=False):
            need = travel(a.area, b.area, prefs.transport) if a.area and b.area else 0
            if a.ends > b.starts:
                issues.append(Issue(day, b.id, f"{b.title} overlaps {a.title}."))
            elif a.ends + need > b.starts:
                issues.append(Issue(day, b.id, f"Not enough time to get from {a.title} to {b.title} "
                                               f"(about {need} minutes)."))
        for i in row:
            a, r = i.activity, i.restaurant
            if a is not None:
                if closed_on(a, day):
                    issues.append(Issue(day, i.id, f"{a.name} is closed on {day:%A}s."))
                if i.starts < minutes(a.opens) or i.ends > minutes(a.closes):
                    issues.append(Issue(day, i.id, f"{a.name} is open {a.opens:%H:%M} to {a.closes:%H:%M}."))
                if a.start_times and i.starts not in [minutes(s.starts) for s in a.start_times]:
                    issues.append(Issue(day, i.id, f"{a.name} starts at "
                                                   f"{', '.join(f'{s.starts:%H:%M}' for s in a.start_times)}."))
                if prefs.children and (a.min_age >= 18 or a.min_age > (prefs.youngest_age or 0)):
                    issues.append(Issue(day, i.id, f"{a.name} is for ages {a.min_age}+."))
                if prefs.step_free and not a.step_free:
                    issues.append(Issue(day, i.id, f"{a.name} isn't step-free."))
                if a.id in seen:
                    issues.append(Issue(day, i.id, f"{a.name} is already on {seen[a.id]:%a %d %b}."))
                seen[a.id] = day
            if r is not None:
                if closed_on(r, day):
                    issues.append(Issue(day, i.id, f"{r.name} is closed on {day:%A}s."))
                which = "lunch" if i.starts < 16 * 60 else "dinner"
                if not (r.lunch if which == "lunch" else r.dinner):
                    issues.append(Issue(day, i.id, f"{r.name} doesn't serve {which}."))
                if not suits_diets(r, prefs.diets):
                    issues.append(Issue(day, i.id, f"{r.name} may not suit your food needs."))
    total = summarise(prefs, stay, items)["total_cents"]
    if total > prefs.budget_cents:
        issues.append(Issue(None, None, f"The plan comes to about {fmt(total)}, "
                                        f"{fmt(total - prefs.budget_cents)} over your budget."))
    return issues


def transport_cost(prefs, stay, items):
    """An estimate for getting around: taxis per trip, hire cars per day, or bus fares, plus ferries."""
    cost = 0
    by_day = {}
    for i in items:
        by_day.setdefault(i.day, []).append(i)
    for day, row in by_day.items():
        stops = [stay.area] + [i.area for i in sorted(row, key=lambda i: i.starts) if i.area] + [stay.area]
        hops = [(a, b) for a, b in zip(stops, stops[1:], strict=False) if a.id != b.id]
        if not hops:
            continue
        if prefs.transport == "hire_car" and day not in (prefs.end,):
            cost += 6000 * math.ceil(prefs.people / 5)
        for a, b in hops:
            mins = travel(a, b, prefs.transport)
            if prefs.transport == "taxi":
                cost += (1500 + 120 * min(mins, 60)) * math.ceil(prefs.people / 4)
            elif prefs.transport == "bus":
                cost += 200 * prefs.people
            if a.island != b.island:
                cost += FERRY_CENTS * prefs.people
    return cost


def summarise(prefs, stay, items):
    stay_cents = stay_cost(stay, prefs) if stay else 0
    activities = sum(i.cost_cents for i in items if i.kind in ("activity", "custom"))
    meals = sum(i.cost_cents for i in items if i.kind == "meal")
    moving = transport_cost(prefs, stay, items) if stay else 0
    total = stay_cents + activities + meals + moving
    return {"stay_cents": stay_cents, "activities_cents": activities, "meals_cents": meals,
            "transport_cents": moving, "total_cents": total, "budget_cents": prefs.budget_cents,
            "left_cents": prefs.budget_cents - total}
