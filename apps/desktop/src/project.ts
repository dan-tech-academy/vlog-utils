import type { Turn } from "./conversation";
import type { IconName } from "./icons";
import { withStatus, type Comment, type Comments } from "./revise";

export type Phase =
  | "empty"
  | "brief"
  | "analyze"
  | "agent"
  | "questions"
  | "strategy"
  | "blocked"
  | "board"
  | "preview"
  | "exported";

export type ThreadItem =
  | { k: "user"; text: string }
  | { k: "batch"; items: { num: string; text: string }[] }
  | { k: "ev"; icon: IconName; text: string; tone?: "muted" | "accent" | "danger" }
  | { k: "divider"; text: string }
  | { k: "qa"; items: { prompt: string; answer: string }[] }
  | { k: "strategy"; text: string; status: "approved" | "replaced" }
  | { k: "ready"; seconds: number }
  | { k: "final"; path: string };

/** What edit/agent/thread.json holds: the conversation plus comments that are not sent yet. */
export type Thread = {
  version: 1;
  items: ThreadItem[];
  comments: Comments;
  /** What the last revision did to each card, keyed by cardKey. */
  changed: Record<string, string>;
  answers: Record<string, string>;
  savedAt?: number;
};

export type Interrupted = { cmd: string; mode?: string | null; started_at?: number };

export type EdlInfo = {
  ok: boolean;
  ranges: number;
  total_duration_s?: number | null;
  errors: string[];
  updated_at?: number;
};

export type ProjectStatus = {
  phase: Exclude<Phase, "empty">;
  brief: string;
  answers: { id: string; prompt: string; answer: string }[];
  turn: Turn | null;
  strategy: string;
  strategy_approved: boolean;
  unexpected_writes: string[];
  edl: EdlInfo | null;
  preview: string | null;
  preview_stale: boolean;
  final: string | null;
  thread: unknown;
  interrupted: Interrupted | null;
  transcripts: { done: number; total: number };
};

export type Project = {
  phase: Exclude<Phase, "empty">;
  brief: string;
  turn: Turn | null;
  strategy: string;
  approved: boolean;
  blocked: string[];
  edl: EdlInfo | null;
  preview: string | null;
  previewStale: boolean;
  final: string | null;
  transcripts: { done: number; total: number };
};

export type Resume =
  | { kind: "resumed"; savedAt?: number; drafts: number }
  | { kind: "agent"; drafts: number }
  | { kind: "render"; mode: "preview" | "final" }
  | { kind: "ingest" }
  | { kind: "restarted"; archive: string | null; transcripts: number };

const ITEM_KINDS = new Set(["user", "batch", "ev", "divider", "qa", "strategy", "ready", "final"]);

export function emptyThread(): Thread {
  return { version: 1, items: [], comments: {}, changed: {}, answers: {} };
}

