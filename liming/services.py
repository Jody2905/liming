"""Liming's operations: accounts, a trip's answers, generating the plan, and editing it.

Every function takes a database session `db` and, where time matters, `now`, so tests can
say exactly what time it is. Changes commit their own transaction: all or nothing.

Editing rules
  * Anything the traveller moves, adds or swaps is locked, so "regenerate" never undoes it.
  * Locked items and everything the traveller added are kept when the plan is rebuilt; the
    planner fills the gaps around them.
  * Edits are never refused for being a bad idea (a museum on its closed day, too little
    time to get somewhere). They are allowed, and `plan_for` lists them as warnings.
"""

import hashlib
import secrets
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import delete, func, or_, select

from . import passwords, planner
from .models import (
    DAY_STARTS,
    DIETS,
    DINING_STYLES,
    INTERESTS,
    PACES,
    STAY_STYLES,
    TRANSPORT,
    Activity,
    Area,
    Booking,
    Destination,
    LoginSession,
    PlanItem,
    Restaurant,
    Stay,
    Trip,
    TripDiet,
    TripInterest,
    User,
)
from .money import fmt
from .planner import Catalogue, Planned, Prefs, minutes, to_time

MAX_NIGHTS = 14
MIN_BUDGET_PER_PERSON_NIGHT = 5000          # US$50: below that, nothing in the catalogue fits


@contextmanager
def _tx(db):
    try:
        yield
        db.commit()
    except BaseException:
        db.rollback()
        raise


class LimingError(Exception):
    """A rule said no. The message is safe to show the traveller."""


class NotFound(LimingError):
    pass


# ======================================================================
# Accounts
# ======================================================================

def create_user(db, email, name, password, now=None):
    email = (email or "").strip().lower()
    if "@" not in email or len(email) > 254:
        raise LimingError("Please enter a valid email address")
    if not (name or "").strip():
        raise LimingError("Please enter your name")
    try:
        hashed = passwords.hash_password(password)
    except ValueError as e:
        raise LimingError(str(e)) from None
    with _tx(db):
        if db.scalar(select(User).where(User.email == email)):
            raise LimingError("There's already an account with this email")
        user = User(email=email, name=name.strip()[:80], password_hash=hashed, created_at=now or datetime.now())
        db.add(user)
    return user


def authenticate(db, email, password):
    user = db.scalar(select(User).where(User.email == (email or "").strip().lower()))
    db.rollback()
    stored = user.password_hash if user else passwords.hash_password("timing-equaliser")
    return user if passwords.verify_password(password or "", stored) and user else None


# ======================================================================
# Login sessions
# ======================================================================
# The browser keeps a random token in a cookie; the database stores only its SHA-256, so a
# leaked database can't be used to log in. Each session has its own CSRF token, which the
# page sends back as a header on every change (another website can't read it).

SESSION_DAYS = 7


def start_session(db, user, now=None):
    """Returns (cookie token, session). The token is shown once and never stored."""
    now = now or datetime.now()
    token = secrets.token_urlsafe(32)
    with _tx(db):
        session = LoginSession(token_hash=_hash_token(token), user_id=user.id, csrf_token=secrets.token_urlsafe(32),
                               created_at=now, expires_at=now + timedelta(days=SESSION_DAYS))
        db.add(session)
    return token, session


def session_for(db, token, now=None):
    """(user, session) for a cookie token, or None if it's unknown or has run out."""
    if not token:
        return None
    now = now or datetime.now()
    row = db.execute(select(LoginSession, User).join(User, User.id == LoginSession.user_id)
                     .where(LoginSession.token_hash == _hash_token(token))).first()
    if row is None or row[0].expires_at <= now:
        db.rollback()
        return None
    session, user = row
    db.expunge(session)
    db.expunge(user)                                # keep their loaded values after the read ends
    db.rollback()
    return user, session


def end_session(db, token):
    if token:
        with _tx(db):
            db.execute(delete(LoginSession).where(LoginSession.token_hash == _hash_token(token)))


