"""Liming's tables.

Three groups:
  * the catalogue: destinations (countries) split into areas, and in each area the
    stays, activities and restaurants the planner can choose from
  * the traveller's answers: a trip, with its interests and food needs
  * the plan: timed items on each day of the trip, which the planner writes and the
    traveller can then move, swap, lock, remove or add to

The database enforces the important rules itself (CHECK, UNIQUE, foreign keys), so
even a bug in the code can't store something impossible.
"""

from datetime import date, datetime, time

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

INTERESTS = {
    "beaches": "beaches and swimming",
    "nature": "nature and gardens",
    "hiking": "hiking",
    "culture": "history and culture",
    "food": "food and drink",
    "water": "snorkelling and sailing",
    "adventure": "adventure",
    "nightlife": "nightlife and music",
    "wellness": "wellness and spas",
    "shopping": "markets and shopping",
}
PACES = ("relaxed", "balanced", "packed")
STAY_STYLES = {
    "guesthouse": "simple guesthouse",
    "hotel": "comfortable hotel",
    "boutique": "small boutique hotel",
    "resort": "resort",
    "villa": "villa with a kitchen",
}
DINING_STYLES = ("local", "mix", "treat")            # cheap local spots / a mix / special meals
TRANSPORT = ("taxi", "hire_car", "bus")
DAY_STARTS = ("early", "normal", "late")
DIETS = {"vegetarian": "vegetarian", "vegan": "vegan", "gluten_free": "gluten-free"}
ITEM_KINDS = ("activity", "meal", "stay", "custom")
BEST_TIMES = ("morning", "afternoon", "evening", "any")


def _in(column, values):
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime]


# ======================================================================
# The catalogue
# ======================================================================

class Destination(Base):
    """A country the planner covers."""
    __tablename__ = "destinations"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(2), unique=True)          # ISO country code, e.g. VC
    name: Mapped[str] = mapped_column(String(80))
    blurb: Mapped[str] = mapped_column(Text, default="")

    areas: Mapped[list["Area"]] = relationship(back_populates="destination", lazy="selectin",
                                               order_by="Area.id")


