"""Liming's web API (FastAPI). The rules live in services.py, planner.py and bookings.py;
this file only translates HTTP to those calls and back.

    py -m liming serve           then open http://127.0.0.1:8000/docs

Security (the same design as the author's Jaunt project)
  * Logging in sets an HttpOnly, SameSite=Lax cookie holding a random session token.
    The database keeps only a SHA-256 of that token.
  * Every change must also send the session's CSRF token in an X-CSRF-Token header.
  * Five wrong passwords for one email in 15 minutes pauses logins for that email.
  * Someone else's trip, plan item or booking answers 404, exactly as if it didn't exist.
"""

import mimetypes
import secrets
import threading
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response, Security
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.security import APIKeyCookie, APIKeyHeader
from fastapi.staticfiles import StaticFiles

from . import bookings, planner, services
from . import schemas as s
from .bookings import SoldOut
from .db import database_url, make_engine, session_factory
from .models import (
    DAY_STARTS,
    DIETS,
    DINING_STYLES,
    INTERESTS,
    PACES,
    STAY_STYLES,
    TRANSPORT,
    LoginSession,
    PlanItem,
    User,
)
from .services import LimingError, NotFound

COOKIE = "liming_session"
WEB = Path(__file__).resolve().parent / "web"         # the built React app (frontend/ builds into here)

# The app's pages may only load files from this server: no inline scripts, no outside code.
# /docs is left out because Swagger UI loads from a CDN.
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; "
       "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")

# Some Windows setups label .js as text/plain, which browsers refuse to run as a module
for kind, ext in (("text/javascript", ".js"), ("text/css", ".css"), ("font/woff2", ".woff2"),
                  ("image/svg+xml", ".svg")):
    mimetypes.add_type(kind, ext)
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

DESCRIPTION = """
Answer a few questions and get a timed, day-by-day Caribbean itinerary that explains every
choice. Then edit it, and book the stay, activities and restaurant tables.
**Every business and price is invented demo data. No payments are taken.**

### Trying it here
1. **POST /api/auth/login** with `jo@example.test` / `Liming-2026-demo` (*Try it out*, then *Execute*).
2. Copy `csrf_token` from the response, click **Authorize** and paste it into **X-CSRF-Token** only.
3. **GET /api/trips**, then **GET /api/trips/{trip_id}** for the whole plan with its reasons.
4. Try **POST /api/trips/{trip_id}/generate** with `{"fresh": true}` for something different,
   or **GET /api/items/{item_id}/alternatives** to see what else would fit.
"""

TAGS = [
    {"name": "account", "description": "Register, log in and out"},
    {"name": "questions", "description": "What the questionnaire asks, and the valid answers"},
    {"name": "plan", "description": "Trips, their generated plan, and regenerating it"},
    {"name": "editing", "description": "Lock, move, swap, add and remove plan items; choose another stay"},
    {"name": "bookings", "description": "Hold, confirm and cancel the stay, activities and tables"},
]

session_cookie = APIKeyCookie(name=COOKIE, auto_error=False,
                              description="Set automatically by your browser when you log in")
csrf_header = APIKeyHeader(name="X-CSRF-Token", auto_error=False,
                           description="The csrf_token from login or GET /api/me")


# ======================================================================
# Plumbing
# ======================================================================

def get_db(request: Request):
    db = request.app.state.Session()
    try:
        yield db
    finally:
        db.close()


def get_now(request: Request) -> datetime:
    return request.app.state.clock()


@dataclass
class Auth:
    user: User
    session: LoginSession
    token: str


def signed_in(request: Request, db=Depends(get_db), now=Depends(get_now),
              token: str | None = Security(session_cookie), csrf: str | None = Security(csrf_header)) -> Auth:
    found = services.session_for(db, token, now)
    if found is None:
        raise HTTPException(401, "Please log in")
    user, session = found
    if request.method not in SAFE_METHODS and not (csrf and secrets.compare_digest(csrf, session.csrf_token)):
        raise HTTPException(403, "Missing or wrong CSRF token: send X-CSRF-Token (from GET /api/me)")
    return Auth(user, session, token)