def end_expired_sessions(db, now=None):
    with _tx(db):
        return db.execute(delete(LoginSession).where(LoginSession.expires_at <= (now or datetime.now()))).rowcount


def _hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


# ======================================================================
# The answers
# ======================================================================

BOOKED_ANSWERS = {"destination_id", "start_date", "end_date", "adults", "children"}
ANSWER_FIELDS = ("title", "destination_id", "start_date", "end_date", "adults", "children", "youngest_age",
                 "budget_cents", "pace", "stay_style", "dining_style", "transport", "day_start", "step_free",
                 "interests", "diets")


def destinations(db):
    return db.scalars(select(Destination).order_by(Destination.name)).all()


def create_trip(db, user, now=None, **answers):
    """Save a traveller's answers as a new trip, then build its first plan."""
    now = now or datetime.now()
    a = _check_answers(db, answers, now)
    with _tx(db):
        trip = Trip(owner_id=user.id, created_at=now, **{k: v for k, v in a.items() if k not in ("interests", "diets")})
        trip.interests = [TripInterest(tag=t, weight=w) for t, w in sorted(a["interests"].items())]
        trip.diets = [TripDiet(diet=d) for d in sorted(a["diets"])]
        db.add(trip)
    return generate(db, user, trip.id, now=now)


def update_answers(db, user, trip_id, now=None, **changes):
    """Change some answers. Items now outside the trip's dates are removed; call `generate` to replan."""
    now = now or datetime.now()
    unknown = set(changes) - set(ANSWER_FIELDS)
    if unknown:
        raise LimingError(f"Unknown answer: {', '.join(sorted(unknown))}")
    trip = _own_trip(db, user, trip_id)
    if changes.keys() & BOOKED_ANSWERS and _live(db, trip.id, now):
        raise LimingError("You have bookings for these dates and people. Cancel them before changing "
                          "the country, dates or group size.")
    current = {k: getattr(trip, k) for k in ANSWER_FIELDS if k not in ("interests", "diets")}
    current["interests"] = {i.tag: i.weight for i in trip.interests}
    current["diets"] = {d.diet for d in trip.diets}
    a = _check_answers(db, {**current, **changes}, now, allow_past=(changes.keys() & {"start_date"}) == set())
    with _tx(db):
        trip = _own_trip(db, user, trip_id, lock=True)
        for k, v in a.items():
            if k not in ("interests", "diets"):
                setattr(trip, k, v)
        if "interests" in changes:
            trip.interests = [TripInterest(tag=t, weight=w) for t, w in sorted(a["interests"].items())]
        if "diets" in changes:
            trip.diets = [TripDiet(diet=d) for d in sorted(a["diets"])]
        # ORM deletes, so the session forgets the removed rows too (SQLite reuses their ids)
        if changes.keys() & {"destination_id"}:
            trip.stay_id, trip.stay_locked = None, False
            db.execute(delete(PlanItem).where(PlanItem.trip_id == trip.id), execution_options={
                "synchronize_session": "fetch"})
        else:
            db.execute(delete(PlanItem).where(
                PlanItem.trip_id == trip.id, (PlanItem.day < trip.start_date) | (PlanItem.day > trip.end_date)),
                execution_options={"synchronize_session": "fetch"})
    return trip


