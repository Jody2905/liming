// The questionnaire's steps and checks, kept apart from the screens so they can be tested.
// The server checks everything again; these checks just give quicker, friendlier feedback.
import type { Answers, Plan, Questions } from "./api";
import { addDays, money, nightsBetween } from "./format";

export interface Draft {
  destinationId: number | null;
  start: string;
  end: string;
  adults: number;
  children: number;
  youngestAge: number | null;
  budgetDollars: string;
  interests: Record<string, 1 | 2>;
  pace: string;
  dayStart: string;
  stayStyle: string;
  diningStyle: string;
  diets: string[];
  transport: string;
  stepFree: boolean;
  title: string;
}

export const STEPS = [
  { key: "where", question: "Where are we liming?" },
  { key: "when", question: "When are you going?" },
  { key: "who", question: "Who's coming?" },
  { key: "budget", question: "What's the budget?" },
  { key: "interests", question: "What do you enjoy?" },
  { key: "pace", question: "How full should the days be?" },
  { key: "stay", question: "Where would you like to stay?" },
  { key: "food", question: "How do you like to eat?" },
  { key: "around", question: "Getting around" },
  { key: "name", question: "Last thing: name the trip" },
] as const;

export type StepKey = (typeof STEPS)[number]["key"];

export function newDraft(today: string): Draft {
  const start = addDays(today, 21);
  return {
    destinationId: null, start, end: addDays(start, 5), adults: 2, children: 0, youngestAge: null,
    budgetDollars: "3000", interests: {}, pace: "balanced", dayStart: "normal", stayStyle: "hotel",
    diningStyle: "mix", diets: [], transport: "taxi", stepFree: false, title: "",
  };
}

export function draftFromPlan(plan: Plan): Draft {
  const a = plan.answers;
  const interests: Record<string, 1 | 2> = {};
  for (const [tag, weight] of Object.entries(a.interests)) interests[tag] = weight === 2 ? 2 : 1;
  return {
    destinationId: plan.destination.id, start: a.start_date, end: a.end_date, adults: a.adults,
    children: a.children, youngestAge: a.youngest_age ?? null, budgetDollars: String(a.budget_cents / 100),
    interests, pace: a.pace, dayStart: a.day_start, stayStyle: a.stay_style, diningStyle: a.dining_style,
    diets: [...a.diets], transport: a.transport, stepFree: a.step_free, title: plan.title,
  };
}

export function budgetCents(d: Draft): number | null {
  const n = Number(String(d.budgetDollars).replace(/[,\s$]/g, ""));
  return Number.isFinite(n) && n > 0 ? Math.round(n * 100) : null;
}

export function people(d: Draft): number {
  return d.adults + d.children;
}

/** The problem with this step's answer, or null if it's fine. */
export function problem(step: StepKey, d: Draft, q: Questions, today: string): string | null {
  switch (step) {
    case "where":
      return d.destinationId ? null : "Pick a country to start.";
    case "when": {
      if (!d.start || !d.end) return "Pick both days.";
      if (d.start < today) return "The trip can't start in the past.";
      const nights = nightsBetween(d.start, d.end);
      if (nights < 1) return "The last day must be after the first.";
      if (nights > q.max_nights) return `Plans can be up to ${q.max_nights} nights.`;
      return null;
    }
    case "who":
      if (d.adults < 1 || d.adults > q.max_adults) return `Between 1 and ${q.max_adults} adults.`;
      if (d.children < 0 || d.children > q.max_children) return `Up to ${q.max_children} children.`;
      if (d.children && (d.youngestAge === null || d.youngestAge < 0 || d.youngestAge > 17))
        return "How old is the youngest child?";
      return null;
    case "budget": {
      const cents = budgetCents(d);
      if (cents === null) return "Enter a budget in US dollars.";
      const least = q.min_budget_cents_per_person_night * people(d) * Math.max(1, nightsBetween(d.start, d.end));
      return cents < least ? `For this group and these dates, the budget needs to be at least ${money(least)}.` : null;
    }
    case "interests":
      return Object.keys(d.interests).length ? null : "Tap at least one thing you'd enjoy.";
    case "name":
      return d.title.trim() ? null : "Give the trip a name.";
    default:
      return null;
  }
}

export function toAnswers(d: Draft): Answers {
  return {
    title: d.title.trim(), destination_id: d.destinationId ?? 0, start_date: d.start, end_date: d.end,
    adults: d.adults, children: d.children, youngest_age: d.children ? d.youngestAge : null,
    budget_cents: budgetCents(d) ?? 0, pace: d.pace, stay_style: d.stayStyle, dining_style: d.diningStyle,
    transport: d.transport, day_start: d.dayStart, step_free: d.stepFree, interests: d.interests, diets: d.diets,
  };
}
