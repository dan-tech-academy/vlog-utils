import { getCurrentWebview } from "@tauri-apps/api/webview";
import { open } from "@tauri-apps/plugin-dialog";
import { useEffect, useReducer, useRef, useState, type ReactNode } from "react";
import {
  clearApiKey,
  hasApiKey,
  mediaUrl,
  onSidecar,
  projectStatus,
  revealPath,
  setApiKey,
  setMediaRoot,
  sidecar,
  type AgentPayload,
  type ClipItem,
  type Deps,
  type Progress,
  type SidecarMessage,
  type StoryboardData,
  type Validation,
  type VideoItem,
} from "./api";
import { AgentPanel, type ComposerConfig, type LiveCard } from "./components/AgentPanel";
import { BatchBar } from "./components/BatchBar";
import { Console } from "./components/Console";
import { Footage } from "./components/Footage";
import { MainPane, type View } from "./components/MainPane";
import { AgentMenu, ProjectMenu } from "./components/Menus";
import { Notices, type NoticeItem } from "./components/Notices";
import { PlayerModal } from "./components/PlayerModal";
import { RestartSheet } from "./components/RestartSheet";
import { SettingsSheet } from "./components/SettingsSheet";
import { StatusBar } from "./components/StatusBar";
import { Storyboard, StoryboardSkeleton, type Compose, type Play } from "./components/Storyboard";
import { Toolbar } from "./components/Toolbar";
import { questionFields } from "./conversation";
import { fmt, folderName, pad2, shortPath } from "./format";
import {
  emptyThread,
  fromStatus,
  projectFrom,
  showsBoard,
  stepIndex,
  threadReducer,
  type Project,
  type Resume,
  type Thread,
  type ThreadItem,
} from "./project";
import {
  buildNote,
  cardKey,
  carryComments,
  diffRanges,
  draftsOf,
  quoteOf,
  type RangeDiff,
  type Words,
} from "./revise";
import { totalDuration, type Range } from "./storyboard";
import { videoStem, type Busy, type ClipMap, type ClipUrls, type Overlay } from "./ui";

const AGENT_KEY = "vlog-utils-agent";
const FOLDER_KEY = "vlog-utils-folder";
const CANCELLED = "đã hủy";
const BRIEF_CHIPS = ["Cắt ờ ừ", "Khoảng 1 phút", "16:9", "9:16", "Có phụ đề", "Tông ấm"];
const BOARD_CHIPS = ["Gọn hơn", "Nhịp nhanh hơn", "Bỏ đoạn lặp ý"];

type Board = { ranges: Range[]; words: Words; grade: string; validation: Validation };
type Failure = { text: string; detail?: string; retry?: { label: string; run: () => void } };
type AgentOpts = {
  title: string;
  sub?: string;
  resetStrategy?: boolean;
  scenes?: boolean;
  edl?: boolean;
  retry?: () => void;
};

