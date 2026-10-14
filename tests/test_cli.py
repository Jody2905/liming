from datetime import date

from sqlalchemy import func, select

from liming import __main__ as cli
from liming import demo, services
from liming.db import make_engine, session_factory
from liming.models import Trip


def test_demo_runs_and_every_refusal_happens():
    lines = []
    demo.run(out=lines.append)
    text = "\n".join(lines)
    assert "!!" not in text
    assert text.count("REFUSED") == 3
    assert "[locked]" in text and "WARNING: Kingstown market morning is open 07:00 to 14:00." in text
    assert "Oistins Friday fish fry" in text                    # Kemar's Friday night


def test_init_demo_builds_a_usable_database(tmp_path, capsys):
    url = f"sqlite:///{tmp_path / 'liming.db'}"
    assert cli.init_demo(url, today=date(2026, 11, 2)) == 0
    engine = make_engine(url)
    db = session_factory(engine)()
    try:
        jo = services.authenticate(db, "jo@example.test", cli.DEMO_PASSWORD)
        [trip] = services.trips_for(db, jo)
        view = services.plan_for(db, jo, trip.id)
        assert trip.start_date == date(2026, 11, 23) and view.issues == []
        assert sum(len(items) for items in view.days.values()) > 10
    finally:
        db.close()
        engine.dispose()
    assert cli.init_demo(url, today=date(2026, 11, 2)) == 1                   # won't wipe data by accident
    assert "--reset" in capsys.readouterr().err
    assert cli.init_demo(url, reset=True, today=date(2026, 11, 2)) == 0
    engine = make_engine(url)
    with engine.connect() as c:
        assert c.execute(select(func.count()).select_from(Trip)).scalar() == 1
    engine.dispose()
