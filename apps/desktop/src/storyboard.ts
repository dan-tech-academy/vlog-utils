export type Word = { start: number; end: number; text?: string };

export type Range = {
  source: string;
  start: number;
  end: number;
  beat?: string;
  quote?: string;
  reason?: string;
};

export function round3(value: number): number {
  return Math.round(value * 1000) / 1000;
}

export function totalDuration(ranges: Array<{ start: number; end: number }>): number {
  const sum = ranges.reduce((total, range) => total + Math.max(0, range.end - range.start), 0);
  return round3(sum);
}