class LoginThrottle:
    """Counts wrong passwords per email. In memory, so it resets on restart (fine for one server)."""
    LIMIT, WINDOW = 5, timedelta(minutes=15)

    def __init__(self):
        self._failures = defaultdict(list)
        self._lock = threading.Lock()

    def wait_seconds(self, email, now):
        with self._lock:
            recent = [t for t in self._failures[email] if t > now - self.WINDOW]
            self._failures[email] = recent
            if len(recent) < self.LIMIT:
                return 0
            return max(1, int((recent[0] + self.WINDOW - now).total_seconds()))

    def failed(self, email, now):
        with self._lock:
            self._failures[email].append(now)

    def succeeded(self, email):
        with self._lock:
            self._failures.pop(email, None)


ERRORS = {400: {"model": s.Problem, "description": "A rule said no"},
          401: {"model": s.Problem, "description": "Not logged in"},
          403: {"model": s.Problem, "description": "Missing CSRF token"},
          404: {"model": s.Problem, "description": "Not found (or not yours)"},
          409: {"model": s.Problem, "description": "Fully booked"}}


def errors(*codes):
    return {c: ERRORS[c] for c in codes}


# ======================================================================
# Turning rows into responses
# ======================================================================

def hhmm(t):
    return f"{t:%H:%M}"


def booking_out(b, now):
    out = s.BookingOut.model_validate(b)
    if b.status == "held":
        left = int((b.held_until - now).total_seconds())
        if left > 0:
            out.hold_seconds_left = left
        else:
            out.status = "expired"                     # a lapsed hold reads as expired straight away
    return out


def _item_booking(out):
    if out is None or out.status not in ("held", "confirmed"):
        return None
    return s.ItemBooking(id=out.id, reference=out.reference, status=out.status,
                         hold_seconds_left=out.hold_seconds_left)


def plan_out(db, user, trip_id, now):
    view = services.plan_for(db, user, trip_id)
    trip = view.trip
    all_bookings = [booking_out(b, now) for b in bookings.bookings_for_trip(db, user, trip.id)]
    live = {b.plan_item_id: b for b in all_bookings if b.status in ("held", "confirmed") and b.plan_item_id}
    stay_booking = next((b for b in all_bookings if b.kind == "stay" and b.status in ("held", "confirmed")), None)
    days = []
    for day, items in view.days.items():
        prev_area = trip.stay.area if trip.stay else None
        out = []
        for i in items:
            bookable = (i.kind == "activity" and i.activity is not None and i.activity.capacity is not None) or (
                i.kind == "meal" and i.restaurant_id is not None)
            minutes = planner.travel(prev_area, i.area, trip.transport) if (prev_area and i.area and i.kind != "stay"
                                                                            and prev_area.id != i.area.id) else 0
            out.append(s.ItemOut(id=i.id, day=i.day, starts=hhmm(i.starts), ends=hhmm(i.ends), kind=i.kind,
                                 title=i.title, area=i.area.name if i.area else None, cost_cents=i.cost_cents,
                                 reason=i.reason, notes=i.notes, locked=i.locked, added_by=i.added_by,
                                 activity_id=i.activity_id, restaurant_id=i.restaurant_id, bookable=bookable,
                                 travel_minutes=minutes, booking=_item_booking(live.get(i.id))))
            prev_area = i.area or prev_area
        days.append(s.DayOut(date=day, items=out))
    stay = None
    if trip.stay:
        st = trip.stay
        stay = s.StayOut(id=st.id, name=st.name, style=st.style, area=st.area.name, blurb=st.blurb,
                         nightly_cents=st.nightly_cents, reason=view.stay_reason, chosen_by_you=trip.stay_locked,
                         booking=_item_booking(stay_booking))
    dest = s.DestinationOut.model_validate(trip.destination)
    return s.PlanOut(
        id=trip.id, title=trip.title, destination=dest,
        answers=s.AnswersOut(start_date=trip.start_date, end_date=trip.end_date, adults=trip.adults,
                             children=trip.children, youngest_age=trip.youngest_age, budget_cents=trip.budget_cents,
                             pace=trip.pace, stay_style=trip.stay_style, dining_style=trip.dining_style,
                             transport=trip.transport, day_start=trip.day_start, step_free=trip.step_free,
                             interests={i.tag: i.weight for i in trip.interests},
                             diets=sorted(d.diet for d in trip.diets)),
        stay=stay, days=days,
        issues=[s.IssueOut(day=i.day, item_id=i.item_id, message=i.message) for i in view.issues],
        totals=s.TotalsOut(**view.totals, booked_cents=bookings.booked_cents(db, trip.id)),
        bookings=all_bookings, planned_at=trip.planned_at)


def me_out(user, session):
    return s.MeOut(user=s.UserOut.model_validate(user), csrf_token=session.csrf_token)