export function projectFrom(status: ProjectStatus): Project {
  return {
    phase: status.phase,
    brief: status.brief || "",
    turn: status.turn || null,
    strategy: status.strategy || "",
    approved: Boolean(status.strategy_approved),
    blocked: status.unexpected_writes || [],
    edl: status.edl || null,
    preview: status.preview || null,
    previewStale: Boolean(status.preview_stale),
    final: status.final || null,
    transcripts: status.transcripts || { done: 0, total: 0 },
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function strings(raw: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (isRecord(raw)) {
    Object.entries(raw).forEach(([key, value]) => {
      if (typeof value === "string") out[key] = value;
    });
  }
  return out;
}

export function parseThread(raw: unknown): Thread | null {
  if (!isRecord(raw) || !Array.isArray(raw.items)) return null;
  const items = raw.items.filter(
    (item): item is ThreadItem => isRecord(item) && typeof item.k === "string" && ITEM_KINDS.has(item.k),
  );
  const comments: Comments = {};
  if (isRecord(raw.comments)) {
    Object.entries(raw.comments).forEach(([key, list]) => {
      if (!Array.isArray(list)) return;
      const clean = list.filter(
        (comment) => isRecord(comment) && typeof comment.id === "string" && typeof comment.text === "string"
          && (comment.status === "draft" || comment.status === "sent" || comment.status === "done"),
      ) as Comments[string];
      if (clean.length) comments[key] = clean;
    });
  }
  return {
    version: 1,
    items,
    comments,
    changed: strings(raw.changed),
    answers: strings(raw.answers),
    savedAt: typeof raw.savedAt === "number" ? raw.savedAt : undefined,
  };
}

/** Folders made by the older app have no thread.json; rebuild the history from what is on disk. */
export function legacyThread(status: ProjectStatus): Thread {
  const thread = emptyThread();
  if (status.brief) thread.items.push({ k: "user", text: status.brief });
  if (status.answers?.length) {
    thread.items.push({ k: "qa", items: status.answers.map(({ prompt, answer }) => ({ prompt, answer })) });
  }
  if (status.strategy && status.strategy_approved) {
    thread.items.push({ k: "strategy", text: status.strategy, status: "approved" });
  }
  if (status.edl?.ok) {
    thread.items.push({ k: "ev", icon: "film", text: `Agent đã dựng storyboard ${status.edl.ranges} cảnh`, tone: "accent" });
  }
  if (status.preview) thread.items.push({ k: "ready", seconds: status.edl?.total_duration_s ?? 0 });
  if (status.final) thread.items.push({ k: "final", path: status.final });
  return thread;
}

function countDrafts(comments: Comments): number {
  return Object.values(comments).reduce(
    (total, list) => total + list.filter((comment) => comment.status === "draft").length,
    0,
  );
}

export function fromStatus(status: ProjectStatus): { project: Project; thread: Thread; resume: Resume | null } {
  const stored = parseThread(status.thread);
  const base = stored || legacyThread(status);
  // A comment still marked sent means the app closed mid-revision; it goes back to the batch.
  const thread: Thread = { ...base, comments: withStatus(base.comments, "sent", "draft") };
  const drafts = countDrafts(thread.comments);
  const job = status.interrupted;
  let resume: Resume | null = null;
  if (job?.cmd === "agent_turn") resume = { kind: "agent", drafts };
  else if (job?.cmd === "render") resume = { kind: "render", mode: job.mode === "final" ? "final" : "preview" };
  else if (job?.cmd === "ingest") resume = { kind: "ingest" };
  else if (status.phase !== "brief" && status.brief) resume = { kind: "resumed", savedAt: thread.savedAt, drafts };
  return { project: projectFrom(status), thread, resume };
}

export type ThreadAction =
  | { type: "load"; thread: Thread }
  | { type: "push"; items: ThreadItem[] }
  | { type: "answer"; id: string; text: string }
  | { type: "clearAnswers" }
  | { type: "addComment"; key: string; comment: Comment }
  | { type: "editComment"; key: string; id: string; text: string }
  | { type: "removeComment"; key: string; id: string }
  | { type: "clearDrafts" }
  | { type: "send" }
  | { type: "unsend" }
  | { type: "revised"; comments: Comments; changed: Record<string, string>; items: ThreadItem[] };

function mapComments(comments: Comments, key: string, update: (list: Comment[]) => Comment[]): Comments {
  const list = update(comments[key] || []);
  const next = { ...comments };
  if (list.length) next[key] = list;
  else delete next[key];
  return next;
}

export function threadReducer(state: Thread, action: ThreadAction): Thread {
  switch (action.type) {
    case "load":
      return action.thread;
    case "push":
      return { ...state, items: [...state.items, ...action.items] };
    case "answer":
      return { ...state, answers: { ...state.answers, [action.id]: action.text } };
    case "clearAnswers":
      return { ...state, answers: {} };
    case "addComment":
      return { ...state, comments: mapComments(state.comments, action.key, (list) => [...list, action.comment]) };
    case "editComment":
      return {
        ...state,
        comments: mapComments(state.comments, action.key, (list) =>
          list.map((comment) => (comment.id === action.id ? { ...comment, text: action.text } : comment))),
      };
    case "removeComment":
      return {
        ...state,
        comments: mapComments(state.comments, action.key, (list) => list.filter((comment) => comment.id !== action.id)),
      };
    case "clearDrafts": {
      const comments: Comments = {};
      Object.entries(state.comments).forEach(([key, list]) => {
        const kept = list.filter((comment) => comment.status !== "draft");
        if (kept.length) comments[key] = kept;
      });
      return { ...state, comments };
    }
    case "send":
      return { ...state, comments: withStatus(state.comments, "draft", "sent") };
    case "unsend":
      return { ...state, comments: withStatus(state.comments, "sent", "draft") };
    case "revised":
      return { ...state, comments: action.comments, changed: action.changed, items: [...state.items, ...action.items] };
  }
}

export function showsBoard(project: Project | null): boolean {
  if (!project) return false;
  if (project.phase === "board" || project.phase === "preview" || project.phase === "exported") return true;
  return project.phase === "agent" && project.approved && project.edl !== null;
}

export const STEPS = ["Footage", "Brief", "Trao đổi", "Storyboard", "Xuất"] as const;

export function stepIndex(phase: Phase, rendering: "preview" | "final" | null = null): number {
  if (phase === "empty") return 0;
  if (phase === "brief") return 1;
  if (phase === "board") return rendering === "final" ? 4 : 3;
  if (phase === "preview") return 4;
  if (phase === "exported") return 5;
  return 2;
}
