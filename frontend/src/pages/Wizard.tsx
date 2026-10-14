import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { api, type Plan, type Questions } from "../api";
import { isoDay, money, nextWeight, nightsBetween, plural } from "../format";
import { draftFromPlan, newDraft, people, problem, STEPS, toAnswers, type Draft } from "../questions";
import { Icon, useApp } from "../components/ui";

/** The questionnaire: one question per screen. With a tripId it edits that trip's answers. */
export function Wizard({ tripId }: { tripId?: number }) {
  const { toast, go } = useApp();
  const today = isoDay(new Date());
  const [q, setQ] = useState<Questions | null>(null);
  const [draft, setDraft] = useState<Draft>(() => newDraft(today));
  const [step, setStep] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    api<Questions>("GET", "/api/questions").then(setQ).catch((e) => toast(e.message, true));
    if (tripId) api<Plan>("GET", `/api/trips/${tripId}`).then((p) => setDraft(draftFromPlan(p)))
      .catch((e) => toast(e.message, true));
  }, [tripId, toast]);

  useEffect(() => { heading.current?.focus(); }, [step]);

  if (!q) return <div className="page"><p className="muted">Loading the questions…</p></div>;

  const key = STEPS[step].key;
  const last = step === STEPS.length - 1;
  const set = (change: Partial<Draft>) => { setDraft((d) => ({ ...d, ...change })); setError(""); };

  const forward = async (e: FormEvent) => {
    e.preventDefault();
    const wrong = problem(key, draft, q, tripId ? "0000-00-00" : today);
    if (wrong) { setError(wrong); return; }
    if (!last) { setStep(step + 1); return; }
    setBusy(true);
    try {
      const plan = tripId
        ? await api<Plan>("PATCH", `/api/trips/${tripId}/answers`, toAnswers(draft))
        : await api<Plan>("POST", "/api/trips", toAnswers(draft));
      toast(tripId ? "Answers updated: the plan was rebuilt around anything you'd locked." : "Here's your plan.");
      go(`#/plan/${plan.id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page wizard">
      <form onSubmit={forward} noValidate>
        <div className="progress" aria-label={`Question ${step + 1} of ${STEPS.length}`}>
          {STEPS.map((s, n) => (
            <button key={s.key} type="button" className={n === step ? "tick now" : n < step ? "tick done" : "tick"}
                    disabled={n > step} onClick={() => setStep(n)} aria-label={`Go back to: ${s.question}`} />
          ))}
          <span>{step + 1} of {STEPS.length}</span>
        </div>
        <h1 ref={heading} tabIndex={-1}>{STEPS[step].question}</h1>
        <div className="answer">{renderStep(key, draft, set, q)}</div>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="wizard-nav">
          {step > 0 && (
            <button type="button" className="btn quiet" onClick={() => { setStep(step - 1); setError(""); }}>
              <Icon name="back" /> Back
            </button>
          )}
          <button className="btn primary big" disabled={busy}>
            {last ? (busy ? "Planning…" : tripId ? "Save and replan" : "Build my plan") : "Next"}
          </button>
        </div>
      </form>
    </div>
  );
}

function renderStep(key: string, d: Draft, set: (c: Partial<Draft>) => void, q: Questions): ReactNode {
  switch (key) {
    case "where":
      return (
        <Cards name="where" value={d.destinationId} onPick={(v) => set({ destinationId: v })}
               options={q.destinations.map((c) => ({ value: c.id, label: c.name, note: c.blurb }))} />
      );
    case "when": {
      const nights = nightsBetween(d.start, d.end);
      return (
        <>
          <div className="row">
            <label className="field">Arriving<input type="date" value={d.start} onChange={(e) => set({ start: e.target.value })} /></label>
            <label className="field">Leaving<input type="date" value={d.end} min={d.start} onChange={(e) => set({ end: e.target.value })} /></label>
          </div>
          {nights > 0 && <p className="note">{plural(nights, "night")}. Arrival day is light, and the last day is just for check-out.</p>}
        </>
      );
    }
    case "who":
      return (
        <>
          <Stepper label="Adults" value={d.adults} min={1} max={q.max_adults} onChange={(adults) => set({ adults })} />
          <Stepper label="Children" value={d.children} min={0} max={q.max_children}
                   onChange={(children) => set({ children, youngestAge: children ? d.youngestAge ?? 6 : null })} />
          {d.children > 0 && (
            <Stepper label="Age of the youngest" value={d.youngestAge ?? 6} min={0} max={17}
                     onChange={(youngestAge) => set({ youngestAge })}
                     note="So nothing gets planned that they're too young for." />
          )}
        </>
      );
    case "budget": {
      const nights = Math.max(1, nightsBetween(d.start, d.end));
      const cents = Math.round(Number(d.budgetDollars.replace(/[,\s$]/g, "")) * 100) || 0;
      return (
        <>
          <label className="field big-field">For everything, for everyone (US$)
            <input inputMode="decimal" value={d.budgetDollars} onChange={(e) => set({ budgetDollars: e.target.value })} />
          </label>
          <p className="note">
            {cents > 0 && `That's about ${money(Math.round(cents / people(d) / nights))} a person a night. `}
            It covers the stay, meals, activities and getting around.
          </p>
        </>
      );
    }
    case "interests":
      return (
        <>
          <p className="note">Tap once if you like it, twice if you love it, again to clear.</p>
          <div className="dominoes">
            {q.interests.map((i) => {
              const weight = d.interests[i.key] ?? 0;
              const state = weight === 2 ? "love it" : weight === 1 ? "like it" : "not picked";
              return (
                <button key={i.key} type="button" className={`domino w${weight}`} aria-label={`${i.label}: ${state}`}
                        onClick={() => {
                          const w = nextWeight(d.interests[i.key]);
                          const interests = { ...d.interests };
                          if (w) interests[i.key] = w; else delete interests[i.key];
                          set({ interests });
                        }}>
                  <span className="domino-top">{i.label}</span>
                  <span className="domino-pips" aria-hidden="true"><i /><i /></span>
                  <span className="domino-state" aria-hidden="true">{weight === 2 ? "Love" : weight === 1 ? "Like" : ""}</span>
                </button>
              );
            })}
          </div>
        </>
      );
    case "pace":
      return (
        <>
          <Cards name="pace" value={d.pace} onPick={(pace) => set({ pace })}
                 options={q.paces.map((p) => ({ value: p.key, label: p.label.split(":")[0], note: p.label.split(":")[1]?.trim() }))} />
          <h2 className="sub">And mornings?</h2>
          <Chips name="day" value={d.dayStart} onPick={(dayStart) => set({ dayStart })}
                 options={q.day_starts.map((s) => ({ value: s.key, label: s.label }))} />
        </>
      );
    case "stay":
      return (
        <Cards name="stay" value={d.stayStyle} onPick={(stayStyle) => set({ stayStyle })}
               options={q.stay_styles.map((s) => ({ value: s.key, label: s.label }))} />
      );
    case "food":
      return (
        <>
          <Cards name="dining" value={d.diningStyle} onPick={(diningStyle) => set({ diningStyle })}
                 options={q.dining_styles.map((s) => ({ value: s.key, label: s.label }))} />
          <h2 className="sub">Any food needs?</h2>
          <div className="checks">
            {q.diets.map((x) => (
              <label key={x.key} className="check">
                <input type="checkbox" checked={d.diets.includes(x.key)}
                       onChange={(e) => set({ diets: e.target.checked ? [...d.diets, x.key] : d.diets.filter((y) => y !== x.key) })} />
                {x.label}
              </label>
            ))}
          </div>
        </>
      );
    case "around":
      return (
        <>
          <Cards name="transport" value={d.transport} onPick={(transport) => set({ transport })}
                 options={q.transport.map((t) => ({ value: t.key, label: t.label }))} />
          <label className="check roomy">
            <input type="checkbox" checked={d.stepFree} onChange={(e) => set({ stepFree: e.target.checked })} />
            Someone needs step-free access (a wheelchair or a pushchair)
          </label>
        </>
      );
    default: {
      const country = q.destinations.find((c) => c.id === d.destinationId)?.name ?? "";
      const loves = q.interests.filter((i) => d.interests[i.key] === 2).map((i) => i.label.toLowerCase());
      return (
        <>
          <label className="field big-field">Trip name
            <input value={d.title} maxLength={100} placeholder={`${country} week`} onChange={(e) => set({ title: e.target.value })} />
          </label>
          <p className="note">
            {country}, {plural(nightsBetween(d.start, d.end), "night")}, {plural(people(d), "person", "people")}
            {loves.length ? `, loving ${loves.join(", ")}` : ""}. You can change any of this later.
          </p>
        </>
      );
    }
  }
}