def _check_answers(db, a, now, allow_past=False):
    title = (a.get("title") or "").strip()
    if not title:
        raise LimingError("Please give the trip a name")
    if len(title) > 100:
        raise LimingError("Please keep the trip name under 100 characters")
    if db.get(Destination, a.get("destination_id") or 0) is None:
        raise LimingError("Please choose where you're going")
    start, end = a.get("start_date"), a.get("end_date")
    if not isinstance(start, date) or not isinstance(end, date):
        raise LimingError("Please choose your dates")
    if start < now.date() and not allow_past:
        raise LimingError("The trip can't start in the past")
    if end <= start:
        raise LimingError("You leave after you arrive: the last day must be after the first")
    if (end - start).days > MAX_NIGHTS:
        raise LimingError(f"Plans can be up to {MAX_NIGHTS} nights")
    adults, children = a.get("adults"), a.get("children", 0) or 0
    if not isinstance(adults, int) or not 1 <= adults <= 8:
        raise LimingError("Adults must be between 1 and 8")
    if not isinstance(children, int) or not 0 <= children <= 6:
        raise LimingError("Children must be between 0 and 6")
    youngest = a.get("youngest_age")
    if children and (not isinstance(youngest, int) or not 0 <= youngest <= 17):
        raise LimingError("Please tell us the youngest child's age (0 to 17)")
    if not children:
        youngest = None
    budget = a.get("budget_cents")
    people, nights = adults + children, (end - start).days
    if not isinstance(budget, int) or budget <= 0:
        raise LimingError("Please set a budget")
    if budget < MIN_BUDGET_PER_PERSON_NIGHT * people * nights:
        raise LimingError(f"For {people} {'person' if people == 1 else 'people'} and {nights} "
                          f"night{'s' if nights != 1 else ''}, the budget needs to be at least "
                          f"{fmt(MIN_BUDGET_PER_PERSON_NIGHT * people * nights)}")
    for key, allowed, label in (("pace", PACES, "pace"), ("stay_style", STAY_STYLES, "kind of stay"),
                                ("dining_style", DINING_STYLES, "way of eating out"),
                                ("transport", TRANSPORT, "way of getting around"),
                                ("day_start", DAY_STARTS, "start to the day")):
        if a.get(key, "normal" if key == "day_start" else None) not in allowed:
            raise LimingError(f"Please choose a {label}")
    interests = a.get("interests") or {}
    if not isinstance(interests, dict) or not interests:
        raise LimingError("Pick at least one thing you'd like to do")
    for tag, weight in interests.items():
        if tag not in INTERESTS or weight not in (1, 2):
            raise LimingError("Interests are rated 1 (like) or 2 (love)")
    diets = set(a.get("diets") or ())
    if diets - set(DIETS):
        raise LimingError("Unknown food need")
    return {"title": title, "destination_id": a["destination_id"], "start_date": start, "end_date": end,
            "adults": adults, "children": children, "youngest_age": youngest, "budget_cents": budget,
            "pace": a["pace"], "stay_style": a["stay_style"], "dining_style": a["dining_style"],
            "transport": a["transport"], "day_start": a.get("day_start", "normal"),
            "step_free": bool(a.get("step_free", False)), "interests": dict(interests), "diets": diets}


def trips_for(db, user):
    return db.scalars(select(Trip).where(Trip.owner_id == user.id).order_by(Trip.start_date, Trip.id)).all()


def delete_trip(db, user, trip_id, now=None):
    now = now or datetime.now()
    with _tx(db):
        trip = _own_trip(db, user, trip_id, lock=True)
        if _live(db, trip.id, now):
            raise LimingError("Cancel this trip's bookings before deleting it")
        db.execute(delete(Booking).where(Booking.trip_id == trip.id), execution_options={
            "synchronize_session": "fetch"})                 # old cancelled or lapsed ones
        db.delete(trip)


# ======================================================================
# Generating
# ======================================================================

def load_catalogue(db, destination_id):
    area_ids = select(Area.id).where(Area.destination_id == destination_id)
    q = lambda model: db.scalars(select(model).where(model.area_id.in_(area_ids)).order_by(model.id)).all()  # noqa: E731
    return Catalogue(areas=db.scalars(select(Area).where(Area.destination_id == destination_id)).all(),
                     stays=q(Stay), activities=q(Activity), restaurants=q(Restaurant))


