import { describe, expect, it } from "vitest";
import { addDays, countdown, dayLabel, duration, money, nextWeight, nightsBetween, plural } from "./format";

describe("format", () => {
  it("shows money in US dollars, dropping .00", () => {
    expect(money(123456)).toBe("US$1,234.56");
    expect(money(12300)).toBe("US$123");
    expect(money(-505)).toBe("-US$5.05");
  });
  it("works with dates without time-zone surprises", () => {
    expect(dayLabel("2026-11-09")).toBe("Mon 9 Nov");
    expect(addDays("2026-11-30", 1)).toBe("2026-12-01");
    expect(nightsBetween("2026-11-09", "2026-11-14")).toBe(5);
  });
  it("reads well", () => {
    expect(plural(1, "night")).toBe("1 night");
    expect(plural(3, "child", "children")).toBe("3 children");
    expect(duration(25)).toBe("25 min");
    expect(duration(60)).toBe("1 hour");
    expect(duration(75)).toBe("1 h 15 min");
    expect(countdown(754)).toBe("12:34");
    expect(countdown(-3)).toBe("0:00");
  });
  it("cycles interest tiles: like, love, off", () => {
    expect(nextWeight(undefined)).toBe(1);
    expect(nextWeight(1)).toBe(2);
    expect(nextWeight(2)).toBe(0);
  });
});
