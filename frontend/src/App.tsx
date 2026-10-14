import { useEffect, useState } from "react";
import { api, setCsrf, whenSignedOut, type Me } from "./api";
import { AppProvider, useApp } from "./components/ui";
import { Home } from "./pages/Home";
import { SignIn } from "./pages/SignIn";
import { PlanPage } from "./pages/PlanPage";
import { Trips } from "./pages/Trips";
import { Wizard } from "./pages/Wizard";

// A tiny hash router: #/, #/login, #/register, #/trips, #/new, #/plan/1, #/plan/1/answers
function useRoute(): string {
  const [hash, setHash] = useState(location.hash || "#/");
  useEffect(() => {
    const onChange = () => {
      setHash(location.hash || "#/");
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return hash;
}

export function App() {
  const [me, setMeState] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);
  const setMe = (m: Me | null) => {
    setCsrf(m?.csrf_token ?? null);
    setMeState(m);
  };

  useEffect(() => {
    api<Me>("GET", "/api/me").then(setMe).catch(() => setMe(null)).finally(() => setReady(true));
  }, []);

  return (
    <AppProvider me={me} setMe={setMe}>
      {ready ? <Shell /> : null}
    </AppProvider>
  );
}

function Shell() {
  const { me, setMe, go, toast } = useApp();
  const route = useRoute();

  useEffect(() => whenSignedOut(() => { setMe(null); go("#/login"); }), [setMe, go]);

  const logOut = async () => {
    try { await api("POST", "/api/auth/logout"); } catch { /* already gone */ }
    setMe(null);
    toast("Logged out. Lime again soon.");
    go("#/");
  };

  let page;
  const plan = route.match(/^#\/plan\/(\d+)(\/answers)?$/);
  const needsLogin = route !== "#/" && route !== "#/login" && route !== "#/register";
  if (needsLogin && !me) page = <SignIn mode="login" next={route} />;
  else if (route === "#/login" || route === "#/register") page = <SignIn mode={route === "#/login" ? "login" : "register"} />;
  else if (route === "#/trips") page = <Trips />;
  else if (route === "#/new") page = <Wizard key="new" />;
  else if (plan && plan[2]) page = <Wizard key={`edit-${plan[1]}`} tripId={Number(plan[1])} />;
  else if (plan) page = <PlanPage key={plan[1]} tripId={Number(plan[1])} />;
  else page = <Home />;

  return (
    <>
      <a className="skip" href="#main" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }}>
        Skip to content
      </a>
      <header className="site-header">
        <a className="wordmark" href="#/">liming</a>
        <nav aria-label="Main">
          {me ? (
            <>
              <a href="#/trips">Your trips</a>
              <a className="btn small primary" href="#/new">Plan a trip</a>
              <button className="link" onClick={logOut}>Log out</button>
            </>
          ) : (
            <>
              <a href="#/login">Log in</a>
              <a className="btn small primary" href="#/register">Sign up</a>
            </>
          )}
        </nav>
      </header>
      <main id="main" tabIndex={-1}>{page}</main>
      <footer className="site-footer">
        A portfolio project. Place names are real; every business and price is invented, and no payment is taken.
      </footer>
    </>
  );
}