class Area(Base):
    """A part of a country. Travel time between areas is worked out from their positions."""
    __tablename__ = "areas"
    __table_args__ = (CheckConstraint("lat BETWEEN -90 AND 90 AND lng BETWEEN -180 AND 180", name="area_on_earth"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    destination_id: Mapped[int] = mapped_column(ForeignKey("destinations.id"))
    name: Mapped[str] = mapped_column(String(80))
    island: Mapped[str] = mapped_column(String(40))                     # crossing to another island means a ferry
    lat: Mapped[float]
    lng: Mapped[float]

    destination: Mapped[Destination] = relationship(back_populates="areas")


class Stay(Base):
    __tablename__ = "stays"
    __table_args__ = (
        CheckConstraint(_in("style", STAY_STYLES), name="stay_style_known"),
        CheckConstraint("nightly_cents > 0 AND sleeps > 0 AND rooms_total > 0", name="stay_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("areas.id"))
    name: Mapped[str] = mapped_column(String(100))
    style: Mapped[str] = mapped_column(String(12))
    blurb: Mapped[str] = mapped_column(Text, default="")
    nightly_cents: Mapped[int]                                        # per room (or per villa)
    sleeps: Mapped[int]                                               # people per room
    rooms_total: Mapped[int]
    kid_friendly: Mapped[bool] = mapped_column(default=True)
    step_free: Mapped[bool] = mapped_column(default=False)
    free_cancel_hours: Mapped[int] = mapped_column(default=48)

    area: Mapped[Area] = relationship(lazy="joined")


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (
        CheckConstraint("minutes > 0 AND price_cents >= 0 AND child_price_cents >= 0", name="activity_positive"),
        CheckConstraint("energy BETWEEN 1 AND 3", name="activity_energy_1_to_3"),
        CheckConstraint(_in("best_time", BEST_TIMES), name="activity_best_time_known"),
        CheckConstraint("closes > opens", name="activity_opens_before_closing"),
        CheckConstraint("min_age BETWEEN 0 AND 18", name="activity_min_age"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("areas.id"))
    name: Mapped[str] = mapped_column(String(100))
    blurb: Mapped[str] = mapped_column(Text, default="")
    minutes: Mapped[int]
    price_cents: Mapped[int]                                          # per adult; 0 = free
    child_price_cents: Mapped[int]
    energy: Mapped[int]                                               # 1 easy, 2 active, 3 strenuous
    min_age: Mapped[int] = mapped_column(default=0)
    step_free: Mapped[bool] = mapped_column(default=False)            # works for a wheelchair or pushchair
    best_time: Mapped[str] = mapped_column(String(10), default="any")
    opens: Mapped[time]
    closes: Mapped[time]
    closed_days: Mapped[str] = mapped_column(String(7), default="")  # weekday digits, Monday=0: "6" = Sundays
    includes_lunch: Mapped[bool] = mapped_column(default=False)
    includes_dinner: Mapped[bool] = mapped_column(default=False)     # a Friday fish fry is dinner too
    highlight: Mapped[bool] = mapped_column(default=False)           # a local favourite worth the trip
    capacity: Mapped[int | None]                                     # bookable: places per start time

    area: Mapped[Area] = relationship(lazy="joined")
    tags: Mapped[list["ActivityTag"]] = relationship(lazy="selectin", cascade="all, delete-orphan")
    start_times: Mapped[list["ActivityStart"]] = relationship(lazy="selectin", cascade="all, delete-orphan",
                                                              order_by="ActivityStart.starts")

    @property
    def tag_names(self):
        return {t.tag for t in self.tags}


class ActivityTag(Base):
    __tablename__ = "activity_tags"
    __table_args__ = (CheckConstraint(_in("tag", INTERESTS), name="activity_tag_known"),)

    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id", ondelete="CASCADE"), primary_key=True)
    tag: Mapped[str] = mapped_column(String(12), primary_key=True)


class ActivityStart(Base):
    """Activities that run at set times (a boat trip, a guided hike). Others start whenever you like."""
    __tablename__ = "activity_starts"

    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id", ondelete="CASCADE"), primary_key=True)
    starts: Mapped[time] = mapped_column(primary_key=True)


class Restaurant(Base):
    __tablename__ = "restaurants"
    __table_args__ = (
        CheckConstraint("price_band BETWEEN 1 AND 4", name="restaurant_band_1_to_4"),
        CheckConstraint("avg_cents > 0 AND covers > 0", name="restaurant_positive"),
        CheckConstraint("lunch OR dinner", name="restaurant_serves_something"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("areas.id"))
    name: Mapped[str] = mapped_column(String(100))
    cuisine: Mapped[str] = mapped_column(String(60))
    blurb: Mapped[str] = mapped_column(Text, default="")
    price_band: Mapped[int]                                           # 1 cheap .. 4 special occasion
    avg_cents: Mapped[int]                                            # a typical meal, per person
    lunch: Mapped[bool]                                               # serves 12:00-15:00
    dinner: Mapped[bool]                                              # serves 18:00-22:00
    closed_days: Mapped[str] = mapped_column(String(7), default="")
    vegetarian: Mapped[bool] = mapped_column(default=False)
    vegan: Mapped[bool] = mapped_column(default=False)
    gluten_free: Mapped[bool] = mapped_column(default=False)
    kid_friendly: Mapped[bool] = mapped_column(default=True)
    step_free: Mapped[bool] = mapped_column(default=False)
    covers: Mapped[int] = mapped_column(default=30)                  # seats per sitting, for table bookings

    area: Mapped[Area] = relationship(lazy="joined")


# ======================================================================
# The traveller's answers
# ======================================================================

class Trip(Base):
    __tablename__ = "trips"
    __table_args__ = (
        CheckConstraint("end_date > start_date", name="trip_at_least_one_night"),
        CheckConstraint("adults BETWEEN 1 AND 8", name="trip_adults_1_to_8"),
        CheckConstraint("children BETWEEN 0 AND 6", name="trip_children_0_to_6"),
        CheckConstraint("(children = 0) = (youngest_age IS NULL)", name="trip_youngest_age_iff_children"),
        CheckConstraint("youngest_age IS NULL OR youngest_age BETWEEN 0 AND 17", name="trip_youngest_is_a_child"),
        CheckConstraint("budget_cents > 0", name="trip_budget_positive"),
        CheckConstraint(_in("pace", PACES), name="trip_pace_known"),
        CheckConstraint(_in("stay_style", STAY_STYLES), name="trip_stay_style_known"),
        CheckConstraint(_in("dining_style", DINING_STYLES), name="trip_dining_style_known"),
        CheckConstraint(_in("transport", TRANSPORT), name="trip_transport_known"),
        CheckConstraint(_in("day_start", DAY_STARTS), name="trip_day_start_known"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(100))
    destination_id: Mapped[int] = mapped_column(ForeignKey("destinations.id"))
    start_date: Mapped[date]                                          # arrival day
    end_date: Mapped[date]                                            # departure day
    adults: Mapped[int]
    children: Mapped[int] = mapped_column(default=0)
    youngest_age: Mapped[int | None]
    budget_cents: Mapped[int]                                         # for everything, for everyone
    pace: Mapped[str] = mapped_column(String(10))
    stay_style: Mapped[str] = mapped_column(String(12))
    dining_style: Mapped[str] = mapped_column(String(6))
    transport: Mapped[str] = mapped_column(String(10))
    day_start: Mapped[str] = mapped_column(String(6), default="normal")
    step_free: Mapped[bool] = mapped_column(default=False)            # someone needs step-free access
    stay_id: Mapped[int | None] = mapped_column(ForeignKey("stays.id"))
    stay_locked: Mapped[bool] = mapped_column(default=False)          # the traveller chose this stay themselves
    variety: Mapped[int] = mapped_column(default=0)                   # "show me something different" counter
    created_at: Mapped[datetime]
    planned_at: Mapped[datetime | None]

    destination: Mapped[Destination] = relationship(lazy="joined")
    stay: Mapped[Stay | None] = relationship(lazy="joined")
    interests: Mapped[list["TripInterest"]] = relationship(lazy="selectin", cascade="all, delete-orphan")
    diets: Mapped[list["TripDiet"]] = relationship(lazy="selectin", cascade="all, delete-orphan")

    @property
    def people(self):
        return self.adults + self.children

    @property
    def nights(self):
        return (self.end_date - self.start_date).days


class TripInterest(Base):
    __tablename__ = "trip_interests"
    __table_args__ = (CheckConstraint(_in("tag", INTERESTS), name="interest_tag_known"),
                      CheckConstraint("weight IN (1, 2)", name="interest_like_or_love"))

    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), primary_key=True)
    tag: Mapped[str] = mapped_column(String(12), primary_key=True)
    weight: Mapped[int]                                               # 1 like, 2 love


class TripDiet(Base):
    __tablename__ = "trip_diets"
    __table_args__ = (CheckConstraint(_in("diet", DIETS), name="diet_known"),)

    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), primary_key=True)
    diet: Mapped[str] = mapped_column(String(12), primary_key=True)


# ======================================================================
# The plan
# ======================================================================

class PlanItem(Base):
    """One timed thing on one day. `added_by` says whether the planner or the traveller put it there;
    `locked` items are kept when the plan is regenerated."""
    __tablename__ = "plan_items"
    __table_args__ = (
        CheckConstraint(_in("kind", ITEM_KINDS), name="item_kind_known"),
        CheckConstraint("ends > starts", name="item_ends_after_it_starts"),
        CheckConstraint("cost_cents >= 0", name="item_cost_not_negative"),
        CheckConstraint("added_by IN ('planner', 'you')", name="item_added_by_known"),
        CheckConstraint("(kind = 'activity') = (activity_id IS NOT NULL)", name="activity_items_name_one"),
        CheckConstraint("restaurant_id IS NULL OR kind = 'meal'", name="only_meals_name_a_restaurant"),
        Index("ix_plan_items_trip_day", "trip_id", "day", "starts"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"))
    day: Mapped[date]
    starts: Mapped[time]
    ends: Mapped[time]
    kind: Mapped[str] = mapped_column(String(10))
    activity_id: Mapped[int | None] = mapped_column(ForeignKey("activities.id"))
    restaurant_id: Mapped[int | None] = mapped_column(ForeignKey("restaurants.id"))
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"))   # where it happens, for travel times
    title: Mapped[str] = mapped_column(String(140))
    cost_cents: Mapped[int] = mapped_column(default=0)                     # estimate for the whole group
    reason: Mapped[str] = mapped_column(Text, default="")                  # why the planner picked it
    notes: Mapped[str] = mapped_column(Text, default="")
    locked: Mapped[bool] = mapped_column(default=False)
    added_by: Mapped[str] = mapped_column(String(8), default="planner")

    activity: Mapped[Activity | None] = relationship(lazy="joined")
    restaurant: Mapped[Restaurant | None] = relationship(lazy="joined")
    area: Mapped[Area | None] = relationship(lazy="joined")


# ======================================================================
# Bookings and logins
# ======================================================================

BOOKING_KINDS = ("stay", "activity", "table")
BOOKING_STATUSES = ("held", "confirmed", "cancelled", "expired")


class Booking(Base):
    """One booking: the stay for the whole trip, places on an activity at a set time, or a table.

    It starts as a 15-minute HOLD (space set aside while the traveller decides), then is
    CONFIRMED, or lapses (EXPIRED), or is CANCELLED. Exactly one of stay_id / activity_id /
    restaurant_id is set, matching `kind`; the database checks that.
    """
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint(_in("kind", BOOKING_KINDS), name="booking_kind_known"),
        CheckConstraint(_in("status", BOOKING_STATUSES), name="booking_status_known"),
        CheckConstraint("quantity > 0 AND units > 0", name="booking_quantity_positive"),
        CheckConstraint("total_cents >= 0 AND refund_cents >= 0 AND refund_cents <= total_cents",
                        name="booking_money_adds_up"),
        CheckConstraint("end_date >= start_date", name="booking_ends_after_start"),
        CheckConstraint("(kind = 'stay') = (stay_id IS NOT NULL) AND (kind = 'activity') = (activity_id IS NOT NULL)"
                        " AND (kind = 'table') = (restaurant_id IS NOT NULL)", name="booking_points_at_one_thing"),
        CheckConstraint("kind <> 'table' OR total_cents = 0", name="tables_are_free_to_book"),
        Index("ix_bookings_stay_dates", "stay_id", "status", "start_date", "end_date"),
        Index("ix_bookings_activity_slot", "activity_id", "status", "starts_at"),
        Index("ix_bookings_table_day", "restaurant_id", "status", "start_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(12), unique=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    plan_item_id: Mapped[int | None] = mapped_column(ForeignKey("plan_items.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(10))
    stay_id: Mapped[int | None] = mapped_column(ForeignKey("stays.id"))
    activity_id: Mapped[int | None] = mapped_column(ForeignKey("activities.id"))
    restaurant_id: Mapped[int | None] = mapped_column(ForeignKey("restaurants.id"))
    title: Mapped[str] = mapped_column(String(160))                  # frozen at booking time
    start_date: Mapped[date]                                         # check-in / the day
    end_date: Mapped[date]                                           # check-out / the same day
    starts_at: Mapped[datetime]                                      # exact start, for cancellation rules
    quantity: Mapped[int]                                            # rooms, or people
    units: Mapped[int] = mapped_column(default=1)                    # nights for a stay, else 1
    total_cents: Mapped[int]
    refund_cents: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime]
    held_until: Mapped[datetime]
    confirmed_at: Mapped[datetime | None]
    cancelled_at: Mapped[datetime | None]


class LoginSession(Base):
    """A signed-in browser. Only a SHA-256 of the cookie token is kept."""
    __tablename__ = "login_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime]
    expires_at: Mapped[datetime]
