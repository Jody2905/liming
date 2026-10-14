# Liming

*Liming (Caribbean English): relaxing, hanging out, taking it easy.*

A Caribbean trip planner. You answer a few questions (where, when, who's coming, budget,
pace, the kind of stay, how you like to eat, what you enjoy) and Liming builds a timed,
day-by-day itinerary, with a reason for every choice. Then it's yours to change: lock what
you love, swap anything for a suggested alternative, move things, add your own, and
regenerate the rest.

> Place names are real; every business and price is invented demo data. No payments are taken.

**Status:** Phase 1 of 4: the planner engine and plan editing. (Booking, the API, the React
front end, then PostgreSQL + CI come next.)

## Run it

```
py -m pip install -r requirements-dev.txt
py -m pytest                 # the test suite
py -m liming demo            # three travellers, three very different plans, then some editing
py -m liming init-demo       # build liming.db with Alembic and add demo accounts and a trip
```

Demo logins: `jo@example.test` and `kemar@example.test`, password `Liming-2026-demo`.

## How the planner decides

It's rule-based, not random and not AI: the same answers always give the same plan, and
every item says why it's there ("You love hiking. A local favourite. About 15 minutes from
Indian Bay Inn.").

1. **A place to stay.** It has to sleep everyone (in up to four rooms), suit children or
   step-free needs, and fit the budget. Among those, the best matches the style you asked
   for, costs a sensible share of the budget, and is close to the things you'd enjoy.
2. **The budget.** It's split into the stay, an estimate for meals and getting around, and
   what's left for activities. With a tight budget, the plan sticks to free things.
3. **Each day, slot by slot**: morning, lunch, afternoon, dinner, evening. Each slot takes
   the best-scoring option that:
   - is open that day and at that time, including tours that only run at set times
   - fits, with real travel time from the previous stop (worked out from distance, slower
     by bus, plus an hour for a ferry)
   - suits the youngest traveller and any step-free needs
   - suits every food need (vegetarian, vegan, gluten-free) and the dining budget
   - hasn't been done already, and is affordable

   Scores favour what you love over what you like, local favourites, and places near the
   last stop, so each day stays in one part of the island. Doing the same kind of thing
   every day costs points.
4. **Sensible days.** Pace sets how full the days are. Arrival day is light and the
   departure day just has check-out. A Friday fish fry *is* dinner. Something you love
   gets an early start if it needs one. Trips to another island are daytime only, back
   before the last ferry.

## Editing

- **Lock** an item, then **regenerate** (or ask for **something different**): locked items
  and anything you added stay put, and the rest is rebuilt around them.
- **Swap**: see what else would fit the same gap, best first, each with its reason.
- **Move** or **retime** anything; **add** your own plans, a catalogue activity or a meal.
- **Redo one day** without touching the others.
- **Choose another stay**; check-in and check-out follow it.

You're in charge, so edits are never refused for being a bad idea. Moving the market to its
closed hours is allowed, and the plan then shows a warning: *"Kingstown market morning is
open 07:00 to 14:00."*

## Tests

- **150 random travellers.** Random dates, group sizes, children's ages, budgets, paces,
  food needs and access needs, across all five countries. Every plan must pass every rule
  (no overlaps, travel time respected, nothing closed, no one too young, food needs met, no
  repeats, no one stranded on another island, lunch and dinner every day).
- Tests that answers really shape the plan, that editing keeps your changes, and that two
  regenerations at once don't double the plan.
- Each key rule was checked by breaking it on purpose and watching a test fail.
- A catalogue check: every tour's set start times fit its opening hours.
- Runs on SQLite and PostgreSQL.

## Built with

Python 3.11+, SQLAlchemy 2, Alembic, pytest. FastAPI and React + TypeScript in later phases.