def set_session_cookie(request, response, token):
    response.set_cookie(COOKIE, token, max_age=services.SESSION_DAYS * 86400, httponly=True, samesite="lax",
                        secure=request.app.state.secure_cookies, path="/")


def _trip_of_item(db, user, item_id):
    item = db.get(PlanItem, item_id)
    if item is None:
        raise NotFound("Plan item not found")
    services.get_trip(db, user, item.trip_id)          # 404 if it isn't yours
    return item.trip_id


# ======================================================================
# Account
# ======================================================================

account = APIRouter(prefix="/api", tags=["account"])


@account.post("/auth/register", status_code=201, response_model=s.MeOut, responses=errors(400))
def register(body: s.RegisterIn, request: Request, response: Response, db=Depends(get_db), now=Depends(get_now)):
    """Create an account and log straight in."""
    user = services.create_user(db, body.email, body.name, body.password, now=now)
    token, session = services.start_session(db, user, now=now)
    set_session_cookie(request, response, token)
    return me_out(user, session)


@account.post("/auth/login", response_model=s.MeOut,
              responses={401: ERRORS[401], 429: {"model": s.Problem, "description": "Too many wrong passwords"}})
def login(body: s.LoginIn, request: Request, response: Response, db=Depends(get_db), now=Depends(get_now),
          old_token: str | None = Security(session_cookie)):
    """Log in. Sets the session cookie and returns the CSRF token to send with changes."""
    email = body.email.strip().lower()
    throttle = request.app.state.throttle
    wait = throttle.wait_seconds(email, now)
    if wait:
        raise HTTPException(429, f"Too many wrong passwords. Try again in {wait // 60 + 1} minutes.",
                            headers={"Retry-After": str(wait)})
    user = services.authenticate(db, email, body.password)
    if user is None:
        throttle.failed(email, now)
        raise HTTPException(401, "Wrong email or password")
    throttle.succeeded(email)
    services.end_expired_sessions(db, now)
    services.end_session(db, old_token)                               # a fresh session on every login
    token, session = services.start_session(db, user, now=now)
    set_session_cookie(request, response, token)
    return me_out(user, session)


@account.post("/auth/logout", status_code=204, responses=errors(401, 403))
def logout(request: Request, response: Response, auth: Auth = Depends(signed_in), db=Depends(get_db)):
    """End this session. The old cookie stops working immediately, even if someone copied it."""
    services.end_session(db, auth.token)
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="lax", secure=request.app.state.secure_cookies)


@account.get("/me", response_model=s.MeOut, responses=errors(401))
def me(auth: Auth = Depends(signed_in)):
    """Who's logged in, and the CSRF token for this session."""
    return me_out(auth.user, auth.session)


# ======================================================================
# The questions
# ======================================================================

questions = APIRouter(prefix="/api", tags=["questions"])

PACE_WORDS = {"relaxed": "Relaxed: one thing a day", "balanced": "Balanced: two things a day",
              "packed": "Packed: as much as fits"}
DINING_WORDS = {"local": "Local spots, easy on the budget", "mix": "A mix", "treat": "Treat ourselves"}
TRANSPORT_WORDS = {"taxi": "Taxis", "hire_car": "A hire car", "bus": "Local buses"}
DAY_WORDS = {"early": "Early bird (from 8am)", "normal": "From about 9am", "late": "Slow mornings (from 10am)"}


@questions.get("/questions", response_model=s.QuestionsOut)
def the_questions(db=Depends(get_db)):
    """Everything the questionnaire needs: where you can go and the valid answer for each question."""
    return s.QuestionsOut(
        destinations=[s.DestinationOut.model_validate(d) for d in services.destinations(db)],
        interests=[s.Choice(key=k, label=v[0].upper() + v[1:]) for k, v in INTERESTS.items()],
        paces=[s.Choice(key=k, label=PACE_WORDS[k]) for k in PACES],
        stay_styles=[s.Choice(key=k, label=v[0].upper() + v[1:]) for k, v in STAY_STYLES.items()],
        dining_styles=[s.Choice(key=k, label=DINING_WORDS[k]) for k in DINING_STYLES],
        transport=[s.Choice(key=k, label=TRANSPORT_WORDS[k]) for k in TRANSPORT],
        day_starts=[s.Choice(key=k, label=DAY_WORDS[k]) for k in DAY_STARTS],
        diets=[s.Choice(key=k, label=v[0].upper() + v[1:]) for k, v in DIETS.items()],
        max_nights=services.MAX_NIGHTS, max_adults=8, max_children=6,
        min_budget_cents_per_person_night=services.MIN_BUDGET_PER_PERSON_NIGHT)


