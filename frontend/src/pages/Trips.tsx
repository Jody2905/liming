import { useEffect, useState } from "react";
import { api, type TripSummary } from "../api";
import { dayLabel, nightsBetween, plural } from "../format";
import { useApp } from "../components/ui";

export function Trips() {
  const { toast } = useApp();
  const [trips, setTrips] = useState<TripSummary[] | null>(null);

  useEffect(() => {
    api<TripSummary[]>("GET", "/api/trips").then(setTrips).catch((e) => toast(e.message, true));
  }, [toast]);

  if (trips === null) return <div className="page"><p className="muted">Loading your trips…</p></div>;
  return (
    <div className="page">
      <div className="page-head">
        <h1>Your trips</h1>
        <a className="btn primary" href="#/new">Plan a trip</a>
      </div>
      {trips.length === 0 ? (
        <div className="card empty">
          <h2>Nothing planned yet</h2>
          <p>Answer ten questions and Liming lays out every day for you.</p>
          <a className="btn primary" href="#/new">Plan your first trip</a>
        </div>
      ) : (
        <ul className="signs">
          {trips.map((t) => (
            <li key={t.id}>
              <a className="sign trip" href={`#/plan/${t.id}`}>
                <h2>{t.destination.name}</h2>
                <p className="what">{t.title}</p>
                <p>{dayLabel(t.start_date)} to {dayLabel(t.end_date)}, {plural(nightsBetween(t.start_date, t.end_date), "night")}</p>
                <p>{plural(t.people, "person", "people")}{t.stay ? `, staying at ${t.stay}` : ""}</p>
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
