import { describe, expect, it } from "vitest";
import { acceptsEdl, questionFields, type Turn } from "./conversation";

const fixture: Turn = {
  kind: "questions",
  questions: [
    { id: "aspect", prompt: "16:9 hay 9:16?" },
    { id: "keep", prompt: "Giữ câu nào?" },
  ],
};

describe("question form", () => {
  it("turns a question fixture into form fields", () => {
    expect(questionFields(fixture).map((question) => question.prompt)).toEqual([
      "16:9 hay 9:16?",
      "Giữ câu nào?",
    ]);
  });

  it("rejects an EDL until the strategy is approved", () => {
    expect(acceptsEdl({ kind: "edl" }, false)).toBe(false);
    expect(acceptsEdl({ kind: "edl" }, true)).toBe(true);
    expect(acceptsEdl(fixture, true)).toBe(false);
  });
});
