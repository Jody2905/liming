import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, type Alternative, type Catalogue, type Item } from "../api";
import { dayLabel, duration, money } from "../format";
import { useApp } from "./ui";

/** A modal <dialog> that opens itself, and closes on Escape or the close button. */
function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    d?.showModal();
    return () => d?.close();
  }, []);
  return (
    <dialog ref={ref} className="sheet" aria-labelledby="sheet-title" onCancel={(e) => { e.preventDefault(); onClose(); }}>
      <div className="sheet-head">
        <h2 id="sheet-title">{title}</h2>
        <button className="btn quiet small" onClick={onClose}>Close</button>
      </div>
      {children}
    </dialog>
  );
}

export function Alternatives({ item, onClose, onPick }:
  { item: Item; onClose: () => void; onPick: (body: { activity_id?: number; restaurant_id?: number }) => void }) {
  const { toast } = useApp();
  const [options, setOptions] = useState<Alternative[] | null>(null);
  useEffect(() => {
    api<Alternative[]>("GET", `/api/items/${item.id}/alternatives`).then(setOptions).catch((e) => {
      toast(e.message, true);
      onClose();
    });
  }, [item.id, toast, onClose]);
  return (
    <Modal title={`Instead of ${item.title}`} onClose={onClose}>
      {options === null ? <p className="muted">Finding what else fits…</p> : options.length === 0 ? (
        <p className="muted">Nothing else fits this gap. Try moving it, or redo the day.</p>
      ) : (
        <>
          <p className="muted">These fit the same gap, best first.</p>
          <ul className="options">
            {options.map((o) => (
              <li key={`${o.activity_id}-${o.restaurant_id}`}>
                <div>
                  <strong>{o.title}</strong>
                  <span className="muted">{o.starts} to {o.ends}{o.cost_cents ? `, about ${money(o.cost_cents)}` : ", free"}</span>
                  <span className="why">{o.reason}</span>
                </div>
                <button className="btn small primary"
                        onClick={() => onPick(o.activity_id ? { activity_id: o.activity_id } : { restaurant_id: o.restaurant_id! })}>
                  Swap in
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </Modal>
  );
}

export function MoveItem({ item, days, onClose, onMove }:
  { item: Item; days: string[]; onClose: () => void; onMove: (body: { day: string; starts: string }) => void }) {
  const [day, setDay] = useState(item.day);
  const [starts, setStarts] = useState(item.starts);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    onMove({ day, starts });
  };
  return (
    <Modal title={`Move ${item.title}`} onClose={onClose}>
      <form onSubmit={submit}>
        <div className="row">
          <label className="field">Day
            <select value={day} onChange={(e) => setDay(e.target.value)}>
              {days.map((d) => <option key={d} value={d}>{dayLabel(d)}</option>)}
            </select>
          </label>
          <label className="field">Starts<input type="time" value={starts} onChange={(e) => setStarts(e.target.value)} required /></label>
        </div>
        <p className="muted">It keeps its length and gets locked, so rebuilding the plan won't undo the move.
          If the new time doesn't work (closed, or not enough time to get there), the plan will say so.</p>
        <div className="actions"><button className="btn primary">Move it</button></div>
      </form>
    </Modal>
  );
}

type AddBody = { day: string; starts: string; ends?: string; title?: string; activity_id?: number; restaurant_id?: number;
                 cost_cents?: number };

export function AddToDay({ tripId, day, busy, onAdd }:
  { tripId: number; day: string; busy: boolean; onAdd: (body: AddBody) => void }) {
  const [open, setOpen] = useState(false);
  const [what, setWhat] = useState<"own" | "activity" | "meal">("own");
  const [cat, setCat] = useState<Catalogue | null>(null);
  const [title, setTitle] = useState("");
  const [starts, setStarts] = useState("15:00");
  const [ends, setEnds] = useState("16:00");
  const [pick, setPick] = useState("");
  const { toast } = useApp();

  useEffect(() => {
    if (open && !cat) api<Catalogue>("GET", `/api/trips/${tripId}/catalogue`).then(setCat).catch((e) => toast(e.message, true));
  }, [open, cat, tripId, toast]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (what === "own") onAdd({ day, starts, ends, title });
    else if (what === "activity") onAdd({ day, starts, activity_id: Number(pick) });
    else onAdd({ day, starts, restaurant_id: Number(pick) });
    setTitle("");
    setPick("");
  };

  if (!open) return <button className="btn quiet add-open" onClick={() => setOpen(true)}>+ Add to {dayLabel(day)}</button>;
  return (
    <form className="card add" onSubmit={submit}>
      <div className="chips" role="radiogroup" aria-label="What to add">
        {([["own", "Your own plan"], ["activity", "Something to do"], ["meal", "A meal"]] as const).map(([k, label]) => (
          <label key={k} className={what === k ? "chip on" : "chip"}>
            <input type="radio" name="what" checked={what === k} onChange={() => { setWhat(k); setPick(""); }} />{label}
          </label>
        ))}
      </div>
      {what === "own" ? (
        <label className="field">What<input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={140}
                                          placeholder="Call home, nap, buy souvenirs…" required /></label>
      ) : (
        <label className="field">{what === "activity" ? "Activity" : "Restaurant"}
          <select value={pick} onChange={(e) => setPick(e.target.value)} required>
            <option value="">Choose…</option>
            {what === "activity"
              ? cat?.activities.map((a) => <option key={a.id} value={a.id}>{a.name} ({a.area}, {duration(a.minutes)}{a.start_times.length ? `, at ${a.start_times.join(" or ")}` : ""})</option>)
              : cat?.restaurants.map((r) => <option key={r.id} value={r.id}>{r.name} ({r.cuisine}, {r.area})</option>)}
          </select>
        </label>
      )}
      <div className="row">
        <label className="field">Starts<input type="time" value={starts} onChange={(e) => setStarts(e.target.value)} required /></label>
        {what === "own" && <label className="field">Ends<input type="time" value={ends} onChange={(e) => setEnds(e.target.value)} required /></label>}
      </div>
      <div className="actions">
        <button className="btn primary" disabled={busy}>Add</button>
        <button type="button" className="btn quiet" onClick={() => setOpen(false)}>Done</button>
      </div>
    </form>
  );
}
