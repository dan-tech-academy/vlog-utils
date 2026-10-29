import { describe, expect, it } from "vitest";
import {
  emptyThread,
  fromStatus,
  showsBoard,
  stepIndex,
  threadReducer,
  type ProjectStatus,
} from "./project";

function status(overrides: Partial<ProjectStatus> = {}): ProjectStatus {
  return {
    phase: "brief",
    brief: "",
    answers: [],
    turn: null,
    strategy: "",
    strategy_approved: false,
    unexpected_writes: [],
    edl: null,
    preview: null,
    preview_stale: false,
    final: null,
    thread: null,
    interrupted: null,
    transcripts: { done: 0, total: 6 },
    ...overrides,
  };
}

const edl = { ok: true, ranges: 9, total_duration_s: 41.2, errors: [] };

describe("fromStatus", () => {
  it("opens a fresh folder at the brief with nothing to resume", () => {
    const { project, thread, resume } = fromStatus(status());
    expect(project.phase).toBe("brief");
    expect(thread.items).toEqual([]);
    expect(resume).toBeNull();
    expect(showsBoard(project)).toBe(false);
  });

  it("returns to pending questions and rebuilds history for folders without thread.json", () => {
    const turn = { kind: "questions" as const, questions: [{ id: "aspect", prompt: "16:9 hay 9:16?" }] };
    const { project, thread, resume } = fromStatus(status({ phase: "questions", brief: "Vlog Đà Lạt", turn }));
    expect(project.phase).toBe("questions");
    expect(project.turn).toEqual(turn);
    expect(thread.items).toEqual([{ k: "user", text: "Vlog Đà Lạt" }]);
    expect(resume).toMatchObject({ kind: "resumed" });
  });

  it("returns to a strategy waiting for approval", () => {
    const { project, thread } = fromStatus(status({
      phase: "strategy",
      brief: "b",
      strategy: "Mở bằng đồi chè",
      answers: [{ id: "aspect", prompt: "16:9?", answer: "16:9" }],
    }));
    expect(project.strategy).toBe("Mở bằng đồi chè");
    expect(thread.items).toEqual([
      { k: "user", text: "b" },
      { k: "qa", items: [{ prompt: "16:9?", answer: "16:9" }] },
    ]);
  });

  it("returns to the storyboard with saved comments", () => {
    const saved = {
      version: 1,
      items: [{ k: "user", text: "b" }, { k: "nonsense" }],
      comments: { "C0103@12.370-15.240": [{ id: "c1", text: "Bỏ chữ luôn", status: "draft" }] },
      changed: { "C0103@12.370-15.240": "Bỏ “luôn.” · ngắn hơn 0.46s", bad: 3 },
      answers: {},
      savedAt: 1730000000000,
    };
    const { project, thread, resume } = fromStatus(status({
      phase: "board", brief: "b", strategy: "s", strategy_approved: true, edl, thread: saved,
    }));
    expect(showsBoard(project)).toBe(true);
    expect(thread.items).toEqual([{ k: "user", text: "b" }]);
    expect(thread.comments["C0103@12.370-15.240"][0].status).toBe("draft");
    expect(thread.changed).toEqual({ "C0103@12.370-15.240": "Bỏ “luôn.” · ngắn hơn 0.46s" });
    expect(resume).toEqual({ kind: "resumed", savedAt: 1730000000000, drafts: 1 });
  });

  it("treats a preview that no longer matches as the storyboard step", () => {
    const { project } = fromStatus(status({
      phase: "board", brief: "b", strategy_approved: true, edl, preview_stale: true,
    }));
    expect(project.previewStale).toBe(true);
    expect(project.preview).toBeNull();
    expect(stepIndex(project.phase)).toBe(3);
  });

  it("puts comments back in the batch when the agent was cut off", () => {
    const saved = {
      version: 1,
      items: [],
      comments: {
        a: [{ id: "c1", text: "x", status: "sent" }],
        b: [{ id: "c2", text: "y", status: "sent" }, { id: "c3", text: "z", status: "done", result: "ok" }],
      },
      changed: {},
      answers: {},
    };
    const { thread, resume } = fromStatus(status({
      phase: "board", brief: "b", strategy_approved: true, edl, thread: saved,
      interrupted: { cmd: "agent_turn", mode: null },
    }));
    expect(resume).toEqual({ kind: "agent", drafts: 2 });
    expect(thread.comments.a[0].status).toBe("draft");
    expect(thread.comments.b.map((comment) => comment.status)).toEqual(["draft", "done"]);
  });

  it("reports an interrupted render and transcribe", () => {
    const render = fromStatus(status({
      phase: "board", brief: "b", strategy_approved: true, edl, interrupted: { cmd: "render", mode: "final" },
    }));
    expect(render.resume).toEqual({ kind: "render", mode: "final" });
    const ingest = fromStatus(status({ phase: "analyze", brief: "b", interrupted: { cmd: "ingest", mode: null } }));
    expect(ingest.resume).toEqual({ kind: "ingest" });
    expect(stepIndex(ingest.project.phase)).toBe(2);
  });

  it("keeps the storyboard visible when the agent left an invalid edl", () => {
    const { project } = fromStatus(status({
      phase: "agent", brief: "b", strategy_approved: true, edl: { ok: false, ranges: 3, errors: ["lỗi"] },
    }));
    expect(showsBoard(project)).toBe(true);
  });

  it("rebuilds rendered outputs for old folders", () => {
    const { thread } = fromStatus(status({
      phase: "exported", brief: "b", strategy: "s", strategy_approved: true, edl,
      preview: "/f/edit/preview.mp4", final: "/f/edit/final.mp4",
    }));
    expect(thread.items.map((item) => item.k)).toEqual(["user", "strategy", "ev", "ready", "final"]);
    expect(stepIndex("exported")).toBe(5);
  });
});

describe("threadReducer", () => {
  it("adds, edits, sends, and clears comments", () => {
    let thread = emptyThread();
    thread = threadReducer(thread, { type: "addComment", key: "k", comment: { id: "1", text: "a", status: "draft" } });
    thread = threadReducer(thread, { type: "addComment", key: "k", comment: { id: "2", text: "b", status: "draft" } });
    thread = threadReducer(thread, { type: "editComment", key: "k", id: "1", text: "a2" });
    thread = threadReducer(thread, { type: "removeComment", key: "k", id: "2" });
    expect(thread.comments.k).toEqual([{ id: "1", text: "a2", status: "draft" }]);
    thread = threadReducer(thread, { type: "send" });
    expect(thread.comments.k[0].status).toBe("sent");
    thread = threadReducer(thread, { type: "unsend" });
    thread = threadReducer(thread, { type: "clearDrafts" });
    expect(thread.comments).toEqual({});
  });
});
