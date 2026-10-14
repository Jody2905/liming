"""Command line.

  python -m liming demo                 three travellers, three plans, then some editing (throwaway database)
  python -m liming init-demo [--reset]  build the database with migrations and add demo accounts and a trip
"""

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from . import demo
from .db import database_url

DEMO_PASSWORD = "Liming-2026-demo"  # noqa: S105 - printed for people to use
ROOT = Path(__file__).resolve().parent.parent


def migrate(url):
    """Bring the database up to the latest migration."""
    from alembic import command
    from alembic.config import Config
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.attributes["url"] = url
    command.upgrade(cfg, "head")


def init_demo(url, reset=False, today=None):
    from sqlalchemy import func, inspect, select

    from . import services
    from .catalogue import seed_catalogue
    from .db import make_engine, session_factory
    from .models import Base, Destination

    engine = make_engine(url)
    if inspect(engine).has_table("destinations"):
        with engine.connect() as c:
            has_data = c.execute(select(func.count()).select_from(Destination)).scalar() > 0
        if has_data and not reset:
            engine.dispose()
            print("The database already has data. Use --reset to start again (this deletes it).", file=sys.stderr)
            return 1
        Base.metadata.drop_all(engine)
        with engine.begin() as c:
            c.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    engine.dispose()
    migrate(url)

    today = today or date.today()
    now = datetime.combine(today, datetime.min.time()).replace(hour=9)
    engine = make_engine(url)
    db = session_factory(engine)()
    dests = seed_catalogue(db)
    db.commit()
    jo = services.create_user(db, "jo@example.test", "Jo", DEMO_PASSWORD, now=now)
    services.create_user(db, "kemar@example.test", "Kemar", DEMO_PASSWORD, now=now)
    start = today + timedelta(days=21)
    services.create_trip(db, jo, now=now, title="Beach and rainforest week", destination_id=dests["VC"].id,
                         start_date=start, end_date=start + timedelta(days=5), adults=2, budget_cents=400000,
                         pace="balanced", stay_style="hotel", dining_style="mix", transport="taxi",
                         interests={"beaches": 2, "nature": 2, "hiking": 1})
    db.close()
    engine.dispose()

    print("Database ready (built with Alembic migrations).\n")
    print(f"Demo logins (password for both: {DEMO_PASSWORD})")
    print("  jo@example.test      has a St Vincent trip already planned")
    print("  kemar@example.test   no trips yet: answer the questions to make one")
    print("\nCatalogue: 5 countries, invented businesses at real places.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="liming")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="three travellers, three plans, then some editing")
    i = sub.add_parser("init-demo", help="build the database and add demo data")
    i.add_argument("--db", help="SQLite file or database URL (default: $LIMING_DATABASE_URL or liming.db)")
    i.add_argument("--reset", action="store_true", help="delete existing data first")
    args = parser.parse_args(argv)
    if args.command == "demo":
        demo.run()
        return 0
    return init_demo(database_url(args.db), args.reset)


if __name__ == "__main__":
    sys.exit(main())