def generate(db, user, trip_id, now=None, fresh=False):
    """(Re)build the whole plan. Locked items and anything the traveller added stay put.
    `fresh=True` asks for something different: the next-best options get a turn."""
    now = now or datetime.now()
    with _tx(db):
        trip = _own_trip(db, user, trip_id, lock=True)
        if fresh:
            trip.variety += 1
        items = _items(db, trip.id)
        kept = [_to_planned(i) for i in items if _keep(i)]
        avoid = []
        if fresh:                                   # "something different": leave out what's there now, if possible
            avoid = [("activity", i.activity_id) for i in items if i.activity_id and not _keep(i)] + [
                ("restaurant", i.restaurant_id) for i in items if i.restaurant_id and not _keep(i)]
        cat = load_catalogue(db, trip.destination_id)
        try:
            plan = planner.plan_trip(Prefs.from_trip(trip), cat, stay=trip.stay if trip.stay_locked else None,
                                     kept=kept, avoid=avoid)
        except planner.PlanError as e:
            raise LimingError(str(e)) from None
        _replace_unkept(db, trip, items, plan.items, days=None)
        trip.stay_id, trip.planned_at = plan.stay.id, now
    db.refresh(trip)
    return trip


def regenerate_day(db, user, trip_id, day, now=None):
    """Rebuild one day, keeping its locked items and everything on the other days."""
    now = now or datetime.now()
    with _tx(db):
        trip = _own_trip(db, user, trip_id, lock=True)
        _check_day(trip, day)
        if trip.stay is None:
            raise LimingError("Build the plan first")
        items = _items(db, trip.id)
        kept = [_to_planned(i) for i in items if i.day != day or _keep(i)]
        before = [i for i in items if i.day == day and not _keep(i)]
        avoid = [("activity", i.activity_id) for i in before if i.activity_id] + [
            ("restaurant", i.restaurant_id) for i in before if i.restaurant_id]
        cat = load_catalogue(db, trip.destination_id)
        plan = planner.plan_trip(Prefs.from_trip(trip), cat, stay=trip.stay, kept=kept, days={day}, avoid=avoid)
        _replace_unkept(db, trip, [i for i in items if i.day == day], plan.items, days={day})
        trip.planned_at = now
    db.refresh(trip)
    return trip


def _keep(item):
    return item.kind != "stay" and (item.locked or item.added_by == "you")


def _replace_unkept(db, trip, old_items, new_items, days):
    for i in old_items:
        if not _keep(i) and (days is None or i.day in days):
            db.delete(i)
    db.flush()
    for p in new_items:
        db.add(PlanItem(trip_id=trip.id, day=p.day, starts=to_time(p.starts), ends=to_time(p.ends), kind=p.kind,
                        activity_id=p.activity.id if p.activity else None,
                        restaurant_id=p.restaurant.id if p.restaurant else None,
                        area_id=p.area.id if p.area else None, title=p.title[:140], cost_cents=p.cost_cents,
                        reason=p.reason, locked=False, added_by="planner"))


# ======================================================================
# Reading the plan
# ======================================================================

@dataclass
class PlanView:
    trip: Trip
    days: dict                     # date -> [PlanItem] in time order
    issues: list                   # planner.Issue
    totals: dict                   # stay / activities / meals / transport / total / budget / left (cents)
    stay_reason: str


def plan_for(db, user, trip_id):
    trip = _own_trip(db, user, trip_id)
    items = _items(db, trip.id)
    prefs = Prefs.from_trip(trip)
    planned = [_to_planned(i) for i in items]
    days = {trip.start_date + timedelta(days=n): [] for n in range(trip.nights + 1)}
    for i in items:
        days.setdefault(i.day, []).append(i)
    stay_reason = ""
    if trip.stay is not None:
        cat = load_catalogue(db, trip.destination_id)
        stay_reason = next((why for s, why in planner.stay_options(prefs, cat) if s.id == trip.stay_id),
                           "You chose this stay.")
    return PlanView(trip=trip, days=days,
                    issues=planner.check(prefs, trip.stay, planned) if trip.stay else [],
                    totals=planner.summarise(prefs, trip.stay, planned), stay_reason=stay_reason)