function message(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

function explain(error: string | undefined): string {
  if (!error) return "Lỗi không rõ";
  if (error === "strategy_required") return "Agent ghi EDL trước khi chiến lược được duyệt. Chạy lại để agent đề xuất chiến lược.";
  if (error === "busy") return "Sidecar đang chạy việc khác. Đợi xong rồi thử lại.";
  return error;
}

function clip(text: string, limit: number): string {
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}

async function clipEntry(item: ClipItem): Promise<[string, ClipUrls] | null> {
  if (!item.source) return null;
  const [video, poster] = await Promise.all([
    item.clip ? mediaUrl(item.clip).catch(() => null) : Promise.resolve(null),
    item.poster ? mediaUrl(item.poster).catch(() => null) : Promise.resolve(null),
  ]);
  return [cardKey({ source: item.source, start: item.start, end: item.end }), { clip: video, poster }];
}

async function previewSrc(path: string): Promise<string> {
  return `${await mediaUrl(path)}&v=${Date.now()}`;
}

function revisionItems(agent: string, diff: RangeDiff, after: Range[], words: Words): ThreadItem[] {
  const parts: string[] = [];
  if (diff.changed) parts.push(`sửa ${diff.changed} cảnh`);
  if (diff.added.length) parts.push(`thêm ${diff.added.length} cảnh`);
  if (diff.removed.length) parts.push(`bỏ ${diff.removed.length} cảnh`);
  const items: ThreadItem[] = [{
    k: "ev",
    icon: parts.length ? "check" : "film",
    tone: "accent",
    text: parts.length
      ? `${agent} ${parts.join(", ")} · còn ${after.length} cảnh, ${fmt(totalDuration(after))}`
      : `${agent} giữ nguyên storyboard`,
  }];
  diff.removed.forEach(({ index, range }) => {
    const quote = quoteOf(range, words);
    items.push({
      k: "ev",
      icon: "trash",
      tone: "muted",
      text: `Bỏ cảnh ${pad2(index + 1)}${quote ? ` “${clip(quote, 60)}”` : ""}`,
    });
  });
  return items;
}

function savedTime(savedAt: number | undefined): string {
  if (!savedAt) return "";
  return new Date(savedAt).toLocaleString("vi-VN", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" });
}

export function App() {
  const [sidecarDown, setSidecarDown] = useState<string | null>(null);
  const [deps, setDeps] = useState<Deps | null>(null);
  const [provider, setProvider] = useState(localStorage.getItem(AGENT_KEY) || "claude");
  const [hasKey, setHasKey] = useState(false);
  const [checkingLogin, setCheckingLogin] = useState(false);

  const [folder, setFolder] = useState<string | null>(null);
  const [videos, setVideos] = useState<VideoItem[] | null>(null);
  const [posters, setPosters] = useState<Record<string, string>>({});
  const [project, setProject] = useState<Project | null>(null);
  const [thread, dispatch] = useReducer(threadReducer, undefined, emptyThread);
  const [resume, setResume] = useState<Resume | null>(null);

  const [board, setBoard] = useState<Board | null>(null);
  const [boardLoading, setBoardLoading] = useState(false);
  const [clips, setClips] = useState<ClipMap>({});
  const [clipsRunning, setClipsRunning] = useState(false);
  const [clipProgress, setClipProgress] = useState<Progress | null>(null);
  const [clipFailures, setClipFailures] = useState<string[]>([]);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  const [busy, setBusy] = useState<Busy | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [log, setLog] = useState<string[]>([]);

  const [view, setView] = useState<View>("board");
  const [overlay, setOverlay] = useState<Overlay>(null);
  const [consoleOpen, setConsoleOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [focusSignal, setFocusSignal] = useState(0);
  const [play, setPlay] = useState<Play | null>(null);
  const [compose, setCompose] = useState<Compose | null>(null);
  const [focusKey, setFocusKey] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const booted = useRef(false);
  const folderRef = useRef<string | null>(null);
  const threadRef = useRef<Thread>(thread);
  const threadFolder = useRef<string | null>(null);
  const loadedThread = useRef<Thread | null>(null);
  const pendingSave = useRef<{ folder: string; thread: Thread } | null>(null);
  const saveTimer = useRef<number | undefined>(undefined);
  const clipsActive = useRef(false);
  const clipsGen = useRef(0);
  const openRef = useRef<(path: string) => Promise<void>>(async () => undefined);

  folderRef.current = folder;
  threadRef.current = thread;

  const agent = deps?.agents.find((item) => item.id === provider);
  const agentLabel = agent?.label || "Agent";

  function note(line: string) {
    setLog((prev) => (prev.length > 600 ? [...prev.slice(-500), line] : [...prev, line]));
  }

  /** The sidecar runs one job at a time; queue here so quick calls wait instead of failing with busy. */
  function job(cmd: string, extra: Record<string, unknown> = {}): Promise<SidecarMessage> {
    const run = queue.current.then(async () => {
      for (let attempt = 0; ; attempt += 1) {
        const result = await sidecar(cmd, extra).catch(
          (err: unknown): SidecarMessage => ({ type: "result", ok: false, error: message(err) }),
        );
        if (result.error !== "busy" || attempt >= 40) return result;
        await new Promise((resolve) => window.setTimeout(resolve, 250));
      }
    });
    queue.current = run;
    return run;
  }

  async function saveThreadNow() {
    window.clearTimeout(saveTimer.current);
    const pending = pendingSave.current;
    pendingSave.current = null;
    if (!pending) return;
    await sidecar("save_thread", {
      folder: pending.folder,
      thread: { ...pending.thread, savedAt: Date.now() },
    }).catch(() => undefined);
  }

  useEffect(() => {
    const target = threadFolder.current;
    if (!target || thread === loadedThread.current) return;
    pendingSave.current = { folder: target, thread };
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => void saveThreadNow(), 500);
  }, [thread]);

  useEffect(() => {
    const flush = () => void saveThreadNow();
    window.addEventListener("beforeunload", flush);
    return () => window.removeEventListener("beforeunload", flush);
  }, []);

  useEffect(() => {
    let alive = true;
    let stop: (() => void) | undefined;
    onSidecar((msg) => {
      const data = msg.data as Record<string, unknown> | undefined;
      if ((msg.type === "log" || msg.type === "stderr") && typeof data?.line === "string" && data.line) {
        note(msg.type === "stderr" ? `[sidecar] ${data.line}` : data.line);
      } else if (msg.type === "progress" && data) {
        const next = data as unknown as Progress;
        if (next.phase === "clips") {
          clipsActive.current = next.done < next.total;
          setClipProgress(next);
        } else {
          setProgress(next);
        }
      } else if (msg.type === "clip" && data) {
        void clipEntry(data as unknown as ClipItem).then((entry) => {
          if (entry) setClips((prev) => ({ ...prev, [entry[0]]: entry[1] }));
        });
      }
    }).then((unlisten) => {
      if (alive) stop = unlisten;
      else unlisten();
    }).catch((err: unknown) => setSidecarDown(message(err)));
    return () => {
      alive = false;
      stop?.();
    };
  }, []);

  useEffect(() => {
    let alive = true;
    let stop: (() => void) | undefined;
    getCurrentWebview().onDragDropEvent((event) => {
      const payload = event.payload;
      if (payload.type === "enter" || payload.type === "over") setDragOver(true);
      else if (payload.type === "leave") setDragOver(false);
      else if (payload.type === "drop") {
        setDragOver(false);
        if (payload.paths[0]) void openRef.current(payload.paths[0]);
      }
    }).then((unlisten) => {
      if (alive) stop = unlisten;
      else unlisten();
    }).catch(() => undefined);
    return () => {
      alive = false;
      stop?.();
    };
  }, []);

  useEffect(() => {
    if (booted.current) return;
    booted.current = true;
    sidecar("ping")
      .then((result) => setSidecarDown(result.ok ? null : result.error || "Không phản hồi"))
      .catch((err: unknown) => setSidecarDown(message(err)));
    hasApiKey().then(setHasKey).catch(() => setHasKey(false));
    void job("check_deps", { include_login: false }).then((result) => {
      if (result.ok && result.data) setDeps(result.data as unknown as Deps);
    });
    const last = localStorage.getItem(FOLDER_KEY);
    if (last) void openFolder(last, true);
  }, []);

  useEffect(() => {
    localStorage.setItem(AGENT_KEY, provider);
  }, [provider]);

  useEffect(() => {
    if (!deps) return;
    if (deps.agents.find((item) => item.id === provider)?.found) return;
    const first = deps.agents.find((item) => item.found);
    if (first) setProvider(first.id);
  }, [deps, provider]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      if (overlay && overlay !== "player" && busy?.kind !== "reset") setOverlay(null);
      else if (!overlay && consoleOpen) setConsoleOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [overlay, busy, consoleOpen]);

  async function refresh(path: string): Promise<Project | null> {
    try {
      const next = projectFrom(await projectStatus(path));
      if (path === folderRef.current) setProject(next);
      return next;
    } catch (err) {
      setFailure({ text: "Không đọc được trạng thái dự án", detail: message(err) });
      return null;
    }
  }

  async function loadVideos(path: string) {
    const result = await job("inventory", { folder: path });
    if (path !== folderRef.current) return;
    if (!result.ok) {
      setVideos([]);
      setFailure({ text: "Không đọc được folder", detail: result.error });
      return;
    }
    const rows = (result.data as { videos?: VideoItem[] } | undefined)?.videos || [];
    setVideos(rows);
    const entries = await Promise.all(
      rows.map(async (row) => [row.path, row.poster ? await mediaUrl(row.poster).catch(() => "") : ""] as const),
    );
    setPosters(Object.fromEntries(entries.filter(([, url]) => url)));
  }

  async function loadBoard(path: string): Promise<StoryboardData | null> {
    setBoardLoading(true);
    const result = await job("storyboard", { folder: path });
    setBoardLoading(false);
    if (path !== folderRef.current) return null;
    if (!result.ok || !result.data) {
      setFailure({ text: "Không mở được storyboard", detail: result.error });
      return null;
    }
    const data = result.data as unknown as StoryboardData;
    setBoard({
      ranges: data.edl.ranges || [],
      words: data.words || {},
      grade: data.edl.grade || "",
      validation: data.validation,
    });
    return data;
  }

  async function makeClips(path: string) {
    const gen = ++clipsGen.current;
    setClipsRunning(true);
    setClipFailures([]);
    setClipProgress(null);
    const result = await job("clips", { folder: path });
    clipsActive.current = false;
    if (gen !== clipsGen.current) return;
    setClipsRunning(false);
    if (path !== folderRef.current) return;
    if (!result.ok) {
      if (result.error !== CANCELLED) setClipFailures([result.error || "Không tạo được clip"]);
      return;
    }
    const data = result.data as { clips?: ClipItem[]; failures?: string[] } | undefined;
    const entries = await Promise.all((data?.clips || []).map(clipEntry));
    setClips(Object.fromEntries(entries.filter((entry): entry is [string, ClipUrls] => entry !== null)));
    setClipFailures(data?.failures || []);
  }

  /** Clips run as a sidecar job too; stop them so agent and render calls do not wait behind them. */
  async function stopClips(): Promise<boolean> {
    if (!clipsActive.current) return false;
    await sidecar("cancel").catch(() => undefined);
    return true;
  }

  async function openFolder(path: string, fromBoot = false) {
    if (busy) {
      setFailure({ text: "Đợi việc đang chạy xong rồi mới đổi folder." });
      return;
    }
    try {
      await setMediaRoot(path);
    } catch {
      if (fromBoot) {
        localStorage.removeItem(FOLDER_KEY);
        setFailure({ text: `Không thấy folder lần trước (${shortPath(path)}). Chọn lại folder footage.` });
      } else {
        setFailure({ text: "Kéo vào một folder chứa video, không phải file lẻ." });
      }
      return;
    }
    await stopClips();
    await saveThreadNow();
    threadFolder.current = null;
    clipsGen.current += 1;
    setClipsRunning(false);
    setFailure(null);
    setResume(null);
    setBoard(null);
    setClips({});
    setClipFailures([]);
    setPreviewUrl(null);
    setPlay(null);
    setCompose(null);
    setDraft("");
    setOverlay(null);
    setProgress(null);
    setProject(null);
    setVideos(null);
    setPosters({});
    dispatch({ type: "load", thread: emptyThread() });
    folderRef.current = path;
    setFolder(path);
    localStorage.setItem(FOLDER_KEY, path);
    note(`[app] mở ${path}`);

    let loaded: ReturnType<typeof fromStatus>;
    try {
      loaded = fromStatus(await projectStatus(path));
    } catch (err) {
      setFailure({ text: "Không đọc được trạng thái dự án", detail: message(err) });
      await loadVideos(path);
      return;
    }
    loadedThread.current = loaded.thread;
    threadFolder.current = path;
    dispatch({ type: "load", thread: loaded.thread });
    setProject(loaded.project);
    setResume(loaded.resume);
    const onBoard = showsBoard(loaded.project);
    setView(onBoard ? "board" : "footage");
    if (onBoard) await loadBoard(path);
    if (loaded.project.preview) setPreviewUrl(await previewSrc(loaded.project.preview).catch(() => null));
    await loadVideos(path);
    if (onBoard) void makeClips(path);
  }
  openRef.current = openFolder;

  async function pickFolder() {
    let selected: string | string[] | null = null;
    try {
      selected = await open({ directory: true, multiple: false, title: "Chọn folder footage" });
    } catch (err) {
      setFailure({ text: "Không mở được hộp chọn folder", detail: message(err) });
      return;
    }
    if (typeof selected === "string") await openFolder(selected);
  }

  async function runAgent(path: string, text: string, opts: AgentOpts): Promise<AgentPayload | null> {
    const hadClips = await stopClips();
    setFailure(null);
    setResume(null);
    setBusy({ kind: "agent", title: opts.title, sub: opts.sub || "Thường mất 1–3 phút", t0: Date.now(), scenes: opts.scenes, edl: opts.edl });
    const result = await job("agent_turn", {
      folder: path,
      provider,
      note: text,
      reset_strategy: Boolean(opts.resetStrategy),
    });
    setBusy(null);
    setProgress(null);
    const payload = (result.data as AgentPayload | undefined) || null;
    await refresh(path);
    const ready = Boolean(result.ok && payload?.storyboard_ready);
    if (hadClips && !ready) void makeClips(path);
    if (result.error === CANCELLED) {
      dispatch({ type: "push", items: [{ k: "ev", icon: "x", text: "Đã hủy lượt agent", tone: "muted" }] });
      return null;
    }
    if (!result.ok) {
      if (!payload?.blocked) {
        setFailure({
          text: explain(payload?.error || result.error),
          retry: opts.retry ? { label: "Chạy lại", run: opts.retry } : undefined,
        });
      }
      return null;
    }
    return payload;
  }

  async function afterTurn(path: string, payload: AgentPayload | null) {
    if (!payload?.storyboard_ready) return;
    const data = await loadBoard(path);
    if (!data) return;
    const ranges = data.edl.ranges || [];
    dispatch({
      type: "push",
      items: [{ k: "ev", icon: "film", tone: "accent", text: `${agentLabel} dựng storyboard ${ranges.length} cảnh · ${fmt(totalDuration(ranges))}` }],
    });
    setView("board");
    void makeClips(path);
  }

  async function ask(path: string, text: string, opts: Partial<AgentOpts> = {}) {
    const payload = await runAgent(path, text, {
      title: `${agentLabel} đang làm việc`,
      ...opts,
      retry: () => void ask(path, text, opts),
    });
    await afterTurn(path, payload);
  }

  async function analyze(path: string) {
    setFailure(null);
    setResume(null);
    const pending = (videos || []).filter((video) => !video.cached).length;
    setBusy({
      kind: "ingest",
      title: pending ? "Transcribe footage" : "Đọc transcript có sẵn",
      sub: pending ? `${pending} video cần transcribe` : "Không tốn thêm tiền ElevenLabs",
      t0: Date.now(),
    });
    const result = await job("ingest", { folder: path });
    setBusy(null);
    setProgress(null);
    await loadVideos(path);
    if (result.error === CANCELLED) {
      dispatch({ type: "push", items: [{ k: "ev", icon: "x", text: "Đã hủy transcribe", tone: "muted" }] });
      await refresh(path);
      return;
    }
    if (!result.ok) {
      setFailure({ text: "Transcribe lỗi", detail: result.error, retry: { label: "Thử lại", run: () => void analyze(path) } });
      await refresh(path);
      return;
    }
    const data = result.data as { videos?: number; transcribed?: number } | undefined;
    dispatch({
      type: "push",
      items: [{
        k: "ev",
        icon: "wave",
        text: data?.transcribed
          ? `Transcribe xong ${data.transcribed} video · ${data.videos} video có transcript`
          : `Dùng transcript có sẵn của ${data?.videos ?? 0} video`,
      }],
    });
    await ask(path, "", { title: `${agentLabel} đang đọc transcript` });
  }

  async function startBrief(text: string) {
    if (!folder) return;
    const path = folder;
    setDraft("");
    dispatch({ type: "push", items: [{ k: "user", text }] });
    const saved = await job("save_brief", { folder: path, prompt: text });
    if (!saved.ok) {
      setFailure({ text: "Không lưu được brief", detail: saved.error });
      return;
    }
    await refresh(path);
    await analyze(path);
  }

  async function submitAnswers() {
    const turn = project?.turn;
    if (!folder || turn?.kind !== "questions") return;
    const path = folder;
    const answers = questionFields(turn).map((question) => ({
      id: question.id,
      prompt: question.prompt,
      answer: (thread.answers[question.id] || "").trim(),
    }));
    const saved = await job("save_answers", { folder: path, answers });
    if (!saved.ok) {
      setFailure({ text: "Không lưu được câu trả lời", detail: saved.error });
      return;
    }
    dispatch({ type: "push", items: [{ k: "qa", items: answers.map(({ prompt, answer }) => ({ prompt, answer })) }] });
    dispatch({ type: "clearAnswers" });
    await ask(path, "Answers are in edit/agent/answers.json. Continue.", { title: `${agentLabel} đang đọc câu trả lời` });
  }

  async function build(path: string) {
    setView("board");
    await ask(path, "Strategy approved. Write edl.json and turn.json with kind edl.", {
      title: `${agentLabel} đang dựng storyboard`,
      sub: "Viết edl.json theo chiến lược đã duyệt",
      edl: true,
    });
  }

  async function approve() {
    if (!folder || !project) return;
    const path = folder;
    const strategy = project.strategy;
    const approved = await job("approve_strategy", { folder: path });
    if (!approved.ok) {
      setFailure({ text: "Không duyệt được chiến lược", detail: approved.error });
      return;
    }
    dispatch({ type: "push", items: [{ k: "strategy", text: strategy, status: "approved" }] });
    await build(path);
  }

  async function reviseStrategy(text: string) {
    if (!folder || !project) return;
    setDraft("");
    dispatch({ type: "push", items: [{ k: "strategy", text: project.strategy, status: "replaced" }, { k: "user", text }] });
    await ask(folder, text, { title: `${agentLabel} đang viết lại chiến lược`, resetStrategy: true });
  }

  async function dismissWrites() {
    if (!folder) return;
    const path = folder;
    const result = await job("dismiss_writes", { folder: path });
    await refresh(path);
    const payload = (result.data as AgentPayload | undefined) || null;
    if (!result.ok) {
      setFailure({ text: explain(payload?.error || result.error) });
      return;
    }
    await afterTurn(path, payload);
  }

  async function sendRevision(general = "") {
    if (!folder || !board || busy) return;
    const path = folder;
    const before = board.ranges;
    const words = board.words;
    const comments = threadRef.current.comments;
    const drafts = draftsOf(before, comments);
    let text: string;
    let items: ThreadItem[];
    let title: string;
    if (general) {
      text = `${general}\n\nUpdate edit/edl.json for this request and reply {"kind":"edl"}.`;
      items = [{ k: "user", text: general }];
      title = `${agentLabel} đang sửa storyboard`;
    } else {
      if (!drafts.length) return;
      text = buildNote(before, comments, words);
      items = [{ k: "batch", items: drafts.map((item) => ({ num: pad2(item.index + 1), text: item.comment.text })) }];
      title = `${agentLabel} đang sửa ${new Set(drafts.map((item) => item.index)).size} cảnh`;
    }
    setDraft("");
    setCompose(null);
    setPlay(null);
    dispatch({ type: "push", items });
    if (!general) dispatch({ type: "send" });
    const payload = await runAgent(path, text, {
      title,
      sub: "Agent đọc góp ý rồi viết lại edl.json",
      scenes: true,
      retry: general ? () => void sendRevision(general) : undefined,
    });
    if (!payload?.storyboard_ready) {
      dispatch({ type: "unsend" });
      return;
    }
    const data = await loadBoard(path);
    if (!data) {
      dispatch({ type: "unsend" });
      return;
    }
    const after = data.edl.ranges || [];
    const allWords = { ...words, ...(data.words || {}) };
    const diff = diffRanges(before, after, allWords);
    dispatch({
      type: "revised",
      comments: carryComments(before, after, diff, threadRef.current.comments),
      changed: diff.labels,
      items: revisionItems(agentLabel, diff, after, allWords),
    });
    void makeClips(path);
  }

  async function render(mode: "preview" | "final") {
    if (!folder || busy) return;
    const path = folder;
    const hadClips = await stopClips();
    setFailure(null);
    setResume(null);
    setBusy({
      kind: "render",
      mode,
      title: mode === "preview" ? "Render preview 720p" : "Xuất final 1080p",
      sub: "Cắt, nối, grade và burn phụ đề",
      t0: Date.now(),
    });
    const result = await job("render", { folder: path, mode });
    setBusy(null);
    setProgress(null);
    if (result.error === CANCELLED) {
      dispatch({ type: "push", items: [{ k: "ev", icon: "x", text: "Đã hủy render", tone: "muted" }] });
    } else if (!result.ok) {
      setFailure({
        text: mode === "preview" ? "Render preview lỗi" : "Xuất final lỗi",
        detail: result.error,
        retry: { label: "Render lại", run: () => void render(mode) },
      });
    } else {
      const data = result.data as { output?: string; warnings?: string[] } | undefined;
      const output = String(data?.output || "");
      const items: ThreadItem[] = [];
      if (mode === "preview") {
        setPreviewUrl(await previewSrc(output).catch(() => null));
        items.push({ k: "ready", seconds: totalDuration(board?.ranges || []) });
      } else {
        items.push({ k: "final", path: output });
      }
      (data?.warnings || []).forEach((warning) => items.push({ k: "ev", icon: "alert", text: warning, tone: "muted" }));
      dispatch({ type: "push", items });
    }
    await refresh(path);
    if (hadClips) void makeClips(path);
  }

  async function restart() {
    if (!folder) return;
    const path = folder;
    await stopClips();
    await saveThreadNow();
    threadFolder.current = null;
    setBusy({ kind: "reset", title: "Đang cất bản cũ", sub: "edit/archive/", t0: Date.now() });
    const result = await job("reset_project", { folder: path });
    setBusy(null);
    if (!result.ok) {
      threadFolder.current = path;
      setOverlay(null);
      setFailure({ text: "Không làm lại từ đầu được", detail: result.error });
      return;
    }
    const archive = (result.data as { archive?: string | null } | undefined)?.archive ?? null;
    const fresh = emptyThread();
    loadedThread.current = fresh;
    dispatch({ type: "load", thread: fresh });
    clipsGen.current += 1;
    setClipsRunning(false);
    setBoard(null);
    setClips({});
    setClipFailures([]);
    setPreviewUrl(null);
    setCompose(null);
    setPlay(null);
    setDraft("");
    setFailure(null);
    const next = await refresh(path);
    threadFolder.current = path;
    setResume({ kind: "restarted", archive, transcripts: next?.transcripts.done ?? 0 });
    setView("footage");
    setOverlay(null);
    note(`[app] làm lại từ đầu, bản cũ ở ${archive || "(không có gì để cất)"}`);
  }

  async function reveal(path: string) {
    try {
      await revealPath(path);
    } catch (err) {
      setFailure({ text: "Không mở được Finder", detail: message(err) });
    }
  }

  async function checkLogin() {
    setCheckingLogin(true);
    const result = await job("check_deps", { include_login: true });
    setCheckingLogin(false);
    if (result.ok && result.data) setDeps(result.data as unknown as Deps);
    else setFailure({ text: "Không kiểm tra được agent", detail: result.error });
  }

  async function saveKey(key: string) {
    try {
      await setApiKey(key);
      setHasKey(true);
    } catch (err) {
      setFailure({ text: "Không lưu được ElevenLabs key", detail: message(err) });
    }
  }

  function cancel() {
    void sidecar("cancel").catch(() => undefined);
  }

  function flash(key: string) {
    setFocusKey(key);
    window.setTimeout(() => setFocusKey((current) => (current === key ? null : current)), 1400);
  }

  function commentOn(index: number) {
    const range = board?.ranges[index];
    if (!range) return;
    const key = cardKey(range);
    setOverlay(null);
    setView("board");
    setCompose({ key, editingId: null });
    flash(key);
  }

  function submitComment(key: string, text: string, editingId: string | null) {
    if (editingId) dispatch({ type: "editComment", key, id: editingId, text });
    else dispatch({ type: "addComment", key, comment: { id: crypto.randomUUID(), text, status: "draft" } });
    setCompose(null);
  }

  function colorOf(source: string): string {
    const index = (videos || []).findIndex((video) => videoStem(video.name) === source);
    return `var(--s${((index >= 0 ? index : 0) % 6) + 1})`;
  }

  const phase = project?.phase ?? "brief";
  const rendering = busy?.kind === "render" ? busy.mode ?? null : null;
  const ranges = board?.ranges || [];
  const drafts = board ? draftsOf(ranges, thread.comments) : [];
  const freshPreview = project?.preview && previewUrl ? previewUrl : null;
  const hasClip = Object.values(clips).some((media) => media.clip);
  const shownView: View = board || busy?.edl || boardLoading ? view : "footage";

  function briefBlocker(): ReactNode {
    if (!deps) return "Đang kiểm tra máy…";
    if (!agent?.found) {
      return (
        <>
          Chưa có agent. Cài Claude Code, Codex hoặc Grok CLI rồi{" "}
          <button type="button" onClick={() => setOverlay("settings")}>kiểm tra lại</button>.
        </>
      );
    }
    if (!deps.ffmpeg.found || !deps.ffprobe.found) return "Thiếu ffmpeg. Cài bằng brew install ffmpeg rồi mở lại app.";
    if (videos === null) return "Đang đọc folder…";
    if (!videos.length) return "Folder này không có video ở cấp trên cùng (.mp4, .mov, .mkv, .avi, .m4v).";
    if (videos.some((video) => !video.cached) && !hasKey) {
      return (
        <>
          Cần ElevenLabs key để transcribe.{" "}
          <button type="button" onClick={() => setOverlay("settings")}>Mở Cài đặt</button>
        </>
      );
    }
    return null;
  }

  function composer(): ComposerConfig {
    if (!folder) return { kind: "note", text: "Mở folder footage để bắt đầu." };
    if (phase === "brief") {
      return {
        kind: "input",
        placeholder: "Mô tả video bạn muốn: nội dung, độ dài, khung hình, phụ đề…",
        button: "Phân tích",
        icon: "sparkle",
        primary: true,
        hint: "⌘↵ để gửi",
        chips: BRIEF_CHIPS,
        blocker: briefBlocker(),
        onSend: (text) => void startBrief(text),
      };
    }
    if (phase === "strategy") {
      return {
        kind: "input",
        placeholder: "Muốn đổi gì trong chiến lược? Agent sẽ viết lại.",
        button: "Yêu cầu sửa",
        icon: "edit",
        primary: false,
        hint: "Hoặc bấm Duyệt và dựng ở trên",
        chips: [],
        blocker: null,
        onSend: (text) => void reviseStrategy(text),
      };
    }
    if (board && (phase === "board" || phase === "preview" || phase === "exported")) {
      return {
        kind: "input",
        placeholder: "Yêu cầu chung cho cả video, ví dụ: gọn còn 45 giây",
        button: "Gửi",
        icon: "arrowUp",
        primary: false,
        hint: "Góp ý từng cảnh thì bấm vào thẻ bên trái",
        chips: BOARD_CHIPS,
        blocker: drafts.length ? `Còn ${drafts.length} góp ý theo cảnh chưa gửi. Gửi hoặc bỏ chúng trước.` : null,
        onSend: (text) => void sendRevision(text),
      };
    }
    if (phase === "questions") return { kind: "note", text: "Trả lời các câu hỏi ở trên để agent tiếp tục." };
    if (phase === "blocked") return { kind: "note", text: "Xử lý các file agent ghi ra ngoài edit/ ở trên trước." };
    if (phase === "analyze") return { kind: "note", text: "Transcribe xong thì agent mới đọc được footage." };
    return { kind: "note", text: "Đợi agent trả lời." };
  }

  function liveCard(): LiveCard {
    if (!folder || !project || busy) return null;
    const path = folder;
    if (phase === "blocked") {
      return {
        kind: "blocked",
        files: project.blocked,
        onDismiss: () => void dismissWrites(),
        onRerun: () => void ask(path, "Your last turn wrote files outside edit/. Redo it and write only inside edit/.", {
          title: `${agentLabel} đang chạy lại`,
        }),
      };
    }
    if (phase === "questions" && project.turn?.kind === "questions") {
      return {
        kind: "questions",
        questions: questionFields(project.turn),
        answers: thread.answers,
        onAnswer: (id, text) => dispatch({ type: "answer", id, text }),
        onSubmit: () => void submitAnswers(),
      };
    }
    if (phase === "strategy" && project.strategy) {
      return {
        kind: "strategy",
        text: project.strategy,
        onApprove: () => void approve(),
        onRevise: () => setFocusSignal((value) => value + 1),
      };
    }
    if (phase === "analyze" && resume?.kind !== "ingest") {
      return {
        kind: "stalled",
        title: "Chưa transcribe xong",
        message: `${project.transcripts.done}/${project.transcripts.total} video có transcript.`,
        action: "Tiếp tục",
        onRun: () => void analyze(path),
      };
    }
    if (phase === "agent") {
      const errors = project.edl && !project.edl.ok ? project.edl.errors : null;
      if (project.approved && errors) {
        return {
          kind: "stalled",
          title: "Storyboard của agent bị lỗi",
          message: errors.slice(0, 3).join(" · ") || "edl.json không hợp lệ",
          action: "Bảo agent sửa",
          onRun: () => void ask(path, `edit/edl.json fails validation: ${errors.join("; ")}. Fix it and reply {"kind":"edl"}.`, {
            title: `${agentLabel} đang sửa edl.json`,
            edl: true,
          }),
        };
      }
      if (project.approved) {
        return {
          kind: "stalled",
          title: "Chưa có storyboard",
          message: "Chiến lược đã duyệt nhưng agent chưa ghi edl.json.",
          action: "Dựng storyboard",
          onRun: () => void build(path),
        };
      }
      return {
        kind: "stalled",
        title: "Agent chưa trả lời",
        message: "Lượt trước không ra câu hỏi hay chiến lược nào.",
        action: "Chạy lại agent",
        onRun: () => void ask(path, "", { title: `${agentLabel} đang đọc transcript` }),
      };
    }
    return null;
  }

  function notices(): NoticeItem[] {
    const items: NoticeItem[] = [];
    if (sidecarDown) {
      items.push({ id: "sidecar", tone: "err", icon: "alert", body: <><b>Sidecar không chạy.</b> App không gọi được phần Python.</>, detail: sidecarDown });
    }
    if (deps && (!deps.ffmpeg.found || !deps.ffprobe.found)) {
      items.push({
        id: "ffmpeg",
        tone: "warn",
        icon: "alert",
        body: <>Không thấy <b>ffmpeg</b>. Cài bằng <span className="mono">brew install ffmpeg</span> rồi mở lại app.</>,
      });
    }
    if (failure) {
      const retry = failure.retry;
      items.push({
        id: "failure",
        tone: "err",
        icon: "alert",
        body: failure.text,
        detail: failure.detail,
        actions: retry
          ? [{ label: retry.label, icon: "refresh", disabled: Boolean(busy), run: () => { setFailure(null); retry.run(); } }]
          : undefined,
        onDismiss: () => setFailure(null),
      });
    }
    if (resume && folder) {
      const dismiss = () => setResume(null);
      if (resume.kind === "resumed") {
        const when = savedTime(resume.savedAt);
        items.push({
          id: "resume",
          tone: "info",
          icon: "refresh",
          body: (
            <>
              Mở lại đúng chỗ bạn dừng{when ? ` lúc ${when}` : ""}.
              {resume.drafts > 0 && <> <b>{resume.drafts} góp ý chưa gửi</b> vẫn còn trên thẻ.</>}
            </>
          ),
          onDismiss: dismiss,
        });
      } else if (resume.kind === "agent") {
        items.push({
          id: "resume",
          tone: "warn",
          icon: "alert",
          body: (
            <>
              Lượt agent trước bị ngắt khi app đóng.
              {resume.drafts > 0 ? <> <b>{resume.drafts} góp ý</b> quay lại trạng thái chưa gửi.</> : " Chạy lại khi sẵn sàng."}
            </>
          ),
          onDismiss: dismiss,
        });
      } else if (resume.kind === "render") {
        const mode = resume.mode;
        items.push({
          id: "resume",
          tone: "warn",
          icon: "alert",
          body: mode === "preview" ? "Render preview bị ngắt khi app đóng." : "Xuất final bị ngắt khi app đóng.",
          actions: [{ label: "Render lại", icon: "refresh", disabled: Boolean(busy) || !board, run: () => void render(mode) }],
          onDismiss: dismiss,
        });
      } else if (resume.kind === "ingest") {
        const path = folder;
        items.push({
          id: "resume",
          tone: "warn",
          icon: "alert",
          body: `Transcribe bị ngắt khi app đóng, mới xong ${project?.transcripts.done ?? 0}/${project?.transcripts.total ?? 0} video. Video đã xong không phải làm lại.`,
          actions: [{ label: "Tiếp tục", icon: "play", disabled: Boolean(busy), run: () => void analyze(path) }],
          onDismiss: dismiss,
        });
      } else {
        const archive = resume.archive;
        items.push({
          id: "resume",
          tone: "info",
          icon: "check",
          body: (
            <>
              {archive ? <>Đã cất bản cũ vào <span className="mono">{shortPath(archive)}</span>. </> : "Không có gì để cất. "}
              Giữ transcript của {resume.transcripts} video. Viết brief mới ở khung bên phải.
            </>
          ),
          actions: archive ? [{ label: "Mở trong Finder", icon: "external", ghost: true, run: () => void reveal(archive) }] : undefined,
          onDismiss: dismiss,
        });
      }
    }
    if (board && !board.validation.ok) {
      items.push({ id: "edl", tone: "err", icon: "alert", body: "EDL có lỗi nên chưa render được.", detail: board.validation.errors.join("\n") });
    }
    if (clipFailures.length && folder) {
      const path = folder;
      items.push({
        id: "clips",
        tone: "warn",
        icon: "alert",
        body: "Không tạo được clip cho một số cảnh. Thẻ vẫn góp ý được.",
        detail: clipFailures.join("\n"),
        actions: [{ label: "Thử lại", icon: "refresh", disabled: clipsRunning || Boolean(busy), run: () => void makeClips(path) }],
        onDismiss: () => setClipFailures([]),
      });
    }
    if (phase === "exported" && project?.final && !busy) {
      const output = project.final;
      items.push({
        id: "final",
        tone: "info",
        icon: "check",
        body: <>Đã xuất <span className="mono">{shortPath(output)}</span></>,
        actions: [{ label: "Mở trong Finder", icon: "external", run: () => void reveal(output) }],
      });
    }
    return items;
  }

  function renderBlock(): string | null {
    if (busy) return "Đang chạy việc khác";
    if (board && !board.validation.ok) return "EDL có lỗi, xem thông báo phía trên";
    return null;
  }

  function exportBlock(): string | null {
    if (busy) return "Đang chạy việc khác";
    if (!project?.preview) return "Render preview và xem lại trước khi xuất";
    return null;
  }

  let statusText = !folder ? "Chưa mở folder" : agent?.found ? `${agent.label} sẵn sàng` : "Chưa có agent";
  let statusTone: "ok" | "unk" | "err" | "off" = agent?.found ? "ok" : "off";
  if (sidecarDown) {
    statusText = "Sidecar không chạy";
    statusTone = "err";
  } else if (busy) {
    statusText = busy.title;
    statusTone = "unk";
  } else if (clipsRunning) {
    statusText = clipProgress?.total ? `Đang tạo clip ${clipProgress.done}/${clipProgress.total}` : "Đang tạo clip";
    statusTone = "unk";
  }

  const stat = board
    ? `${fmt(totalDuration(ranges))}${clipsRunning && clipProgress?.total ? ` · clip ${clipProgress.done}/${clipProgress.total}` : ""}`
    : null;

  let body: ReactNode;
  if (shownView === "board" && board) {
    body = (
      <Storyboard
        ranges={ranges}
        words={board.words}
        colorOf={colorOf}
        clips={clips}
        clipsRunning={clipsRunning}
        comments={thread.comments}
        changed={thread.changed}
        revising={Boolean(busy?.scenes)}
        locked={busy?.kind === "agent" || busy?.kind === "reset"}
        play={play}
        compose={compose}
        focusKey={focusKey}
        onPlay={(key) => setPlay((current) => (current?.key === key ? { key, playing: !current.playing } : { key, playing: true }))}
        onEnded={() => setPlay((current) => (current ? { ...current, playing: false } : null))}
        onCompose={setCompose}
        onSubmit={submitComment}
        onDelete={(key, id) => dispatch({ type: "removeComment", key, id })}
      />
    );
  } else if (shownView === "board") {
    body = <StoryboardSkeleton />;
  } else {
    body = <Footage videos={videos || []} posters={posters} ranges={ranges} transcribing={busy?.kind === "ingest"} />;
  }

  const sceneSet = new Set(drafts.map((item) => item.index)).size;
  const outputs = [
    project?.preview || project?.previewStale ? "preview.mp4" : "",
    project?.final ? "final.mp4" : "",
  ].filter(Boolean);

  return (
    <div className="app">
      <Toolbar
        folder={folder}
        step={stepIndex(folder ? phase : "empty", rendering)}
        agent={agent}
        projectMenuOpen={overlay === "projmenu"}
        agentMenuOpen={overlay === "agentmenu"}
        consoleOpen={consoleOpen}
        onProjectMenu={() => setOverlay(overlay === "projmenu" ? null : "projmenu")}
        onAgentMenu={() => setOverlay(overlay === "agentmenu" ? null : "agentmenu")}
        onConsole={() => setConsoleOpen((value) => !value)}
        onSettings={() => setOverlay("settings")}
      />
      <div className="workspace">
        <MainPane
          folder={folder}
          view={shownView}
          sceneCount={board ? ranges.length : null}
          videoCount={videos?.length ?? 0}
          stat={stat}
          stale={Boolean(project?.previewStale)}
          previewReady={Boolean(project?.preview)}
          rendering={rendering}
          canPlay={ranges.length > 0 && (Boolean(freshPreview) || hasClip)}
          renderBlock={renderBlock()}
          exportBlock={exportBlock()}
          dragOver={dragOver}
          notices={<Notices items={notices()} />}
          overlay={
            board && shownView === "board" ? (
              <BatchBar
                drafts={drafts.length}
                scenes={sceneSet}
                revising={busy?.scenes ? busy.title : null}
                blocked={busy ? "Đợi việc đang chạy xong" : !agent?.found ? "Chưa có agent" : null}
                onSend={() => void sendRevision()}
                onClear={() => dispatch({ type: "clearDrafts" })}
                onCancel={cancel}
              />
            ) : null
          }
          onView={setView}
          onPick={() => void pickFolder()}
          onPlayer={() => setOverlay("player")}
          onPreview={() => void render("preview")}
          onExport={() => void render("final")}
        >
          {body}
        </MainPane>
        <AgentPanel
          agentLabel={agentLabel}
          items={thread.items}
          live={liveCard()}
          busy={busy}
          progress={progress}
          locked={Boolean(busy)}
          composer={composer()}
          draft={draft}
          focusSignal={focusSignal}
          onDraft={setDraft}
          onCancel={cancel}
          onOpenPlayer={() => setOverlay("player")}
          onReveal={(path) => void reveal(path)}
        />
      </div>
      <StatusBar
        text={statusText}
        tone={statusTone}
        hasKey={hasKey}
        deps={deps}
        folder={folder}
        onConsole={() => setConsoleOpen((value) => !value)}
      />
      <Console open={consoleOpen} lines={log} onClose={() => setConsoleOpen(false)} />
      {overlay === "projmenu" && folder && (
        <ProjectMenu
          folder={folder}
          canRestart={phase !== "brief" && !busy}
          onOpenOther={() => {
            setOverlay(null);
            void pickFolder();
          }}
          onRestart={() => setOverlay("restart")}
          onReveal={() => {
            setOverlay(null);
            void reveal(folder);
          }}
          onClose={() => setOverlay(null)}
        />
      )}
      {overlay === "agentmenu" && (
        <AgentMenu
          agents={deps?.agents || []}
          provider={provider}
          onPick={(id) => {
            setProvider(id);
            setOverlay(null);
          }}
          onSettings={() => setOverlay("settings")}
          onClose={() => setOverlay(null)}
        />
      )}
      {overlay === "settings" && (
        <SettingsSheet
          deps={deps}
          provider={provider}
          hasKey={hasKey}
          checkingLogin={checkingLogin}
          onProvider={setProvider}
          onSaveKey={saveKey}
          onClearKey={() => void clearApiKey().then(() => setHasKey(false)).catch((err: unknown) => {
            setFailure({ text: "Không xóa được key", detail: message(err) });
          })}
          onCheckLogin={() => void checkLogin()}
          onClose={() => setOverlay(null)}
        />
      )}
      {overlay === "restart" && folder && (
        <RestartSheet
          folder={folderName(folder)}
          transcripts={project?.transcripts.done ?? 0}
          scenes={board?.ranges.length ?? project?.edl?.ranges ?? 0}
          outputs={outputs}
          working={busy?.kind === "reset"}
          onConfirm={() => void restart()}
          onClose={() => {
            if (busy?.kind !== "reset") setOverlay(null);
          }}
        />
      )}
      {overlay === "player" && board && (
        <PlayerModal
          ranges={ranges}
          clips={clips}
          previewUrl={freshPreview}
          grade={board.grade}
          onClose={() => setOverlay(null)}
          onComment={commentOn}
        />
      )}
    </div>
  );
}