# ======================================================================
# Trips and the plan
# ======================================================================

plan = APIRouter(prefix="/api", tags=["plan"], responses=errors(401, 403, 404))


@plan.get("/trips", response_model=list[s.TripSummary])
def list_trips(auth: Auth = Depends(signed_in), db=Depends(get_db)):
    return [s.TripSummary(id=t.id, title=t.title, destination=s.DestinationOut.model_validate(t.destination),
                          start_date=t.start_date, end_date=t.end_date, people=t.people,
                          stay=t.stay.name if t.stay else None) for t in services.trips_for(db, auth.user)]


@plan.post("/trips", status_code=201, response_model=s.PlanOut, responses=errors(400))
def create_trip(body: s.AnswersIn, auth: Auth = Depends(signed_in), db=Depends(get_db), now=Depends(get_now)):
    """Save the answers and build the first plan."""
    trip = services.create_trip(db, auth.user, now=now, **body.model_dump())
    return plan_out(db, auth.user, trip.id, now)


@plan.get("/trips/{trip_id}", response_model=s.PlanOut)
def get_plan(trip_id: int, auth: Auth = Depends(signed_in), db=Depends(get_db), now=Depends(get_now)):
    """The whole plan: every day's timed items with their reasons, warnings, costs and bookings."""
    return plan_out(db, auth.user, trip_id, now)


@plan.patch("/trips/{trip_id}/answers", response_model=s.PlanOut, responses=errors(400))
def change_answers(trip_id: int, body: s.AnswersPatch, auth: Auth = Depends(signed_in), db=Depends(get_db),
                   now=Depends(get_now)):
    """Change some answers, then rebuild the plan around anything locked or added by you."""
    changes = body.model_dump(exclude_unset=True)
    services.update_answers(db, auth.user, trip_id, now=now, **changes)
    services.generate(db, auth.user, trip_id, now=now)
    return plan_out(db, auth.user, trip_id, now)


@plan.post("/trips/{trip_id}/generate", response_model=s.PlanOut, responses=errors(400))
def generate(trip_id: int, body: s.GenerateIn, auth: Auth = Depends(signed_in), db=Depends(get_db),
             now=Depends(get_now)):
    """Rebuild the plan. Locked items, booked items and anything you added stay put."""
    services.generate(db, auth.user, trip_id, now=now, fresh=body.fresh)
    return plan_out(db, auth.user, trip_id, now)


@plan.post("/trips/{trip_id}/days/{day}/regenerate", response_model=s.PlanOut, responses=errors(400))
def regenerate_day(trip_id: int, day: date, auth: Auth = Depends(signed_in), db=Depends(get_db),
                   now=Depends(get_now)):
    """Redo one day; the other days don't change."""
    services.regenerate_day(db, auth.user, trip_id, day, now=now)
    return plan_out(db, auth.user, trip_id, now)


@plan.delete("/trips/{trip_id}", status_code=204, responses=errors(400))
def delete_trip(trip_id: int, auth: Auth = Depends(signed_in), db=Depends(get_db), now=Depends(get_now)):
    services.delete_trip(db, auth.user, trip_id, now=now)


@plan.get("/trips/{trip_id}/catalogue", response_model=s.CatalogueOut)
def catalogue(trip_id: int, auth: Auth = Depends(signed_in), db=Depends(get_db)):
    """Everything in the trip's country, for adding to the plan by hand."""
    trip = services.get_trip(db, auth.user, trip_id)
    cat = services.load_catalogue(db, trip.destination_id)
    return s.CatalogueOut(
        activities=[s.CatalogueActivity(id=a.id, name=a.name, area=a.area.name, blurb=a.blurb,
                                        tags=sorted(a.tag_names), minutes=a.minutes, price_cents=a.price_cents,
                                        child_price_cents=a.child_price_cents, min_age=a.min_age,
                                        step_free=a.step_free, opens=hhmm(a.opens), closes=hhmm(a.closes),
                                        start_times=[hhmm(t.starts) for t in a.start_times],
                                        bookable=a.capacity is not None) for a in cat.activities],
        restaurants=[s.CatalogueRestaurant(id=r.id, name=r.name, area=r.area.name, cuisine=r.cuisine, blurb=r.blurb,
                                           price_band=r.price_band, avg_cents=r.avg_cents, lunch=r.lunch,
                                           dinner=r.dinner, vegetarian=r.vegetarian, vegan=r.vegan,
                                           gluten_free=r.gluten_free) for r in cat.restaurants])