interface Option<T> { value: T; label: string; note?: string }

function Cards<T extends string | number>({ name, value, options, onPick }:
  { name: string; value: T | null; options: Option<T>[]; onPick: (v: T) => void }) {
  return (
    <div className="cards" role="radiogroup" aria-label={name}>
      {options.map((o) => (
        <label key={String(o.value)} className={o.value === value ? "pick on" : "pick"}>
          <input type="radio" name={name} checked={o.value === value} onChange={() => onPick(o.value)} />
          <strong>{o.label}</strong>
          {o.note && <span>{o.note}</span>}
        </label>
      ))}
    </div>
  );
}

function Chips({ name, value, options, onPick }:
  { name: string; value: string; options: Option<string>[]; onPick: (v: string) => void }) {
  return (
    <div className="chips" role="radiogroup" aria-label={name}>
      {options.map((o) => (
        <label key={o.value} className={o.value === value ? "chip on" : "chip"}>
          <input type="radio" name={name} checked={o.value === value} onChange={() => onPick(o.value)} />
          {o.label}
        </label>
      ))}
    </div>
  );
}

function Stepper({ label, value, min, max, onChange, note }:
  { label: string; value: number; min: number; max: number; onChange: (n: number) => void; note?: string }) {
  return (
    <div className="stepper">
      <span className="stepper-label">{label}{note && <small>{note}</small>}</span>
      <button type="button" aria-label={`Fewer: ${label}`} disabled={value <= min} onClick={() => onChange(value - 1)}>−</button>
      <output aria-live="polite" aria-label={label}>{value}</output>
      <button type="button" aria-label={`More: ${label}`} disabled={value >= max} onClick={() => onChange(value + 1)}>+</button>
    </div>
  );
}
