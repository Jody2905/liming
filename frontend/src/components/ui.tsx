// Shared building blocks: icons, the app context (who's logged in, messages, the confirm box).
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import type { Me } from "../api";

const PATHS: Record<string, string> = {
  lock: "M7 11V8a5 5 0 0 1 10 0v3 M5 11h14v10H5z",
  unlock: "M7 11V8a5 5 0 0 1 9.6-2 M5 11h14v10H5z",
  swap: "M4 8h13l-3-3 M20 16H7l3 3",
  move: "M12 3v18 M3 12h18 M9 6l3-3 3 3 M9 18l3 3 3-3",
  bin: "M4 7h16 M9 7V4h6v3 M6 7l1 13h10l1-13",
  plus: "M12 5v14 M5 12h14",
  redo: "M20 11a8 8 0 1 0-2.3 5.7 M20 4v7h-7",
  check: "M5 12l5 5L20 7",
  ticket: "M4 7h16v4a2 2 0 0 0 0 4v4H4v-4a2 2 0 0 0 0-4z",
  warn: "M12 4l9 16H3z M12 10v4 M12 17h.01",
  back: "M15 5l-7 7 7 7",
};

export function Icon({ name, label }: { name: keyof typeof PATHS | string; label?: string }) {
  return (
    <svg className="icon" viewBox="0 0 24 24" aria-hidden={label ? undefined : true} role={label ? "img" : undefined}
         aria-label={label}>
      <path d={PATHS[name] ?? PATHS.plus} />
    </svg>
  );
}

interface Toast { id: number; text: string; bad: boolean }
interface Ask { title: string; lines: string[]; yes: string; no: string; resolve: (ok: boolean) => void }

interface AppContext {
  me: Me | null;
  setMe: (me: Me | null) => void;
  toast: (text: string, bad?: boolean) => void;
  confirm: (title: string, lines: string[], yes: string, no?: string) => Promise<boolean>;
  go: (hash: string) => void;
}

const Ctx = createContext<AppContext | null>(null);

export function useApp(): AppContext {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useApp outside AppProvider");
  return ctx;
}

export function AppProvider({ me, setMe, children }: { me: Me | null; setMe: (m: Me | null) => void; children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [ask, setAsk] = useState<Ask | null>(null);
  const next = useRef(1);
  const dialog = useRef<HTMLDialogElement>(null);

  const toast = useCallback((text: string, bad = false) => {
    const id = next.current++;
    setToasts((t) => [...t, { id, text, bad }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), bad ? 6500 : 4000);
  }, []);

  const confirm = useCallback((title: string, lines: string[], yes: string, no = "Not now") =>
    new Promise<boolean>((resolve) => {
      setAsk({ title, lines, yes, no, resolve });
      requestAnimationFrame(() => dialog.current?.showModal());
    }), []);

  const answer = (ok: boolean) => {
    dialog.current?.close();
    ask?.resolve(ok);
    setAsk(null);
  };

  const go = useCallback((hash: string) => {
    if (location.hash === hash) window.dispatchEvent(new HashChangeEvent("hashchange"));
    else location.hash = hash;
  }, []);

  return (
    <Ctx.Provider value={{ me, setMe, toast, confirm, go }}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => <div key={t.id} className={t.bad ? "toast bad" : "toast"}>{t.text}</div>)}
      </div>
      <dialog ref={dialog} className="ask" aria-labelledby="ask-title" onCancel={(e) => { e.preventDefault(); answer(false); }}>
        {ask && (
          <>
            <h2 id="ask-title">{ask.title}</h2>
            {ask.lines.map((line) => <p key={line}>{line}</p>)}
            <div className="ask-actions">
              <button className="btn quiet" onClick={() => answer(false)}>{ask.no}</button>
              <button className="btn primary" onClick={() => answer(true)} autoFocus>{ask.yes}</button>
            </div>
          </>
        )}
      </dialog>
    </Ctx.Provider>
  );
}

/** Run an action with its button disabled, and show any error as a message. */
export function useBusy() {
  const { toast } = useApp();
  const [busy, setBusy] = useState(false);
  const run = useCallback(async (action: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await action();
    } catch (e) {
      toast((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }, [toast]);
  return [busy, run] as const;
}