# ======================================================================
# Editing
# ======================================================================

editing = APIRouter(prefix="/api", tags=["editing"], responses=errors(400, 401, 403, 404))


@editing.post("/trips/{trip_id}/items", status_code=201, response_model=s.PlanOut)
def add_item(trip_id: int, body: s.ItemIn, auth: Auth = Depends(signed_in), db=Depends(get_db),
             now=Depends(get_now)):
    """Add your own plan (title + times), an activity from the catalogue, or a meal at a restaurant."""
    services.add_item(db, auth.user, trip_id, body.day, body.starts, ends=body.ends, title=body.title,
                      activity_id=body.activity_id, restaurant_id=body.restaurant_id, cost_cents=body.cost_cents,
                      notes=body.notes)
    return plan_out(db, auth.user, trip_id, now)


@editing.patch("/items/{item_id}", response_model=s.PlanOut)
def edit_item(item_id: int, body: s.ItemPatch, auth: Auth = Depends(signed_in), db=Depends(get_db),
              now=Depends(get_now)):
    """Move (day and/or start), change the end time, lock or unlock, or add notes.
    Moving or retiming locks the item, so regenerating won't undo it."""
    trip_id = _trip_of_item(db, auth.user, item_id)
    changes = body.model_dump(exclude_unset=True)
    item = db.get(PlanItem, item_id)
    if "day" in changes or "starts" in changes:
        services.move_item(db, auth.user, item_id, changes.get("day") or item.day,
                           changes.get("starts") or item.starts, now=now)
        item = db.get(PlanItem, item_id)
    if changes.get("ends"):
        services.retime_item(db, auth.user, item_id, item.starts, changes["ends"], now=now)
    if changes.get("locked") is not None:
        services.set_locked(db, auth.user, item_id, changes["locked"], now=now)
    if "notes" in changes:
        services.set_notes(db, auth.user, item_id, changes["notes"])
    return plan_out(db, auth.user, trip_id, now)


@editing.delete("/items/{item_id}", response_model=s.PlanOut)
def remove_item(item_id: int, auth: Auth = Depends(signed_in), db=Depends(get_db), now=Depends(get_now)):
    trip_id = services.remove_item(db, auth.user, item_id, now=now)
    return plan_out(db, auth.user, trip_id, now)


@editing.get("/items/{item_id}/alternatives", response_model=list[s.AlternativeOut])
def alternatives(item_id: int, auth: Auth = Depends(signed_in), db=Depends(get_db)):
    """What else would fit this item's gap, best first, each with its reason. Changes nothing."""
    return [s.AlternativeOut(kind=o.kind, title=o.title, starts=planner.clock(o.starts), ends=planner.clock(o.ends),
                             cost_cents=o.cost_cents, reason=o.reason,
                             activity_id=o.activity.id if o.activity else None,
                             restaurant_id=o.restaurant.id if o.restaurant else None)
            for o in services.alternatives(db, auth.user, item_id)]


@editing.post("/items/{item_id}/swap", response_model=s.PlanOut)
def swap(item_id: int, body: s.SwapIn, auth: Auth = Depends(signed_in), db=Depends(get_db), now=Depends(get_now)):
    """Swap in an alternative (or anything from the same country). The new item is locked."""
    trip_id = _trip_of_item(db, auth.user, item_id)
    services.swap(db, auth.user, item_id, activity_id=body.activity_id, restaurant_id=body.restaurant_id, now=now)
    return plan_out(db, auth.user, trip_id, now)


@editing.get("/trips/{trip_id}/stays", response_model=list[s.StayChoiceOut])
def stays(trip_id: int, auth: Auth = Depends(signed_in), db=Depends(get_db)):
    """Every stay that suits the group, best first."""
    trip = services.get_trip(db, auth.user, trip_id)
    return [s.StayChoiceOut(id=st.id, name=st.name, style=st.style, area=st.area.name, blurb=st.blurb,
                            nightly_cents=st.nightly_cents, total_cents=cost, reason=why, current=st.id == trip.stay_id)
            for st, cost, why in services.stay_choices(db, auth.user, trip_id)]


