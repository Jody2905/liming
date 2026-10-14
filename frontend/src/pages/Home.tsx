import { useEffect, useState } from "react";
import { api, type Me, type Questions } from "../api";
import { useApp, useBusy } from "../components/ui";

const SAMPLE = [
  { time: "09:15", title: "Indian Bay snorkel", why: "You love beaches and swimming. Close to Indian Bay Inn.", travel: "" },
  { time: "12:15", title: "Lunch at Cobblestone Café", why: "Has vegetarian options. Close to the bay.", travel: "5 min" },
  { time: "13:45", title: "Botanic Gardens", why: "You love nature and gardens. The oldest in the Americas.", travel: "15 min" },
  { time: "19:00", title: "Dinner at Bayview Kitchen", why: "Vincentian food on the way back to your stay.", travel: "20 min" },
];

export function Home() {
  const { me, setMe, go } = useApp();
  const [countries, setCountries] = useState<Questions["destinations"]>([]);
  const [busy, run] = useBusy();

  useEffect(() => {
    api<Questions>("GET", "/api/questions").then((q) => setCountries(q.destinations)).catch(() => {});
  }, []);

  const tryDemo = () => run(async () => {
    setMe(await api<Me>("POST", "/api/auth/login", { email: "jo@example.test", password: "Liming-2026-demo" }));
    go("#/trips");
  });

  return (
    <>
      <section className="hero" aria-labelledby="hero-title">
        <div className="hero-copy">
          <h1 id="hero-title">Tell us how you lime. We'll plan the days.</h1>
          <p className="lede">
            Answer ten quick questions about your trip. Liming builds a day-by-day plan for the island,
            says why it picked every stop, and lets you change anything before you book.
          </p>
          <div className="actions">
            <a className="btn primary big" href={me ? "#/new" : "#/register"}>Plan a trip</a>
            {!me && <button className="btn big" onClick={tryDemo} disabled={busy}>Look around as Jo</button>}
          </div>
        </div>
        <figure className="sample" aria-label="An example day from a plan">
          <figcaption><span>Tue 10 Nov</span> St Vincent</figcaption>
          <ol className="timeline">
            {SAMPLE.map((s) => (
              <li key={s.title}>
                {s.travel && <div className="hop">{s.travel}</div>}
                <div className="stop">
                  <span className="time">{s.time}</span>
                  <div><strong>{s.title}</strong><p>{s.why}</p></div>
                </div>
              </li>
            ))}
          </ol>
        </figure>
      </section>

      <section className="page" aria-labelledby="how">
        <h2 id="how">How it works</h2>
        <ol className="how">
          <li><strong>Answer ten questions.</strong> Dates, who's coming, budget, what you enjoy, how full you like your days.</li>
          <li><strong>Get a plan that explains itself.</strong> Every stop says why: your interests, travel time, opening hours, the kids' ages.</li>
          <li><strong>Make it yours.</strong> Lock what you love, swap the rest, then book the stay, tours and tables.</li>
        </ol>
      </section>

      {countries.length > 0 && (
        <section className="page" aria-labelledby="where">
          <h2 id="where">Five countries to start with</h2>
          <ul className="signs">
            {countries.map((c) => (
              <li key={c.id} className="sign">
                <h3>{c.name}</h3>
                <p>{c.blurb}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
