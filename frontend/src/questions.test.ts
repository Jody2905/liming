import { describe, expect, it } from "vitest";
import type { Questions } from "./api";
import { newDraft, problem, toAnswers } from "./questions";

const q = { max_nights: 14, max_adults: 8, max_children: 6, min_budget_cents_per_person_night: 5000 } as Questions;
const today = "2026-11-02";

describe("the questionnaire", () => {
  it("starts three weeks out, for five nights", () => {
    const d = newDraft(today);
    expect([d.start, d.end]).toEqual(["2026-11-23", "2026-11-28"]);
  });

  it("checks each step", () => {
    const d = newDraft(today);
    expect(problem("where", d, q, today)).toBe("Pick a country to start.");
    expect(problem("when", { ...d, end: d.start }, q, today)).toBe("The last day must be after the first.");
    expect(problem("when", { ...d, start: "2026-11-01" }, q, today)).toBe("The trip can't start in the past.");
    expect(problem("who", { ...d, children: 1 }, q, today)).toBe("How old is the youngest child?");
    expect(problem("budget", { ...d, budgetDollars: "200" }, q, today)).toBe(
      "For this group and these dates, the budget needs to be at least US$500.");
    expect(problem("budget", { ...d, budgetDollars: "$2,500" }, q, today)).toBeNull();
    expect(problem("interests", d, q, today)).toBe("Tap at least one thing you'd enjoy.");
  });

  it("turns the answers into what the API expects", () => {
    const d = { ...newDraft(today), destinationId: 3, budgetDollars: "2,500.50", title: " Week away ",
                children: 0, youngestAge: 7, interests: { beaches: 2 as const } };
    const a = toAnswers(d);
    expect(a.budget_cents).toBe(250050);
    expect(a.title).toBe("Week away");
    expect(a.youngest_age).toBeNull();              // no children, so no age is sent
  });
});
