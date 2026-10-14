import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Booking, type Item, type Plan, type Refund, type StayChoice } from "../api";
import { countdown, dayLabel, duration, money, nightsBetween, plural } from "../format";
import { Icon, useApp, useBusy } from "../components/ui";
import { AddToDay, Alternatives, MoveItem } from "../components/Editing";

/** One trip's plan: pick a day, read why each stop is there, change anything, book. */
export function PlanPage({ tripId }: { tripId: number }) {
  const { toast, confirm, go } = useApp();
  const [plan, setPlan] = useState<Plan | null>(null);
  const [dayIndex, setDayIndex] = useState(1);
  const [fetchedAt, setFetchedAt] = useState(Date.now());
  const [now, setNow] = useState(Date.now());
  const [busy, run] = useBusy();
  const [swapping, setSwapping] = useState<Item | null>(null);
  const [moving, setMoving] = useState<Item | null>(null);
  const refreshing = useRef(false);

  const show = useCallback((p: Plan) => {
    setPlan(p);
    setFetchedAt(Date.now());
  }, []);
  const reload = useCallback(() => api<Plan>("GET", `/api/trips/${tripId}`).then(show), [tripId, show]);

  useEffect(() => { reload().catch((e) => toast(e.message, true)); }, [reload, toast]);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const secondsLeft = (b: { hold_seconds_left?: number | null }) =>
    (b.hold_seconds_left ?? 0) - (now - fetchedAt) / 1000;

  // When a hold runs out, fetch the plan again so it shows as lapsed
  useEffect(() => {
    if (!plan || refreshing.current) return;
    if (plan.bookings.some((b) => b.status === "held" && secondsLeft(b) <= 0)) {
      refreshing.current = true;
      reload().then(() => toast("A hold ran out, so that space went back on sale.", true))
        .finally(() => { refreshing.current = false; });
    }
  });

  if (!plan) return <div className="page"><p className="muted">Loading the plan…</p></div>;

  const day = plan.days[Math.min(dayIndex, plan.days.length - 1)];
  const edit = (method: "POST" | "PATCH" | "DELETE" | "PUT", path: string, body?: unknown, done?: string) =>
    run(async () => {
      show(await api<Plan>(method, path, body));
      if (done) toast(done);
    });

  const somethingDifferent = () => edit("POST", `/api/trips/${tripId}/generate`, { fresh: true },
    "Something different: everything you locked or added stayed put.");
  const deleteTrip = async () => {
    if (!(await confirm("Delete this trip?", [`${plan.title} and its plan will be gone for good.`], "Delete trip", "Keep it")))
      return;
    run(async () => {
      await api("DELETE", `/api/trips/${tripId}`);
      toast("Trip deleted.");
      go("#/trips");
    });
  };

  const people = plan.answers.adults + plan.answers.children;
  return (
    <div className="page plan">
      <header className="plan-head">
        <div>
          <a className="back" href="#/trips"><Icon name="back" /> Your trips</a>
          <p className="country">{plan.destination.name}</p>
          <h1>{plan.title}</h1>
          <p className="muted">
            {dayLabel(plan.answers.start_date)} to {dayLabel(plan.answers.end_date)},{" "}
            {plural(nightsBetween(plan.answers.start_date, plan.answers.end_date), "night")},{" "}
            {plural(people, "person", "people")}, {plan.answers.pace} pace
          </p>
        </div>
        <div className="head-actions">
          <button className="btn" onClick={somethingDifferent} disabled={busy}><Icon name="redo" /> Something different</button>
          <a className="btn quiet" href={`#/plan/${tripId}/answers`}>Change answers</a>
        </div>
      </header>

      {plan.issues.length > 0 && (
        <section className="issues" aria-label="Things to check">
          <h2><Icon name="warn" /> Worth a look</h2>
          <ul>{plan.issues.map((i) => <li key={`${i.item_id}-${i.message}`}>{i.day ? `${dayLabel(i.day)}: ` : ""}{i.message}</li>)}</ul>
        </section>
      )}

      <div className="plan-grid">
        <section aria-label="Day by day">
          <div className="day-tabs" role="tablist" aria-label="Days">
            {plan.days.map((d, n) => (
              <button key={d.date} role="tab" aria-selected={d.date === day.date} className="day-tab"
                      onClick={() => setDayIndex(n)}>
                <span>Day {n + 1}</span>{dayLabel(d.date)}
              </button>
            ))}
          </div>
          <div role="tabpanel" aria-label={dayLabel(day.date)}>
            <ol className="timeline big">
              {day.items.map((item, n) => (
                <li key={item.id}>
                  {item.travel_minutes > 0 && (
                    <div className="hop">
                      {duration(item.travel_minutes)} by {transportWord(plan.answers.transport)}
                      {n === 0 || day.items.slice(0, n).every((i) => i.kind === "stay") ? ` from ${plan.stay?.name ?? "your stay"}` : ""}
                    </div>
                  )}
                  <ItemCard item={item} busy={busy} secondsLeft={item.booking ? secondsLeft(item.booking) : 0}
                            onLock={() => edit("PATCH", `/api/items/${item.id}`, { locked: !item.locked })}
                            onRemove={() => edit("DELETE", `/api/items/${item.id}`, undefined, `Removed ${item.title}.`)}
                            onSwap={() => setSwapping(item)} onMove={() => setMoving(item)}
                            onHold={() => run(async () => {
                              const b = await api<Booking>("POST", `/api/items/${item.id}/hold`);
                              await reload();
                              toast(`Held until ${b.held_until.slice(11, 16)}. Confirm it to book.`);
                            })}
                            onConfirm={(id) => confirmBooking(id)} onCancel={(id) => cancelBooking(id)} />
                </li>
              ))}
            </ol>
            {day.items.every((i) => i.kind === "stay") && day.date !== plan.answers.end_date && (
              <p className="muted free">Nothing planned: a free day.</p>
            )}
            <div className="day-actions">
              <button className="btn quiet" disabled={busy}
                      onClick={() => edit("POST", `/api/trips/${tripId}/days/${day.date}/regenerate`, undefined,
                                          `${dayLabel(day.date)} redone. Locked things stayed.`)}>
                <Icon name="redo" /> Redo this day
              </button>
            </div>
            <AddToDay tripId={tripId} day={day.date} busy={busy}
                      onAdd={(body) => edit("POST", `/api/trips/${tripId}/items`, body, "Added to your plan.")} />
          </div>
        </section>

        <aside className="side">
          <BudgetCard plan={plan} />
          <StayCard plan={plan} busy={busy} secondsLeft={plan.stay?.booking ? secondsLeft(plan.stay.booking) : 0}
                    onHold={() => run(async () => {
                      await api<Booking>("POST", `/api/trips/${tripId}/stay/hold`);
                      await reload();
                      toast("Your stay is held for 15 minutes.");
                    })}
                    onConfirm={(id) => confirmBooking(id)} onCancel={(id) => cancelBooking(id)}
                    onChoose={(stayId) => edit("PUT", `/api/trips/${tripId}/stay`, { stay_id: stayId },
                                               "Stay changed. Use Something different to replan around it.")} />
          <section className="card">
            <h2>Your bookings</h2>
            {plan.bookings.length === 0 ? <p className="muted">Nothing booked yet. Use Book on a tour or a meal, or book the stay above.</p> : (
              <ul className="bookings">
                {plan.bookings.map((b) => (
                  <li key={b.id} className={`booking ${b.status}`}>
                    <strong>{b.title}</strong>
                    <span>{b.reference}. {b.kind === "stay" ? `${dayLabel(b.start_date)} to ${dayLabel(b.end_date)}` : `${dayLabel(b.start_date)}, ${b.starts_at.slice(11, 16)}`}</span>
                    <span className="state">{statusWords(b, secondsLeft(b))}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <button className="btn danger" onClick={deleteTrip} disabled={busy}>Delete this trip</button>
        </aside>
      </div>

      {swapping && (
        <Alternatives item={swapping} onClose={() => setSwapping(null)}
                      onPick={(body) => { setSwapping(null); edit("POST", `/api/items/${swapping.id}/swap`, body, "Swapped. The new pick is locked."); }} />
      )}
      {moving && (
        <MoveItem item={moving} days={plan.days.map((d) => d.date)} onClose={() => setMoving(null)}
                  onMove={(body) => { setMoving(null); edit("PATCH", `/api/items/${moving.id}`, body, "Moved and locked."); }} />
      )}
    </div>
  );

  async function confirmBooking(id: number) {
    const b = plan!.bookings.find((x) => x.id === id);
    const lines = b && b.total_cents ? [`Total ${money(b.total_cents)}.`, "This is a demo, so no payment is taken."]
      : ["There's no charge to book a table."];
    if (!(await confirm(`Confirm ${b?.title ?? "this booking"}?`, lines, "Confirm booking", "Not yet"))) return;
    run(async () => {
      try {
        const done = await api<Booking>("POST", `/api/bookings/${id}/confirm`);
        toast(`Booked. Your reference is ${done.reference}.`);
      } finally {
        await reload();
      }
    });
  }

  async function cancelBooking(id: number) {
    const b = plan!.bookings.find((x) => x.id === id);
    run(async () => {
      const held = b?.status === "held";
      const quote = held ? null : await api<Refund>("GET", `/api/bookings/${id}/refund`);
      const lines = quote ? [`You'd get back ${money(quote.refund_cents)} of ${money(b?.total_cents ?? 0)}.`, quote.reason]
        : ["Nothing has been charged for a hold."];
      if (!(await confirm(held ? "Let this hold go?" : `Cancel ${b?.title}?`, lines, held ? "Let it go" : "Cancel booking", "Keep it")))
        return;
      await api("POST", `/api/bookings/${id}/cancel`);
      await reload();
      toast(held ? "Let go. The space is back on sale." : "Cancelled.");
    });
  }
}

function transportWord(t: string) {
  return t === "hire_car" ? "car" : t === "bus" ? "bus" : "taxi";
}

function statusWords(b: { status: string; refund_cents: number }, seconds: number) {
  if (b.status === "held") return `On hold, ${countdown(seconds)} left`;
  if (b.status === "confirmed") return "Booked";
  if (b.status === "cancelled") return b.refund_cents ? `Cancelled, ${money(b.refund_cents)} refunded` : "Cancelled";
  return "Hold ran out";
}

interface CardProps {
  item: Item;
  busy: boolean;
  secondsLeft: number;
  onLock: () => void;
  onRemove: () => void;
  onSwap: () => void;
  onMove: () => void;
  onHold: () => void;
  onConfirm: (bookingId: number) => void;
  onCancel: (bookingId: number) => void;
}

function ItemCard({ item, busy, secondsLeft, onLock, onRemove, onSwap, onMove, onHold, onConfirm, onCancel }: CardProps) {
  const booked = item.booking;
  const canEdit = item.kind !== "stay" && !booked;
  return (
    <article className={`stop kind-${item.kind}${item.locked ? " locked" : ""}${booked ? " booked" : ""}`}>
      <span className="time">{item.starts}<small>{item.ends}</small></span>
      <div className="stop-body">
        <h3>{item.title}</h3>
        <p className="why">{item.reason}</p>
        {item.notes && <p className="notes">{item.notes}</p>}
        <p className="meta">
          {item.area && <span>{item.area}</span>}
          {item.cost_cents > 0 && <span>about {money(item.cost_cents)}</span>}
          {item.locked && !booked && <span className="tag">Locked</span>}
          {booked && <span className="tag booked">{booked.status === "held" ? `On hold, ${countdown(secondsLeft)} left` : `Booked ${booked.reference}`}</span>}
        </p>
        <div className="item-actions">
          {booked?.status === "held" && <button className="btn small primary" disabled={busy} onClick={() => onConfirm(booked.id)}><Icon name="check" /> Confirm</button>}
          {booked && <button className="btn small quiet" disabled={busy} onClick={() => onCancel(booked.id)}>{booked.status === "held" ? "Let it go" : "Cancel booking"}</button>}
          {!booked && item.bookable && <button className="btn small" disabled={busy} onClick={onHold}><Icon name="ticket" /> {item.kind === "meal" ? "Book a table" : "Book"}</button>}
          {canEdit && (
            <>
              <button className="icon-btn" disabled={busy} onClick={onLock} aria-pressed={item.locked}
                      title={item.locked ? "Unlock" : "Lock: keep this when the plan is rebuilt"}>
                <Icon name={item.locked ? "lock" : "unlock"} label={item.locked ? `Unlock ${item.title}` : `Lock ${item.title}`} />
              </button>
              {(item.kind === "activity" || item.kind === "meal") && (
                <button className="icon-btn" disabled={busy} onClick={onSwap} title="Swap for something else">
                  <Icon name="swap" label={`Swap ${item.title}`} />
                </button>
              )}
              <button className="icon-btn" disabled={busy} onClick={onMove} title="Move to another day or time">
                <Icon name="move" label={`Move ${item.title}`} />
              </button>
              <button className="icon-btn" disabled={busy} onClick={onRemove} title="Remove">
                <Icon name="bin" label={`Remove ${item.title}`} />
              </button>
            </>
          )}
        </div>
      </div>
    </article>
  );
}

function BudgetCard({ plan }: { plan: Plan }) {
  const t = plan.totals;
  const parts = [
    { key: "stay", label: "Stay", cents: t.stay_cents },
    { key: "activities", label: "Things to do", cents: t.activities_cents },
    { key: "meals", label: "Meals", cents: t.meals_cents },
    { key: "transport", label: "Getting around", cents: t.transport_cents },
  ];
  const scale = Math.max(t.budget_cents, t.total_cents);
  const over = t.left_cents < 0;
  return (
    <section className="card budget" aria-labelledby="budget-title">
      <h2 id="budget-title">Budget</h2>
      <p className="big-number">{over ? `${money(-t.left_cents)} over` : `${money(t.left_cents)} to spare`}</p>
      <p className="muted">About {money(t.total_cents)} of {money(t.budget_cents)}</p>
      <div className="bar" role="img" aria-label={parts.map((p) => `${p.label} ${money(p.cents)}`).join(", ")}>
        {parts.map((p) => <span key={p.key} className={`seg ${p.key}`} style={{ width: `${(p.cents / scale) * 100}%` }} />)}
      </div>
      <ul className="key">
        {parts.map((p) => <li key={p.key}><i className={`seg ${p.key}`} />{p.label} <b>{money(p.cents)}</b></li>)}
      </ul>
      {t.booked_cents > 0 && <p className="muted">Booked so far: {money(t.booked_cents)}</p>}
    </section>
  );
}

interface StayProps {
  plan: Plan;
  busy: boolean;
  secondsLeft: number;
  onHold: () => void;
  onConfirm: (id: number) => void;
  onCancel: (id: number) => void;
  onChoose: (stayId: number) => void;
}

function StayCard({ plan, busy, secondsLeft, onHold, onConfirm, onCancel, onChoose }: StayProps) {
  const [choices, setChoices] = useState<StayChoice[] | null>(null);
  const { toast } = useApp();
  const stay = plan.stay;
  if (!stay) return null;
  const booking = stay.booking;
  const open = () => api<StayChoice[]>("GET", `/api/trips/${plan.id}/stays`).then(setChoices)
    .catch((e) => toast(e.message, true));
  return (
    <section className="card stay" aria-labelledby="stay-title">
      <h2 id="stay-title">Where you're staying</h2>
      <h3>{stay.name}</h3>
      <p className="muted">{stay.area}. {money(stay.nightly_cents)} a night{stay.chosen_by_you ? ". You chose this." : ""}</p>
      <p className="why">{stay.reason}</p>
      <div className="item-actions">
        {booking?.status === "held" && <button className="btn small primary" disabled={busy} onClick={() => onConfirm(booking.id)}><Icon name="check" /> Confirm stay</button>}
        {booking && <span className="tag booked">{booking.status === "held" ? `On hold, ${countdown(secondsLeft)} left` : `Booked ${booking.reference}`}</span>}
        {booking && <button className="btn small quiet" disabled={busy} onClick={() => onCancel(booking.id)}>{booking.status === "held" ? "Let it go" : "Cancel"}</button>}
        {!booking && <button className="btn small" disabled={busy} onClick={onHold}><Icon name="ticket" /> Book the stay</button>}
        {!booking && <button className="btn small quiet" disabled={busy} onClick={open}>Other places</button>}
      </div>
      {choices && !booking && (
        <ul className="choices">
          {choices.filter((c) => !c.current).map((c) => (
            <li key={c.id}>
              <strong>{c.name}</strong>
              <span className="muted">{c.area}. {money(c.total_cents)} in all.</span>
              <span className="why">{c.reason}</span>
              <button className="btn small" disabled={busy} onClick={() => { setChoices(null); onChoose(c.id); }}>Stay here</button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