def get_trip(db, user, trip_id):
    return _own_trip(db, user, trip_id)


# ======================================================================
# Editing
# ======================================================================

def alternatives(db, user, item_id, limit=5):
    """Things that could go in this item's place, best first (nothing is changed)."""
    item, trip = _own_item(db, user, item_id)
    if item.kind not in ("activity", "meal"):
        raise LimingError("Only activities and meals can be swapped")
    items = _items(db, trip.id)
    planned = {i.id: _to_planned(i) for i in items}
    return planner.alternatives(Prefs.from_trip(trip), load_catalogue(db, trip.destination_id), trip.stay,
                                list(planned.values()), planned[item.id], limit=limit)


def swap(db, user, item_id, activity_id=None, restaurant_id=None, now=None):
    """Swap an item for one of its alternatives (or any activity/restaurant in the same country)."""
    now = now or datetime.now()
    if (activity_id is None) == (restaurant_id is None):
        raise LimingError("Choose one activity or one restaurant to swap in")
    options = alternatives(db, user, item_id, limit=100)
    with _tx(db):
        item, trip = _own_item(db, user, item_id, lock_trip=True)
        _not_booked(db, item, now)
        if (activity_id is not None) != (item.kind == "activity"):
            raise LimingError("Swap an activity for an activity, and a meal for a meal")
        choice = next((o for o in options if (o.activity and o.activity.id == activity_id)
                       or (o.restaurant and o.restaurant.id == restaurant_id)), None)
        if choice is None:                          # not a neat fit: put it in the same slot and let check() warn
            thing = db.get(Activity if activity_id else Restaurant, activity_id or restaurant_id)
            if thing is None or thing.area.destination_id != trip.destination_id:
                raise NotFound("That isn't in this country")
            prefs = Prefs.from_trip(trip)
            if activity_id:
                length, cost, title = thing.minutes, planner.group_price(thing, prefs), thing.name
            else:
                length = minutes(item.ends) - minutes(item.starts)
                cost = planner.meal_price(thing, prefs)
                title = f"{'Lunch' if minutes(item.starts) < 16 * 60 else 'Dinner'} at {thing.name}"
            start = minutes(item.starts)
            choice = Planned(item.day, start, min(start + length, planner.DAY_ENDS), item.kind, title, thing.area, cost,
                             "You chose this.", activity=thing if activity_id else None,
                             restaurant=thing if restaurant_id else None)
        item.activity_id = choice.activity.id if choice.activity else None
        item.restaurant_id = choice.restaurant.id if choice.restaurant else None
        item.area_id = choice.area.id if choice.area else None
        item.title, item.cost_cents, item.reason = choice.title[:140], choice.cost_cents, choice.reason
        item.starts, item.ends = to_time(choice.starts), to_time(choice.ends)
        item.locked = True
    return _refreshed(db, item)


def move_item(db, user, item_id, day, starts, now=None):
    """Move an item to another day and/or time, keeping its length. Moved items are locked."""
    starts, now = _clock(starts), now or datetime.now()
    with _tx(db):
        item, trip = _own_item(db, user, item_id, lock_trip=True)
        if item.kind == "stay":
            raise LimingError("Check-in and check-out follow your stay. Change the stay instead.")
        _not_booked(db, item, now)
        _check_day(trip, day)
        length = minutes(item.ends) - minutes(item.starts)
        if minutes(starts) + length > planner.DAY_ENDS:
            raise LimingError("That would run past midnight")
        item.day, item.starts, item.ends = day, starts, to_time(minutes(starts) + length)
        item.locked = True
    return _refreshed(db, item)


def retime_item(db, user, item_id, starts, ends, now=None):
    starts, ends, now = _clock(starts), _clock(ends), now or datetime.now()
    if ends <= starts:
        raise LimingError("It has to end after it starts")
    with _tx(db):
        item, trip = _own_item(db, user, item_id, lock_trip=True)
        if item.kind == "stay":
            raise LimingError("Check-in and check-out follow your stay. Change the stay instead.")
        _not_booked(db, item, now)
        item.starts, item.ends, item.locked = starts, ends, True
    return _refreshed(db, item)


