export type Word = { start: number; end: number };

export type Range = {
  source: string;
  start: number;
  end: number;
  beat?: string;
  quote?: string;
  reason?: string;
};

const PAD_IN = 0.05;
const PAD_OUT = 0.08;

export function round3(value: number): number {
  return Math.round(value * 1000) / 1000;
}

function padForGap(gap: number, preferred: number): number | null {
  if (gap + 1e-6 < 0.03) return null;
  const pad = Math.min(preferred, 0.2, gap);
  if (pad + 1e-6 < 0.03) return null;
  return pad;
}

function nearestIndex(points: number[], time: number): number {
  let best = 0;
  let dist = Infinity;
  points.forEach((point, index) => {
    const delta = Math.abs(point - time);
    if (delta < dist) {
      dist = delta;
      best = index;
    }
  });
  return best;
}

function snapStart(time: number, words: Word[]): number {
  let index = nearestIndex(words.map((word) => word.start), time);
  while (index >= 0) {
    const prev = index === 0 ? 0 : words[index - 1].end;
    const pad = padForGap(words[index].start - prev, PAD_IN);
    if (pad !== null) return round3(Math.max(0, words[index].start - pad));
    index -= 1;
  }
  return 0;
}

function snapEnd(time: number, words: Word[], duration?: number): number {
  let index = nearestIndex(words.map((word) => word.end), time);
  while (index < words.length) {
    const gap = index < words.length - 1
      ? words[index + 1].start - words[index].end
      : duration === undefined
        ? Number.POSITIVE_INFINITY
        : Math.max(0, duration - words[index].end);
    const pad = padForGap(gap, PAD_OUT);
    if (pad !== null) return round3(words[index].end + pad);
    if (index === words.length - 1) {
      return round3(duration ?? words[index].end + PAD_OUT);
    }
    index += 1;
  }
  const last = words[words.length - 1];
  return round3(duration ?? last.end + PAD_OUT);
}

export function snapEdge(
  time: number,
  words: Word[],
  edge: "start" | "end",
  duration?: number,
): number {
  const sorted = [...words].sort((a, b) => a.start - b.start);
  if (sorted.length === 0) return round3(Math.max(0, time));
  return edge === "start" ? snapStart(time, sorted) : snapEnd(time, sorted, duration);
}

export function trimRange(
  range: Range,
  edge: "start" | "end",
  time: number,
  words: Word[],
  duration?: number,
): Range {
  const snapped = snapEdge(time, words, edge, duration);
  if (edge === "start") {
    if (snapped >= range.end) return range;
    return { ...range, start: snapped };
  }
  if (snapped <= range.start) return range;
  return { ...range, end: snapped };
}

export function reorder<T>(items: T[], from: number, to: number): T[] {
  if (from === to || from < 0 || to < 0 || from >= items.length || to >= items.length) {
    return items;
  }
  const next = items.slice();
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

export function removeAt<T>(items: T[], index: number): T[] {
  return items.filter((_, itemIndex) => itemIndex !== index);
}

export function totalDuration(ranges: Array<{ start: number; end: number }>): number {
  const sum = ranges.reduce((total, range) => total + Math.max(0, range.end - range.start), 0);
  return round3(sum);
}