@editing.put("/trips/{trip_id}/stay", response_model=s.PlanOut)
def choose_stay(trip_id: int, body: s.StayChoiceIn, auth: Auth = Depends(signed_in), db=Depends(get_db),
                now=Depends(get_now)):
    """Pick a different stay. Check-in and check-out move with it; regenerate to replan around it."""
    services.choose_stay(db, auth.user, trip_id, body.stay_id, now=now)
    return plan_out(db, auth.user, trip_id, now)


# ======================================================================
# Bookings
# ======================================================================

booking = APIRouter(prefix="/api", tags=["bookings"], responses=errors(400, 401, 403, 404, 409))


@booking.post("/trips/{trip_id}/stay/hold", status_code=201, response_model=s.BookingOut)
def hold_stay(trip_id: int, auth: Auth = Depends(signed_in), db=Depends(get_db), now=Depends(get_now)):
    """Hold the stay for every night (enough rooms for everyone) for 15 minutes."""
    return booking_out(bookings.hold_stay(db, auth.user, trip_id, now=now), now)


@booking.post("/items/{item_id}/hold", status_code=201, response_model=s.BookingOut)
def hold_item(item_id: int, auth: Auth = Depends(signed_in), db=Depends(get_db), now=Depends(get_now)):
    """Hold places on this activity, or a table for this meal, for 15 minutes. The item is locked."""
    return booking_out(bookings.hold_item(db, auth.user, item_id, now=now), now)


@booking.post("/bookings/{booking_id}/confirm", response_model=s.BookingOut)
def confirm(booking_id: int, auth: Auth = Depends(signed_in), db=Depends(get_db), now=Depends(get_now)):
    """Confirm a hold (a real system would take payment here)."""
    return booking_out(bookings.confirm(db, auth.user, booking_id, now=now), now)


@booking.get("/bookings/{booking_id}/refund", response_model=s.RefundOut)
def refund_quote(booking_id: int, auth: Auth = Depends(signed_in), db=Depends(get_db), now=Depends(get_now)):
    """What cancelling now would give back, and why. Changes nothing."""
    r = bookings.refund_quote(db, auth.user, booking_id, now=now)
    return s.RefundOut(refund_cents=r.cents, reason=r.reason)


@booking.post("/bookings/{booking_id}/cancel", response_model=s.CancelOut)
def cancel(booking_id: int, auth: Auth = Depends(signed_in), db=Depends(get_db), now=Depends(get_now)):
    b, r = bookings.cancel(db, auth.user, booking_id, now=now)
    return s.CancelOut(booking=booking_out(b, now), refund_cents=b.refund_cents, reason=r.reason)


# ======================================================================
# The app
# ======================================================================

def create_app(url=None, engine=None, clock=None, secure_cookies=False):
    """`clock` lets tests choose what time it is. Pass secure_cookies=True when served over HTTPS."""
    app = FastAPI(title="Liming", version="1.0.0", description=DESCRIPTION, openapi_tags=TAGS)
    app.state.Session = session_factory(engine or make_engine(url or database_url()))
    app.state.clock = clock or datetime.now
    app.state.secure_cookies = secure_cookies
    app.state.throttle = LoginThrottle()

    for router in (account, questions, plan, editing, booking):
        app.include_router(router)

    @app.exception_handler(LimingError)
    def rule_broken(request, exc):
        status = 404 if isinstance(exc, NotFound) else 409 if isinstance(exc, SoldOut) else 400
        return JSONResponse({"detail": str(exc)}, status_code=status)

    @app.exception_handler(RequestValidationError)
    def bad_request(request, exc):
        def where(err):
            return ".".join(str(p) for p in err["loc"] if p not in ("body", "query", "path"))
        return JSONResponse({"detail": "; ".join(f"{where(e)}: {e['msg']}" for e in exc.errors())},
                            status_code=422)

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        path = request.url.path
        if path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        if not (path.startswith("/docs") or path.startswith("/redoc")):
            response.headers["Content-Security-Policy"] = CSP
        return response

    if (WEB / "index.html").exists():
        app.mount("/static", StaticFiles(directory=WEB), name="static")

    @app.get("/", include_in_schema=False)
    def home():
        """The React app is one page; it moves between screens itself (#/plan/1 ...)."""
        if not (WEB / "index.html").exists():
            return HTMLResponse("<p>The front end hasn't been built yet. Run <code>npm run build</code> in "
                                "<code>frontend/</code>, or use the API at <a href='/docs'>/docs</a>.</p>",
                                status_code=503)
        return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})

    return app