def set_locked(db, user, item_id, locked, now=None):
    now = now or datetime.now()
    with _tx(db):
        item, _ = _own_item(db, user, item_id, lock_trip=True)
        if item.kind == "stay":
            raise LimingError("Check-in and check-out always stay in the plan")
        if not locked:
            _not_booked(db, item, now)
        item.locked = bool(locked)
    return _refreshed(db, item)


def set_notes(db, user, item_id, notes):
    with _tx(db):
        item, _ = _own_item(db, user, item_id, lock_trip=True)
        item.notes = (notes or "").strip()[:2000]
    return _refreshed(db, item)


def remove_item(db, user, item_id, now=None):
    now = now or datetime.now()
    with _tx(db):
        item, trip = _own_item(db, user, item_id, lock_trip=True)
        if item.kind == "stay":
            raise LimingError("Check-in and check-out follow your stay. Change the stay instead.")
        _not_booked(db, item, now)
        db.delete(item)
    return trip.id


def add_item(db, user, trip_id, day, starts, ends=None, title=None, activity_id=None, restaurant_id=None,
             cost_cents=0, notes=""):
    """Add your own thing (title + times), a catalogue activity, or a meal at a restaurant."""
    starts = _clock(starts)
    with _tx(db):
        trip = _own_trip(db, user, trip_id, lock=True)
        _check_day(trip, day)
        prefs = Prefs.from_trip(trip)
        area = None
        if activity_id is not None:
            thing = _in_country(db, Activity, activity_id, trip)
            kind, area, title = "activity", thing.area, thing.name
            ends = to_time(min(minutes(starts) + thing.minutes, planner.DAY_ENDS))
            cost_cents = planner.group_price(thing, prefs)
        elif restaurant_id is not None:
            thing = _in_country(db, Restaurant, restaurant_id, trip)
            meal = "Lunch" if minutes(starts) < 16 * 60 else "Dinner"
            kind, area, title = "meal", thing.area, f"{meal} at {thing.name}"
            ends = to_time(min(minutes(starts) + (planner.LUNCH_MINUTES if meal == "Lunch" else
                                                 planner.DINNER_MINUTES), planner.DAY_ENDS))
            cost_cents = planner.meal_price(thing, prefs)
        else:
            title = (title or "").strip()
            if not title:
                raise LimingError("Please say what it is")
            if len(title) > 140:
                raise LimingError("Please keep it under 140 characters")
            if ends is None:
                raise LimingError("Please give an end time")
            ends = _clock(ends)
            if not isinstance(cost_cents, int) or cost_cents < 0:
                raise LimingError("The cost can't be negative")
            kind = "custom"
        if ends <= starts:
            raise LimingError("It has to end after it starts")
        item = PlanItem(trip_id=trip.id, day=day, starts=starts, ends=ends, kind=kind, title=title,
                        activity_id=activity_id, restaurant_id=restaurant_id, area_id=area.id if area else None,
                        cost_cents=cost_cents, reason="You added this.", notes=(notes or "").strip()[:2000],
                        locked=True, added_by="you")
        db.add(item)
    return _refreshed(db, item)


def stay_choices(db, user, trip_id):
    trip = _own_trip(db, user, trip_id)
    prefs = Prefs.from_trip(trip)
    return [(s, planner.stay_cost(s, prefs), why)
            for s, why in planner.stay_options(prefs, load_catalogue(db, trip.destination_id))]


