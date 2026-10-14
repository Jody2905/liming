import os
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from liming import services  # noqa: E402
from liming.catalogue import seed_catalogue  # noqa: E402
from liming.db import create_tables, make_engine, session_factory  # noqa: E402
from liming.models import Activity, Base, Restaurant, Stay  # noqa: E402

PASSWORD = "correct-horse-battery"
NOW = datetime(2026, 11, 2, 10, 0)            # "now" in every test: Monday 2 November 2026, 10:00
TEST_DATABASE_URL = os.environ.get("LIMING_TEST_DATABASE_URL")


def d(day, month=11):
    return date(2026, month, day)


@pytest.fixture
def db_url(tmp_path):
    if not TEST_DATABASE_URL:
        return f"sqlite:///{tmp_path / 'test.db'}"
    engine = make_engine(TEST_DATABASE_URL)
    Base.metadata.drop_all(engine)
    with engine.begin() as c:
        c.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    engine.dispose()
    return TEST_DATABASE_URL


@pytest.fixture
def engine(db_url):
    engine = make_engine(db_url)
    create_tables(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def Session(engine):
    return session_factory(engine)


@pytest.fixture
def db(Session):
    session = Session()
    yield session
    session.close()


@pytest.fixture
def dest(db):
    """{country code: destination id} for the demo catalogue."""
    found = seed_catalogue(db)
    db.commit()
    return {code: d.id for code, d in found.items()}


@pytest.fixture
def jo(db):
    return services.create_user(db, "jo@example.test", "Jo", PASSWORD, now=NOW)


@pytest.fixture
def friend(db):
    return services.create_user(db, "friend@example.test", "Kemar", PASSWORD, now=NOW)


def answers(dest, **changes):
    """A sensible set of answers: two adults, St Vincent, Mon 9 to Sat 14 November, US$4,000."""
    base = dict(title="Island week", destination_id=dest["VC"], start_date=d(9), end_date=d(14), adults=2,
                children=0, youngest_age=None, budget_cents=400000, pace="balanced", stay_style="hotel",
                dining_style="mix", transport="taxi", day_start="normal", step_free=False,
                interests={"beaches": 2, "nature": 1}, diets=set())
    base.update(changes)
    return base


@pytest.fixture
def trip(db, jo, dest):
    return services.create_trip(db, jo, now=NOW, **answers(dest))


def activity(db, name):
    return db.scalar(select(Activity).where(Activity.name == name))


def restaurant(db, name):
    return db.scalar(select(Restaurant).where(Restaurant.name == name))


def stay(db, name):
    return db.scalar(select(Stay).where(Stay.name == name))
