// Small pure helpers, unit-tested in format.test.ts.

/** 123456 -> "US$1,234.56"; whole dollars drop the cents: 12300 -> "US$123". */
export function money(cents: number): string {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  const dollars = Math.floor(abs / 100).toLocaleString("en-US");
  const rest = abs % 100;
  return `${sign}US$${dollars}${rest ? "." + String(rest).padStart(2, "0") : ""}`;
}

/** "2026-11-09" as a local date (no time-zone surprises). */
export function parseDay(iso: string): Date {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function isoDay(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function addDays(iso: string, n: number): string {
  const d = parseDay(iso);
  d.setDate(d.getDate() + n);
  return isoDay(d);
}

export function nightsBetween(start: string, end: string): number {
  return Math.round((parseDay(end).getTime() - parseDay(start).getTime()) / 86_400_000);
}

/** "Mon 9 Nov" */
export function dayLabel(iso: string): string {
  const d = parseDay(iso);
  const weekday = d.toLocaleDateString("en-GB", { weekday: "short" });
  const month = d.toLocaleDateString("en-GB", { month: "short" });
  return `${weekday} ${d.getDate()} ${month}`;
}

export function plural(n: number, word: string, many = word + "s"): string {
  return `${n} ${n === 1 ? word : many}`;
}

/** 25 -> "25 min", 75 -> "1 h 15 min", 60 -> "1 hour" */
export function duration(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (!h) return `${m} min`;
  if (!m) return plural(h, "hour");
  return `${h} h ${m} min`;
}

/** A hold's countdown: 754 -> "12:34" */
export function countdown(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** Interest tiles cycle: not picked -> like (1 pip) -> love (2 pips) -> not picked. */
export function nextWeight(weight: number | undefined): 0 | 1 | 2 {
  return weight === 1 ? 2 : weight === 2 ? 0 : 1;
}
