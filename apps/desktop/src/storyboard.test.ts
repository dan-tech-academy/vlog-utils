import { describe, expect, it } from "vitest";
import { removeAt, reorder, snapEdge, totalDuration, trimRange, type Range } from "./storyboard";

const wide = [
  { start: 1, end: 1.4 },
  { start: 2, end: 2.4 },
];

const tight = [
  { start: 1, end: 1.2 },
  { start: 1.22, end: 1.5 },
];

describe("snap", () => {
  it("pads 50ms before a word when the gap allows it", () => {
    expect(snapEdge(2.05, wide, "start")).toBe(1.95);
  });

  it("pads 80ms after a word when the gap allows it", () => {
    expect(snapEdge(1.4, wide, "end")).toBe(1.48);
  });

  it("includes the previous word when 30ms of lead-in does not fit", () => {
    expect(snapEdge(1.22, tight, "start")).toBe(0.95);
  });

  it("includes the next word when 30ms of tail does not fit", () => {
    expect(snapEdge(1.2, tight, "end")).toBe(1.58);
  });

  it("stops at the media end when the last word has no 30ms left", () => {
    expect(snapEdge(9.99, [{ start: 9.98, end: 9.99 }], "end", 10)).toBe(10);
  });
});

describe("edits", () => {
  const ranges: Range[] = [
    { source: "A", start: 0.95, end: 1.48 },
    { source: "B", start: 2, end: 3 },
    { source: "C", start: 4, end: 5 },
  ];

  it("reorders ranges", () => {
    expect(reorder(ranges, 0, 2).map((range) => range.source)).toEqual(["B", "C", "A"]);
  });

  it("deletes a range", () => {
    expect(removeAt(ranges, 1).map((range) => range.source)).toEqual(["A", "C"]);
  });

  it("sums duration", () => {
    expect(totalDuration(ranges)).toBe(2.53);
  });

  it("refuses a trim that would invert the range", () => {
    const range = ranges[0];
    expect(trimRange(range, "end", 0, [], undefined)).toEqual(range);
  });
});
