"""The web API, through real HTTP requests (FastAPI's TestClient)."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from liming.api import COOKIE, create_app
from liming.models import LoginSession

from .conftest import NOW, PASSWORD, activity, answers, restaurant


class Clock:
    def __init__(self):
        self.now = NOW

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def client(engine, clock, dest):
    with TestClient(create_app(engine=engine, clock=clock)) as c:
        yield c


def log_in(client, email="jo@example.test", password=PASSWORD):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    client.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return r


@pytest.fixture
def jo_client(client, jo):
    log_in(client)
    return client


def body(dest, **changes):
    a = answers(dest, **changes)
    return {**a, "start_date": a["start_date"].isoformat(), "end_date": a["end_date"].isoformat(),
            "diets": sorted(a["diets"])}


@pytest.fixture
def plan(jo_client, dest):
    r = jo_client.post("/api/trips", json=body(dest))
    assert r.status_code == 201, r.text
    return r.json()


def items(plan, day=None):
    return [i for d_ in plan["days"] for i in d_["items"] if day is None or d_["date"] == day]


# ---- Accounts and security --------------------------------------------------------------------------------

def test_register_and_session_cookie(client):
    r = client.post("/api/auth/register", json={"email": "Sam@Example.test", "name": "Sam",
                                                "password": "a-long-passphrase"})
    assert r.status_code == 201, r.text
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert client.get("/api/me").json()["user"]["email"] == "sam@example.test"


def test_only_a_hash_of_the_cookie_is_stored(client, jo, db):
    log_in(client)
    stored = db.scalars(select(LoginSession.token_hash)).all()
    assert len(stored) == 1 and client.cookies[COOKIE] not in stored[0] and len(stored[0]) == 64


def test_login_throttle_and_same_answer_for_unknown_email(client, jo, clock):
    wrong = client.post("/api/auth/login", json={"email": "jo@example.test", "password": "wrong-password"})
    nobody = client.post("/api/auth/login", json={"email": "nobody@example.test", "password": "wrong-password"})
    assert wrong.status_code == nobody.status_code == 401 and wrong.json() == nobody.json()
    for _ in range(4):
        client.post("/api/auth/login", json={"email": "jo@example.test", "password": "wrong-password"})
    assert client.post("/api/auth/login", json={"email": "jo@example.test", "password": PASSWORD}).status_code == 429
    clock.advance(minutes=15, seconds=1)
    log_in(client)


def test_changes_need_a_login_and_the_csrf_token(client, jo, dest):
    assert client.get("/api/trips").status_code == 401
    log_in(client)
    good = client.headers.pop("X-CSRF-Token")
    assert client.post("/api/trips", json=body(dest)).status_code == 403
    assert client.post("/api/trips", json=body(dest), headers={"X-CSRF-Token": "guess"}).status_code == 403
    assert client.post("/api/trips", json=body(dest), headers={"X-CSRF-Token": good}).status_code == 201


def test_logout_and_expiry(jo_client, clock):
    stolen = jo_client.cookies[COOKIE]
    assert jo_client.post("/api/auth/logout").status_code == 204
    jo_client.cookies.set(COOKIE, stolen)
    assert jo_client.get("/api/me").status_code == 401
    log_in(jo_client)
    clock.advance(days=7)
    assert jo_client.get("/api/me").status_code == 401


def test_security_headers(jo_client):
    h = jo_client.get("/api/trips").headers
    assert (h["x-content-type-options"], h["x-frame-options"], h["cache-control"]) == ("nosniff", "DENY", "no-store")


# ---- The questions and the plan ---------------------------------------------------------------------------

def test_questions_list_every_valid_answer(client):
    q = client.get("/api/questions").json()
    assert [d_["code"] for d_ in q["destinations"]] == ["BB", "DM", "GD", "LC", "VC"]
    assert {c["key"] for c in q["interests"]} >= {"beaches", "hiking", "food", "nightlife"}
    assert [c["key"] for c in q["paces"]] == ["relaxed", "balanced", "packed"]
    assert q["max_nights"] == 14 and q["min_budget_cents_per_person_night"] == 5000


def test_answers_become_a_plan_that_explains_itself(plan):
    assert plan["title"] == "Island week" and plan["destination"]["code"] == "VC"
    assert [d_["date"] for d_ in plan["days"]] == [f"2026-11-{n:02d}" for n in range(9, 15)]
    acts = [i for i in items(plan) if i["kind"] == "activity"]
    assert acts and all(i["reason"] and ":" in i["starts"] for i in acts)
    assert plan["stay"]["reason"].startswith("A comfortable hotel, as you asked.")
    assert plan["issues"] == [] and plan["totals"]["left_cents"] > 0
    assert any(i["travel_minutes"] > 0 for i in items(plan))


@pytest.mark.parametrize("change, status, message", [
    ({"pace": "frantic"}, 400, "Please choose a pace"),
    ({"budget_cents": 100}, 400, "the budget needs to be at least"),
    ({"adults": "2"}, 422, "adults: Input should be a valid integer"),
    ({"surprise": 1}, 422, "surprise: Extra inputs are not permitted"),
])
def test_bad_answers_are_explained(jo_client, dest, change, status, message):
    r = jo_client.post("/api/trips", json={**body(dest), **change})
    assert r.status_code == status and message in r.json()["detail"], r.text


def test_change_answers_and_regenerate(jo_client, plan):
    r = jo_client.patch(f"/api/trips/{plan['id']}/answers", json={"pace": "relaxed", "end_date": "2026-11-12"})
    assert r.status_code == 200, r.text
    changed = r.json()
    assert changed["answers"]["pace"] == "relaxed" and len(changed["days"]) == 4
    fresh = jo_client.post(f"/api/trips/{plan['id']}/generate", json={"fresh": True}).json()
    assert [i["title"] for i in items(fresh)] != [i["title"] for i in items(changed)]
    day = jo_client.post(f"/api/trips/{plan['id']}/days/2026-11-10/regenerate").json()
    assert day["issues"] == []


# ---- Editing --------------------------------------------------------------------------------------------------

def test_edit_items(jo_client, plan, db):
    first = next(i for i in items(plan, "2026-11-10") if i["kind"] == "activity")
    moved = jo_client.patch(f"/api/items/{first['id']}", json={"day": "2026-11-12", "starts": "15:00"}).json()
    item = next(i for i in items(moved) if i["id"] == first["id"])
    assert (item["day"], item["starts"], item["locked"]) == ("2026-11-12", "15:00", True)
    noted = jo_client.patch(f"/api/items/{first['id']}", json={"notes": "Bring reef-safe sunscreen"}).json()
    assert next(i for i in items(noted) if i["id"] == first["id"])["notes"] == "Bring reef-safe sunscreen"

    mine = jo_client.post(f"/api/trips/{plan['id']}/items",
                          json={"day": "2026-11-11", "starts": "17:00", "ends": "18:00", "title": "Call home"})
    assert mine.status_code == 201
    call = next(i for i in items(mine.json()) if i["title"] == "Call home")
    assert (call["added_by"], call["locked"]) == ("you", True)
    after = jo_client.delete(f"/api/items/{call['id']}").json()
    assert "Call home" not in [i["title"] for i in items(after)]
    r = jo_client.patch(f"/api/items/{first['id']}", json={"starts": "half ten"})
    assert r.status_code == 422


def test_alternatives_and_swap(jo_client, plan):
    target = next(i for i in items(plan, "2026-11-11") if i["kind"] == "activity")
    options = jo_client.get(f"/api/items/{target['id']}/alternatives").json()
    assert options and all(o["reason"] for o in options)
    swapped = jo_client.post(f"/api/items/{target['id']}/swap", json={"activity_id": options[0]["activity_id"]}).json()
    now_there = next(i for i in items(swapped) if i["id"] == target["id"])
    assert now_there["title"] == options[0]["title"] and now_there["locked"]


def test_choose_another_stay(jo_client, plan):
    choices = jo_client.get(f"/api/trips/{plan['id']}/stays").json()
    assert choices[0]["current"] and all(c["reason"] for c in choices)
    other = next(c for c in choices if not c["current"])
    changed = jo_client.put(f"/api/trips/{plan['id']}/stay", json={"stay_id": other["id"]}).json()
    assert changed["stay"]["name"] == other["name"] and changed["stay"]["chosen_by_you"]


def test_catalogue_for_adding_things(jo_client, plan):
    cat = jo_client.get(f"/api/trips/{plan['id']}/catalogue").json()
    paddle = next(a for a in cat["activities"] if a["name"] == "Stand-up paddleboard lesson")
    assert paddle["bookable"] and paddle["start_times"] == ["09:00", "14:00"]
    assert any(r["vegan"] for r in cat["restaurants"])


# ---- Booking --------------------------------------------------------------------------------------------------

def test_book_an_activity_from_the_plan(jo_client, plan, db, clock):
    paddle_id = activity(db, "Stand-up paddleboard lesson").id
    db.rollback()                                   # end the test's own read before the API writes
    added = jo_client.post(f"/api/trips/{plan['id']}/items",
                           json={"day": "2026-11-10", "starts": "09:00", "activity_id": paddle_id}).json()
    paddle = next(i for i in items(added) if i["title"] == "Stand-up paddleboard lesson")
    assert paddle["bookable"] and paddle["booking"] is None
    held = jo_client.post(f"/api/items/{paddle['id']}/hold")
    assert held.status_code == 201, held.text
    b = held.json()
    assert (b["status"], b["hold_seconds_left"], b["total_cents"]) == ("held", 900, 9000)
    shown = next(i for i in items(jo_client.get(f"/api/trips/{plan['id']}").json()) if i["id"] == paddle["id"])
    assert shown["booking"]["reference"] == b["reference"] and shown["locked"]

    r = jo_client.patch(f"/api/items/{paddle['id']}", json={"starts": "14:00"})
    assert r.status_code == 400 and "Cancel the booking first" in r.json()["detail"]

    clock.advance(minutes=5)
    assert jo_client.post(f"/api/bookings/{b['id']}/confirm").json()["status"] == "confirmed"
    trip = jo_client.get(f"/api/trips/{plan['id']}").json()
    assert trip["totals"]["booked_cents"] == 9000
    quote = jo_client.get(f"/api/bookings/{b['id']}/refund").json()
    assert quote["refund_cents"] == 9000
    done = jo_client.post(f"/api/bookings/{b['id']}/cancel").json()
    assert (done["booking"]["status"], done["refund_cents"]) == ("cancelled", 9000)


def test_book_the_stay_and_a_table(jo_client, plan, db):
    s = jo_client.post(f"/api/trips/{plan['id']}/stay/hold")
    assert s.status_code == 201 and s.json()["kind"] == "stay"
    bayview_id = restaurant(db, "Bayview Kitchen").id
    db.rollback()
    meal = jo_client.post(f"/api/trips/{plan['id']}/items",
                          json={"day": "2026-11-10", "starts": "12:30", "restaurant_id": bayview_id}).json()
    lunch = next(i for i in items(meal) if i["title"] == "Lunch at Bayview Kitchen")
    table = jo_client.post(f"/api/items/{lunch['id']}/hold").json()
    assert (table["kind"], table["total_cents"]) == ("table", 0)
    trip = jo_client.get(f"/api/trips/{plan['id']}").json()
    assert trip["stay"]["booking"]["status"] == "held" and len(trip["bookings"]) == 2


def test_a_lapsed_hold_reads_as_expired(jo_client, plan, clock):
    b = jo_client.post(f"/api/trips/{plan['id']}/stay/hold").json()
    clock.advance(minutes=15)
    trip = jo_client.get(f"/api/trips/{plan['id']}").json()
    assert trip["bookings"][0]["status"] == "expired" and trip["stay"]["booking"] is None
    r = jo_client.post(f"/api/bookings/{b['id']}/confirm")
    assert r.status_code == 400 and "run out" in r.json()["detail"]


def test_fully_booked_is_409(jo_client, client, friend, dest, plan, db):
    paddle_id = activity(db, "Stand-up paddleboard lesson").id
    db.rollback()
    mine = jo_client.post(f"/api/trips/{plan['id']}/items",
                          json={"day": "2026-11-10", "starts": "09:00", "activity_id": paddle_id}).json()
    jo_client.post(f"/api/items/{next(i for i in items(mine) if i['activity_id'] == paddle_id)['id']}/hold")
    log_in(client, "friend@example.test")
    big = client.post("/api/trips", json=body(dest, adults=7, budget_cents=900000)).json()
    theirs = client.post(f"/api/trips/{big['id']}/items",
                         json={"day": "2026-11-10", "starts": "09:00", "activity_id": paddle_id}).json()
    r = client.post(f"/api/items/{next(i for i in items(theirs) if i['activity_id'] == paddle_id)['id']}/hold")
    assert r.status_code == 409 and "Only 6 places left" in r.json()["detail"]


def test_someone_elses_things_look_missing(client, jo, friend, dest):
    log_in(client)
    plan = client.post("/api/trips", json=body(dest)).json()
    item_id = items(plan)[1]["id"]
    booking_id = client.post(f"/api/trips/{plan['id']}/stay/hold").json()["id"]
    log_in(client, "friend@example.test")
    for method, path, payload in (("GET", f"/api/trips/{plan['id']}", None),
                                  ("POST", f"/api/trips/{plan['id']}/generate", {"fresh": True}),
                                  ("PATCH", f"/api/items/{item_id}", {"locked": True}),
                                  ("DELETE", f"/api/items/{item_id}", None),
                                  ("GET", f"/api/items/{item_id}/alternatives", None),
                                  ("POST", f"/api/items/{item_id}/hold", None),
                                  ("POST", f"/api/bookings/{booking_id}/confirm", None),
                                  ("GET", f"/api/bookings/{booking_id}/refund", None)):
        r = client.request(method, path, json=payload)
        assert r.status_code == 404, (method, path, r.text)
    assert client.get("/api/trips").json() == []


def test_docs(client):
    assert client.get("/docs").status_code == 200
    spec = client.get("/openapi.json").json()
    assert {"/api/questions", "/api/trips/{trip_id}", "/api/items/{item_id}/alternatives",
            "/api/items/{item_id}/hold", "/api/bookings/{booking_id}/cancel"} <= set(spec["paths"])
    assert len(spec["paths"]) >= 20
