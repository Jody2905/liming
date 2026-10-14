"""The shapes of the API's requests and responses.

Requests are strict: unknown fields are rejected and numbers must be real JSON numbers.
The rules themselves (dates, budget, which paces exist...) are checked once, in services.py,
and GET /api/questions publishes the valid choices for the front end.
Times are "HH:MM" strings; money is whole US cents.
"""

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Int = Annotated[int, Field(strict=True)]
Clock = Annotated[str, Field(pattern=r"^\d{1,2}:\d{2}$", examples=["09:30"])]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Problem(BaseModel):
    detail: str = Field(description="A message that's safe to show the traveller")


# ---- Accounts ----------------------------------------------------------------------------------------

class RegisterIn(In):
    email: str = Field(max_length=254, examples=["sam@example.test"])
    name: str = Field(max_length=80, examples=["Sam"])
    password: str = Field(max_length=200, examples=["a-long-passphrase"])


class LoginIn(In):
    email: str = Field(max_length=254, examples=["jo@example.test"])
    password: str = Field(max_length=200, examples=["Liming-2026-demo"])


class UserOut(Out):
    id: int
    email: str
    name: str


class MeOut(BaseModel):
    user: UserOut
    csrf_token: str = Field(description="Send this back in the X-CSRF-Token header on every change")


# ---- The questions ----------------------------------------------------------------------------------------

class Choice(BaseModel):
    key: str
    label: str


class DestinationOut(Out):
    id: int
    code: str
    name: str
    blurb: str


class QuestionsOut(BaseModel):
    destinations: list[DestinationOut]
    interests: list[Choice]
    paces: list[Choice]
    stay_styles: list[Choice]
    dining_styles: list[Choice]
    transport: list[Choice]
    day_starts: list[Choice]
    diets: list[Choice]
    max_nights: int
    max_adults: int
    max_children: int
    min_budget_cents_per_person_night: int


class AnswersIn(In):
    title: str = Field(max_length=100, examples=["Beach and rainforest week"])
    destination_id: Int
    start_date: date
    end_date: date
    adults: Int = 2
    children: Int = 0
    youngest_age: Int | None = None
    budget_cents: Int = Field(examples=[400000])
    pace: str = Field(examples=["balanced"])
    stay_style: str = Field(examples=["hotel"])
    dining_style: str = Field(examples=["mix"])
    transport: str = Field(examples=["taxi"])
    day_start: str = "normal"
    step_free: bool = False
    interests: dict[str, Int] = Field(examples=[{"beaches": 2, "nature": 1}],
                                      description="Each interest rated 1 (like) or 2 (love)")
    diets: list[str] = Field(default_factory=list, examples=[["vegetarian"]])


class AnswersPatch(In):
    title: str | None = Field(None, max_length=100)
    destination_id: Int | None = None
    start_date: date | None = None
    end_date: date | None = None
    adults: Int | None = None
    children: Int | None = None
    youngest_age: Int | None = None
    budget_cents: Int | None = None
    pace: str | None = None
    stay_style: str | None = None
    dining_style: str | None = None
    transport: str | None = None
    day_start: str | None = None
    step_free: bool | None = None
    interests: dict[str, Int] | None = None
    diets: list[str] | None = None


class AnswersOut(BaseModel):
    start_date: date
    end_date: date
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
    interests: dict[str, int]
    diets: list[str]


# ---- The plan ------------------------------------------------------------------------------------------

class BookingOut(Out):
    id: int
    reference: str
    kind: str
    status: str
    title: str
    plan_item_id: int | None
    start_date: date
    end_date: date
    starts_at: datetime
    quantity: int
    units: int
    total_cents: int
    refund_cents: int
    held_until: datetime
    hold_seconds_left: int | None = None
    confirmed_at: datetime | None
    cancelled_at: datetime | None


class ItemBooking(BaseModel):
    id: int
    reference: str
    status: str
    hold_seconds_left: int | None


class ItemOut(BaseModel):
    id: int
    day: date
    starts: str
    ends: str
    kind: str
    title: str
    area: str | None
    cost_cents: int
    reason: str
    notes: str
    locked: bool
    added_by: str
    activity_id: int | None
    restaurant_id: int | None
    bookable: bool = Field(description="Can be held and booked (set-time activities and restaurant tables)")
    travel_minutes: int = Field(description="About how long to get here from the previous stop")
    booking: ItemBooking | None


class DayOut(BaseModel):
    date: date
    items: list[ItemOut]


class IssueOut(BaseModel):
    day: date | None
    item_id: int | None
    message: str


class TotalsOut(BaseModel):
    stay_cents: int
    activities_cents: int
    meals_cents: int
    transport_cents: int
    total_cents: int
    budget_cents: int
    left_cents: int
    booked_cents: int = Field(description="Committed so far: confirmed bookings and anything kept on cancellations")


class StayOut(BaseModel):
    id: int
    name: str
    style: str
    area: str
    blurb: str
    nightly_cents: int
    reason: str
    chosen_by_you: bool
    booking: ItemBooking | None


class TripSummary(BaseModel):
    id: int
    title: str
    destination: DestinationOut
    start_date: date
    end_date: date
    people: int
    stay: str | None


class PlanOut(BaseModel):
    id: int
    title: str
    destination: DestinationOut
    answers: AnswersOut
    stay: StayOut | None
    days: list[DayOut]
    issues: list[IssueOut] = Field(description="Things in the plan that won't work as it stands")
    totals: TotalsOut
    bookings: list[BookingOut]
    planned_at: datetime | None


class GenerateIn(In):
    fresh: bool = Field(False, description="Ask for something different: the next-best options get a turn")


class ItemIn(In):
    day: date
    starts: Clock
    ends: Clock | None = None
    title: str | None = Field(None, max_length=140, examples=["Call home"])
    activity_id: Int | None = None
    restaurant_id: Int | None = None
    cost_cents: Int = 0
    notes: str = Field("", max_length=2000)


class ItemPatch(In):
    day: date | None = None
    starts: Clock | None = None
    ends: Clock | None = None
    locked: bool | None = None
    notes: str | None = Field(None, max_length=2000)


class SwapIn(In):
    activity_id: Int | None = None
    restaurant_id: Int | None = None


class AlternativeOut(BaseModel):
    kind: str
    title: str
    starts: str
    ends: str
    cost_cents: int
    reason: str
    activity_id: int | None
    restaurant_id: int | None


class StayChoiceIn(In):
    stay_id: Int


class StayChoiceOut(BaseModel):
    id: int
    name: str
    style: str
    area: str
    blurb: str
    nightly_cents: int
    total_cents: int
    reason: str
    current: bool


class CatalogueActivity(BaseModel):
    id: int
    name: str
    area: str
    blurb: str
    tags: list[str]
    minutes: int
    price_cents: int
    child_price_cents: int
    min_age: int
    step_free: bool
    opens: str
    closes: str
    start_times: list[str]
    bookable: bool


class CatalogueRestaurant(BaseModel):
    id: int
    name: str
    area: str
    cuisine: str
    blurb: str
    price_band: int
    avg_cents: int
    lunch: bool
    dinner: bool
    vegetarian: bool
    vegan: bool
    gluten_free: bool


class CatalogueOut(BaseModel):
    activities: list[CatalogueActivity]
    restaurants: list[CatalogueRestaurant]


class RefundOut(BaseModel):
    refund_cents: int
    reason: str


class CancelOut(BaseModel):
    booking: BookingOut
    refund_cents: int
    reason: str