def choose_stay(db, user, trip_id, stay_id, now=None):
    """Pick a different stay. Check-in and check-out move with it; the rest of the plan stays as it is
    (regenerate to replan around the new base)."""
    now = now or datetime.now()
    with _tx(db):
        trip = _own_trip(db, user, trip_id, lock=True)
        if db.scalar(select(Booking).where(Booking.trip_id == trip.id, Booking.kind == "stay", holding(now))):
            raise LimingError("Your stay is booked. Cancel that booking before choosing another.")
        prefs = Prefs.from_trip(trip)
        options = {s.id: s for s, _ in planner.stay_options(prefs, load_catalogue(db, trip.destination_id))}
        if stay_id not in options:
            raise LimingError("That stay doesn't fit your group (size, children or step-free access)")
        stay = options[stay_id]
        trip.stay_id, trip.stay_locked = stay.id, True
        for i in _items(db, trip.id):
            if i.kind == "stay":
                i.title = (f"Check in at {stay.name}" if i.day == trip.start_date else f"Check out of {stay.name}")
                i.area_id = stay.area_id
    db.refresh(trip)
    return trip


# ======================================================================
# Helpers
# ======================================================================

def holding(now):
    """Bookings that still take up space: confirmed ones, and holds that haven't run out."""
    return or_(Booking.status == "confirmed", (Booking.status == "held") & (Booking.held_until > now))


def _live(db, trip_id, now):
    return db.scalar(select(func.count()).select_from(Booking).where(Booking.trip_id == trip_id, holding(now)))


def _not_booked(db, item, now):
    b = db.scalar(select(Booking).where(Booking.plan_item_id == item.id, holding(now)))
    if b is not None:
        raise LimingError(f"{item.title} is booked ({b.reference}). Cancel the booking first.")


def _items(db, trip_id):
    return db.scalars(select(PlanItem).where(PlanItem.trip_id == trip_id)
                      .order_by(PlanItem.day, PlanItem.starts, PlanItem.id)).all()


def _to_planned(i):
    return Planned(day=i.day, starts=minutes(i.starts), ends=minutes(i.ends), kind=i.kind, title=i.title,
                   area=i.area, cost_cents=i.cost_cents, reason=i.reason, activity=i.activity,
                   restaurant=i.restaurant, locked=i.locked, added_by=i.added_by, notes=i.notes, id=i.id)


def _refreshed(db, item):
    db.refresh(item)
    return item


def _clock(value):
    if isinstance(value, time):
        return value.replace(second=0, microsecond=0)
    try:
        return datetime.strptime(str(value).strip(), "%H:%M").time()
    except ValueError:
        raise LimingError("Times look like 09:30") from None


def _check_day(trip, day):
    if not isinstance(day, date) or not trip.start_date <= day <= trip.end_date:
        raise LimingError(f"That day isn't part of this trip ({trip.start_date:%d %b} to {trip.end_date:%d %b})")


def _in_country(db, model, thing_id, trip):
    thing = db.get(model, thing_id)
    if thing is None or thing.area.destination_id != trip.destination_id:
        raise NotFound(f"{'Activity' if model is Activity else 'Restaurant'} not found in "
                       f"{trip.destination.name}")
    return thing


def _get(db, model, obj_id, lock=False):
    q = select(model).where(model.id == obj_id)
    if lock:
        q = q.with_for_update(of=model)
    obj = db.scalar(q)
    if obj is None:
        raise NotFound(f"{model.__name__.replace('PlanItem', 'Plan item')} not found")
    return obj


def _own_trip(db, user, trip_id, lock=False):
    trip = _get(db, Trip, trip_id, lock=lock)
    if trip.owner_id != user.id:
        raise NotFound("Trip not found")          # someone else's trip looks exactly like a missing one
    if lock:
        db.refresh(trip)                         # read it fresh now that we hold the lock
    return trip


def _own_item(db, user, item_id, lock_trip=False):
    item = _get(db, PlanItem, item_id)
    trip = _own_trip(db, user, item.trip_id, lock=lock_trip)
    return item, trip


def count_items(db, trip_id):
    return db.scalar(select(func.count()).select_from(PlanItem).where(PlanItem.trip_id == trip_id))

