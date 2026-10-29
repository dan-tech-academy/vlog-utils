import { describe, expect, it } from "vitest";
import {
  buildNote,
  cardKey,
  carryComments,
  diffRanges,
  draftsOf,
  type Comments,
  type Words,
} from "./revise";
import type { Range } from "./storyboard";

const words: Words = {
  C0103: [
    { start: 12.42, end: 12.8, text: "Quán" },
    { start: 12.86, end: 13.2, text: "này" },
    { start: 13.3, end: 13.9, text: "không" },
    { start: 14.0, end: 14.6, text: "biển" },
    { start: 14.7, end: 15.16, text: "luôn." },
  ],
  C0104: [
    { start: 8.6, end: 9.0, text: "Mưa" },
    { start: 9.1, end: 9.5, text: "rồi." },
  ],
};

const board: Range[] = [
  { source: "C0104", start: 8.55, end: 9.58, beat: "Chợ đêm" },
  { source: "C0103", start: 12.37, end: 15.24, beat: "Cà phê" },
  { source: "C0104", start: 30, end: 31 },
];

describe("cardKey", () => {
  it("is source@start-end with three decimals", () => {
    expect(cardKey({ source: "C0103", start: 12.37, end: 15.24 })).toBe("C0103@12.370-15.240");
  });

  it("finds unsent comments again after the storyboard is reloaded", () => {
    const saved: Comments = {
      "C0103@12.370-15.240": [{ id: "c1", text: "Bỏ chữ luôn", status: "draft" }],
      "C0104@99.000-100.000": [{ id: "c2", text: "cảnh đã mất", status: "draft" }],
    };
    const reloaded = board.map((range) => ({ ...range }));
    const drafts = draftsOf(reloaded, saved);
    expect(drafts.map((draft) => [draft.index, draft.comment.id])).toEqual([[1, "c1"]]);
  });
});

describe("buildNote", () => {
  it("lists only commented cards, numbered as on the storyboard", () => {
    const comments: Comments = {
      [cardKey(board[1])]: [
        { id: "c1", text: "Bỏ chữ “luôn” ở cuối", status: "draft" },
        { id: "c0", text: "đã xử lý", status: "done", result: "x" },
      ],
      [cardKey(board[2])]: [{ id: "c2", text: "Bỏ\ncảnh này", status: "draft" }],
    };
    const note = buildNote(board, comments, words);
    const lines = note.split("\n");
    expect(lines[0]).toContain("Card N is ranges[N-1]");
    expect(lines[1]).toBe('02 (C0103 12.37-15.24 "Quán này không biển luôn."): Bỏ chữ “luôn” ở cuối');
    expect(lines[2]).toBe("03 (C0104 30.00-31.00): Bỏ cảnh này");
    expect(lines[3]).toContain("keep every other range exactly as it is");
    expect(note).not.toContain("đã xử lý");
  });

  it("is empty without drafts", () => {
    expect(buildNote(board, {}, words)).toBe("");
  });
});

describe("diffRanges", () => {
  it("labels a trimmed card with the words it lost and the time saved", () => {
    const after = [board[0], { ...board[1], end: 14.68 }, board[2]];
    const diff = diffRanges(board, after, words);
    expect(diff.labels[cardKey(after[1])]).toBe("Bỏ “luôn.” · ngắn hơn 0.56s");
    expect(diff.changed).toBe(1);
    expect(diff.removed).toEqual([]);
    expect(diff.labels[cardKey(board[0])]).toBeUndefined();
  });

  it("marks removed and added cards", () => {
    const after: Range[] = [board[1], { source: "C0105", start: 3, end: 5 }];
    const diff = diffRanges(board, after, words);
    expect(diff.removed.map((item) => item.index)).toEqual([0, 2]);
    expect(diff.added).toEqual([1]);
    expect(diff.labels[cardKey(after[1])]).toBe("Cảnh mới");
    expect(diff.matches).toEqual([{ from: 1, to: 0 }]);
  });

  it("says when the agent kept more words", () => {
    const shorter = { ...board[1], end: 14.68 };
    const diff = diffRanges([shorter], [board[1]], words);
    expect(diff.labels[cardKey(board[1])]).toBe("Giữ thêm “luôn.” · dài hơn 0.56s");
  });
});

describe("carryComments", () => {
  it("moves comments to the replacing card and records the result", () => {
    const after = [board[0], { ...board[1], end: 14.68 }];
    const comments: Comments = {
      [cardKey(board[0])]: [{ id: "a", text: "giữ", status: "sent" }],
      [cardKey(board[1])]: [{ id: "b", text: "Bỏ chữ luôn", status: "sent" }],
      [cardKey(board[2])]: [{ id: "c", text: "Bỏ cảnh này", status: "sent" }],
    };
    const diff = diffRanges(board, after, words);
    const next = carryComments(board, after, diff, comments);
    expect(next[cardKey(after[1])]).toEqual([
      { id: "b", text: "Bỏ chữ luôn", status: "done", result: "Bỏ “luôn.” · ngắn hơn 0.56s" },
    ]);
    expect(next[cardKey(board[0])][0]).toMatchObject({ status: "done", result: "Agent giữ nguyên cảnh này" });
    expect(Object.keys(next)).toHaveLength(2);
  });
});
