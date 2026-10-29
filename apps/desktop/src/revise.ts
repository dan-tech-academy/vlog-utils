import { pad2 } from "./format";
import type { Range, Word } from "./storyboard";

export type CommentStatus = "draft" | "sent" | "done";
export type Comment = { id: string; text: string; status: CommentStatus; result?: string };
/** Comments per card, keyed by cardKey so they survive a reload of edl.json. */
export type Comments = Record<string, Comment[]>;
export type Words = Record<string, Word[]>;

const EPS = 1e-6;

export function cardKey(range: Pick<Range, "source" | "start" | "end">): string {
  return `${range.source}@${range.start.toFixed(3)}-${range.end.toFixed(3)}`;
}

export function keptWords(range: Range, words: Words): Word[] {
  return (words[range.source] || []).filter(
    (word) => word.start >= range.start - EPS && word.end <= range.end + EPS,
  );
}

export function quoteOf(range: Range, words: Words): string {
  const spoken = keptWords(range, words).map((word) => word.text || "").filter(Boolean).join(" ");
  return spoken || range.quote || "";
}

export type Draft = { index: number; range: Range; comment: Comment };

export function draftsOf(ranges: Range[], comments: Comments): Draft[] {
  return ranges.flatMap((range, index) =>
    (comments[cardKey(range)] || [])
      .filter((comment) => comment.status === "draft")
      .map((comment) => ({ index, range, comment })),
  );
}

function oneLine(text: string, limit = 0): string {
  const flat = text.replace(/\s+/g, " ").trim();
  return limit && flat.length > limit ? `${flat.slice(0, limit - 1)}…` : flat;
}

export function buildNote(ranges: Range[], comments: Comments, words: Words): string {
  const lines: string[] = [];
  ranges.forEach((range, index) => {
    const texts = (comments[cardKey(range)] || [])
      .filter((comment) => comment.status === "draft")
      .map((comment) => oneLine(comment.text))
      .filter(Boolean);
    if (!texts.length) return;
    const quote = oneLine(quoteOf(range, words), 90).replace(/"/g, "'");
    const where = `${range.source} ${range.start.toFixed(2)}-${range.end.toFixed(2)}${quote ? ` "${quote}"` : ""}`;
    lines.push(`${pad2(index + 1)} (${where}): ${texts.join(" / ")}`);
  });
  if (!lines.length) return "";
  return [
    'Card comments. Card N is ranges[N-1] in edit/edl.json (see "Comments on cards" in edit/agent/protocol.md).',
    ...lines,
    'Change only these cards and keep every other range exactly as it is. Reply {"kind":"edl"}.',
  ].join("\n");
}

function phrase(words: Word[]): string {
  const texts = words.map((word) => word.text || "").filter(Boolean);
  if (!texts.length) return `${words.length} từ`;
  if (texts.length <= 8) return `“${texts.join(" ")}”`;
  return `“${texts.slice(0, 4).join(" ")} … ${texts.slice(-3).join(" ")}”`;
}

export function changeLabel(before: Range, after: Range, words: Words): string {
  const was = keptWords(before, words);
  const now = keptWords(after, words);
  const wasStarts = new Set(was.map((word) => word.start));
  const nowStarts = new Set(now.map((word) => word.start));
  const dropped = before.source === after.source ? was.filter((word) => !nowStarts.has(word.start)) : was;
  const gained = before.source === after.source ? now.filter((word) => !wasStarts.has(word.start)) : now;
  const parts: string[] = [];
  if (dropped.length) parts.push(`Bỏ ${phrase(dropped)}`);
  if (gained.length) parts.push(`Giữ thêm ${phrase(gained)}`);
  const delta = (after.end - after.start) - (before.end - before.start);
  if (Math.abs(delta) >= 0.005) {
    parts.push(delta < 0 ? `ngắn hơn ${Math.abs(delta).toFixed(2)}s` : `dài hơn ${delta.toFixed(2)}s`);
  }
  if (!parts.length) parts.push("Chỉnh lại điểm cắt");
  return parts.join(" · ");
}

export type RangeDiff = {
  /** Card index in the new list → index of the card it replaced. */
  matches: { from: number; to: number }[];
  /** Label per new cardKey, for cards that changed or are new. */
  labels: Record<string, string>;
  removed: { index: number; range: Range }[];
  added: number[];
  changed: number;
};

export function diffRanges(before: Range[], after: Range[], words: Words): RangeDiff {
  const used = new Set<number>();
  const matchOf: Array<number | null> = after.map(() => null);
  const beforeKeys = before.map(cardKey);

  after.forEach((range, to) => {
    const key = cardKey(range);
    const from = beforeKeys.findIndex((candidate, index) => candidate === key && !used.has(index));
    if (from >= 0) {
      used.add(from);
      matchOf[to] = from;
    }
  });
  after.forEach((range, to) => {
    if (matchOf[to] !== null) return;
    let best = -1;
    let bestOverlap = 0;
    before.forEach((old, from) => {
      if (used.has(from) || old.source !== range.source) return;
      const overlap = Math.min(old.end, range.end) - Math.max(old.start, range.start);
      if (overlap > bestOverlap + EPS) {
        best = from;
        bestOverlap = overlap;
      }
    });
    if (best >= 0) {
      used.add(best);
      matchOf[to] = best;
    }
  });

  const diff: RangeDiff = { matches: [], labels: {}, removed: [], added: [], changed: 0 };
  after.forEach((range, to) => {
    const from = matchOf[to];
    if (from === null) {
      diff.added.push(to);
      diff.labels[cardKey(range)] = "Cảnh mới";
      return;
    }
    diff.matches.push({ from, to });
    if (beforeKeys[from] !== cardKey(range)) {
      diff.changed += 1;
      diff.labels[cardKey(range)] = changeLabel(before[from], range, words);
    }
  });
  before.forEach((range, index) => {
    if (!used.has(index)) diff.removed.push({ index, range });
  });
  return diff;
}

/** Move comments onto the cards that replaced theirs; sent comments get the agent's result. */
export function carryComments(before: Range[], after: Range[], diff: RangeDiff, comments: Comments): Comments {
  const next: Comments = {};
  diff.matches.forEach(({ from, to }) => {
    const newKey = cardKey(after[to]);
    const result = diff.labels[newKey] || "Agent giữ nguyên cảnh này";
    const moved = (comments[cardKey(before[from])] || []).map((comment): Comment =>
      comment.status === "sent" ? { ...comment, status: "done", result } : comment,
    );
    if (moved.length) next[newKey] = [...(next[newKey] || []), ...moved];
  });
  return next;
}

export function withStatus(comments: Comments, from: CommentStatus, to: CommentStatus): Comments {
  const next: Comments = {};
  Object.entries(comments).forEach(([key, list]) => {
    next[key] = list.map((comment) => (comment.status === from ? { ...comment, status: to } : comment));
  });
  return next;
}
