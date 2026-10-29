import { describe, expect, it } from "vitest";
import { totalDuration, type Range } from "./storyboard";

describe("storyboard", () => {
  const ranges: Range[] = [
    { source: "A", start: 0.95, end: 1.48 },
    { source: "B", start: 2, end: 3 },
    { source: "C", start: 4, end: 5 },
  ];

  it("sums duration", () => {
    expect(totalDuration(ranges)).toBe(2.53);
  });
});
