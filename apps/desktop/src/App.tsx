import { open } from "@tauri-apps/plugin-dialog";
import { useEffect, useState } from "react";
import {
  hasApiKey,
  mediaUrl,
  onSidecar,
  setApiKey,
  setMediaRoot,
  sidecar,
  type AgentInfo,
  type AgentPayload,
  type Deps,
  type Progress,
  type StoryboardData,
  type ThumbFrame,
  type Validation,
  type VideoItem,
  clearApiKey,
} from "./api";
import { Board } from "./Board";
import { questionFields, type Turn } from "./conversation";
import type { Range, Word } from "./storyboard";

const AGENT_KEY = "vlog-utils-agent";

function loginLabel(agent: AgentInfo): string {
  if (!agent.found) return agent.detail || "không có trên PATH";
  if (agent.logged_in === true) return "đã đăng nhập";
  if (agent.logged_in === false) return "chưa đăng nhập";
  return agent.detail || "không rõ đăng nhập";
}

function explain(error: string | undefined): string {
  if (!error) return "Lỗi không rõ";
  if (error === "strategy_required") {
    return "Agent ghi EDL trước khi chiến lược được duyệt. Bấm viết lại.";
  }
  return error;
}

export function App() {
  const [sidecarError, setSidecarError] = useState<string | null>(null);
  const [deps, setDeps] = useState<Deps | null>(null);
  const [provider, setProvider] = useState(localStorage.getItem(AGENT_KEY) || "claude");
  const [hasKey, setHasKey] = useState(false);
  const [keyDraft, setKeyDraft] = useState("");
  const [folder, setFolder] = useState<string | null>(null);
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [log, setLog] = useState<string[]>([]);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [turn, setTurn] = useState<Turn | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [rewrite, setRewrite] = useState("");
  const [blocked, setBlocked] = useState<string[]>([]);
  const [view, setView] = useState<"talk" | "board">("talk");
  const [ranges, setRanges] = useState<Range[]>([]);
  const [words, setWords] = useState<Record<string, Word[]>>({});
  const [durations, setDurations] = useState<Record<string, number>>({});
  const [frames, setFrames] = useState<{ index: number; url: string | null }[]>([]);
  const [validation, setValidation] = useState<Validation | null>(null);
  const [previewReady, setPreviewReady] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [finalPath, setFinalPath] = useState<string | null>(null);

  useEffect(() => {
    let unlisten: (() => void) | undefined;
    onSidecar((message) => {
      const line = message.data && "line" in message.data ? String(message.data.line ?? "") : "";
      if ((message.type === "log" || message.type === "stderr") && line) {
        setLog((prev) => [...prev.slice(-400), line]);
      }
      if (message.type === "progress" && message.data && "phase" in message.data) {
        const data = message.data as unknown as Progress;
        setProgress(data);
      }
    }).then((stop) => {
      unlisten = stop;
    }).catch((err: unknown) => {
      setSidecarError(err instanceof Error ? err.message : String(err));
    });
    sidecar("ping")
      .then(() => setSidecarError(null))
      .catch((err: unknown) => setSidecarError(err instanceof Error ? err.message : String(err)));
    hasApiKey().then(setHasKey).catch(() => setHasKey(false));
    sidecar("check_deps", { include_login: false }).then((result) => {
      if (result.ok && result.data) setDeps(result.data as unknown as Deps);
      else setError(result.error || "Không kiểm tra được ffmpeg và agent");
    }).catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
    return () => { unlisten?.(); };
  }, []);

  useEffect(() => {
    localStorage.setItem(AGENT_KEY, provider);
  }, [provider]);

  useEffect(() => {
    if (!deps) return;
    const current = deps.agents.find((agent) => agent.id === provider);
    if (current?.found) return;
    const first = deps.agents.find((agent) => agent.found);
    if (first) setProvider(first.id);
  }, [deps, provider]);

  async function chooseFolder() {
    let selected: string | string[] | null;
    try {
      selected = await open({ directory: true, multiple: false, title: "Chọn folder footage" });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      return;
    }
    if (typeof selected !== "string") return;
    setError(null);
    setFolder(selected);
    setView("talk");
    setTurn(null);
    setPreviewReady(false);
    setPreviewUrl(null);
    setFinalPath(null);
    await setMediaRoot(selected);
    const listed = await sidecar("inventory", { folder: selected });
    if (!listed.ok) {
      setError(listed.error || "Không đọc được folder");
      return;
    }
    const rows = (listed.data as { videos?: VideoItem[] } | undefined)?.videos || [];
    setVideos(rows);
  }

  async function saveKey() {
    const trimmed = keyDraft.trim();
    if (!trimmed) return;
    try {
      await setApiKey(trimmed);
      setKeyDraft("");
      setHasKey(true);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function applyPayload(resultOk: boolean, payload: AgentPayload | undefined, fallback?: string) {
    if (!payload) {
      if (!resultOk) setError(explain(fallback));
      return;
    }
    setTurn(payload.turn || null);
    setBlocked(payload.blocked ? payload.unexpected_writes || [] : []);
    if (payload.storyboard_ready) {
      setView("board");
      setError(null);
      await loadBoard();
      return;
    }
    setView("talk");
    if (!resultOk) setError(explain(payload.error || fallback));
    else setError(null);
  }

  async function runAgent(note = "", resetStrategy = false) {
    if (!folder) return;
    setBusy(true);
    setError(null);
    try {
      const result = await sidecar("agent_turn", {
        folder,
        provider,
        note,
        reset_strategy: resetStrategy,
      });
      await applyPayload(Boolean(result.ok), result.data as AgentPayload | undefined, result.error);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
      setProgress(null);
    }
  }

  async function start() {
    if (!folder) return;
    if (!selected?.found) {
      setError("Chưa có agent nào được chọn. Bật Claude, Codex hoặc Grok ở cột trái.");
      return;
    }
    if (deps && (!deps.ffmpeg.found || !deps.ffprobe.found)) {
      setError("Không thấy ffmpeg hoặc ffprobe. Cài bằng brew install ffmpeg rồi mở lại app.");
      return;
    }
    setBusy(true);
    setError(null);
    setLog([]);
    setView("talk");
    try {
      const typed = keyDraft.trim();
      if (typed) {
        await setApiKey(typed);
        setKeyDraft("");
        setHasKey(true);
      }
      const saved = await sidecar("save_brief", { folder, prompt });
      if (!saved.ok) throw new Error(saved.error || "Không lưu được prompt");
      const ingested = await sidecar("ingest", { folder });
      if (!ingested.ok) throw new Error(ingested.error || "Transcribe thất bại");
      const result = await sidecar("agent_turn", { folder, provider, note: "" });
      await applyPayload(Boolean(result.ok), result.data as AgentPayload | undefined, result.error);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
      setProgress(null);
    }
  }

  async function sendAnswers() {
    if (!folder || !turn || turn.kind !== "questions") return;
    const answers = questionFields(turn).map((question) => ({
      id: question.id,
      prompt: question.prompt,
      answer: drafts[question.id] || "",
    }));
    setBusy(true);
    try {
      const saved = await sidecar("save_answers", { folder, answers });
      if (!saved.ok) throw new Error(saved.error || "Không lưu được câu trả lời");
      await runAgent("Answers are in edit/agent/answers.json. Continue.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  async function approve() {
    if (!folder) return;
    setBusy(true);
    try {
      const approved = await sidecar("approve_strategy", { folder });
      if (!approved.ok) throw new Error(approved.error || "Không duyệt được");
      await runAgent("Strategy approved. Write edl.json and turn.json with kind edl.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  async function loadBoard() {
    if (!folder) return;
    const board = await sidecar("storyboard", { folder });
    if (!board.ok || !board.data) {
      setError(board.error || "Không mở được storyboard");
      setView("talk");
      return;
    }
    const data = board.data as unknown as StoryboardData;
    setRanges(data.edl.ranges || []);
    setWords(data.words || {});
    setDurations(data.durations || {});
    setValidation(data.validation);
    const thumbs = await sidecar("thumbs", { folder });
    const framesIn = ((thumbs.data as { frames?: ThumbFrame[] } | undefined)?.frames) || [];
    const withUrls = await Promise.all(framesIn.map(async (frame) => ({
      index: frame.index,
      url: frame.path ? await mediaUrl(frame.path) : null,
    })));
    setFrames(withUrls);
    setView("board");
  }

  async function persistRanges(next: Range[]) {
    if (!folder) return;
    const previous = ranges;
    setRanges(next);
    const result = await sidecar("save_ranges", { folder, ranges: next });
    if (!result.ok) {
      setRanges(previous);
      setError(result.error || "Không lưu được storyboard");
      return;
    }
    const data = result.data as { edl?: { ranges: Range[] }; validation?: Validation } | undefined;
    setRanges(data?.edl?.ranges || next);
    setValidation(data?.validation || null);
    setPreviewReady(false);
    setError(null);
  }

  async function render(mode: "preview" | "final") {
    if (!folder) return;
    setBusy(true);
    setError(null);
    try {
      const result = await sidecar("render", { folder, mode });
      if (!result.ok) {
        setError(result.error || "Render thất bại");
        return;
      }
      const output = String((result.data as { output?: string } | undefined)?.output || "");
      if (mode === "preview") {
        setPreviewReady(true);
        setPreviewUrl(`${await mediaUrl(output)}&v=${Date.now()}`);
      } else {
        setFinalPath(output);
      }
      const warnings = (result.data as { warnings?: string[] } | undefined)?.warnings || [];
      if (warnings.length) {
        setValidation((prev) => ({
          ok: prev?.ok ?? true,
          errors: prev?.errors ?? [],
          warnings,
        }));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
      setProgress(null);
    }
  }

  async function dismissWrites() {
    if (!folder) return;
    const result = await sidecar("dismiss_writes", { folder });
    await applyPayload(Boolean(result.ok), result.data as AgentPayload | undefined, result.error);
  }

  const selected = deps?.agents.find((agent) => agent.id === provider);
  const startBlocker = !folder
    ? "Chọn folder footage ở cột trái."
    : videos.length === 0
      ? "Không thấy video ngay trong folder đó. Cần .mp4, .mov, .mkv, .avi hoặc .m4v, không nằm trong thư mục con."
      : !prompt.trim()
        ? "Gõ prompt vào ô bên dưới. Dòng màu nhạt chỉ là gợi ý, không tính."
        : busy
          ? "Đang chạy."
          : "";
  const canStart = startBlocker === "";
  const fields = questionFields(turn);
  const answersReady = fields.every((question) => (drafts[question.id] || "").trim());

  return (
    <div className="app">
      <aside className="side">
        <div>
          <p className="eyebrow">Desktop</p>
          <h1>Vlog Utils</h1>
        </div>
        {sidecarError && <div className="banner">Sidecar không chạy. {sidecarError}</div>}
        <div className="stack">
          <strong>Agent</strong>
          <div className="agents">
            {(deps?.agents || []).map((agent) => (
              <label className="agent" key={agent.id}>
                <input
                  type="radio"
                  name="agent"
                  checked={provider === agent.id}
                  disabled={!agent.found}
                  onChange={() => setProvider(agent.id)}
                />
                <span>{agent.label}</span>
                <small>{loginLabel(agent)}</small>
              </label>
            ))}
          </div>
        </div>
        <div className="stack">
          <strong>ElevenLabs</strong>
          <p className="muted">{hasKey ? "Key đã lưu." : "Dán key rồi bấm Phân tích. Không cần bấm Lưu key trước."}</p>
          <input
            type="password"
            autoComplete="off"
            placeholder="Dán API key"
            value={keyDraft}
            onChange={(event) => setKeyDraft(event.target.value)}
          />
          <div className="row">
            <button type="button" onClick={() => void saveKey()} disabled={!keyDraft.trim()}>Lưu key</button>
            <button type="button" className="quiet" onClick={() => void clearApiKey().then(() => setHasKey(false))} disabled={!hasKey}>Xóa</button>
          </div>
        </div>
        <div className="stack">
          <strong>Máy</strong>
          <p className="muted">
            ffmpeg {deps?.ffmpeg.found ? "có" : "thiếu"} · ffprobe {deps?.ffprobe.found ? "có" : "thiếu"} · Python deps {deps?.python_deps ? "có" : "thiếu"}
          </p>
        </div>
        <div className="stack">
          <div className="row">
            <button type="button" onClick={() => void chooseFolder()}>Chọn folder</button>
          </div>
          {folder && <p className="muted">{folder}</p>}
          <ul className="videos">
            {videos.map((video) => (
              <li key={video.path}>
                <span>{video.name}</span>
                <span className="muted">{video.cached ? "có transcript" : "chưa transcribe"}</span>
              </li>
            ))}
          </ul>
        </div>
        <pre className="log">{log.join("\n")}</pre>
      </aside>
      <main className="main">
        {error && <div className="banner">{error}</div>}
        {progress && (
          <p className="muted">{progress.phase} {progress.done}/{progress.total}</p>
        )}
        {view === "talk" && (
          <section className="stack">
            <label className="field">
              Prompt
              <textarea
                value={prompt}
                placeholder="Vlog đi chợ, giữ những câu tự nhiên, cắt ờ ừ, khoảng một phút, phụ đề."
                onChange={(event) => setPrompt(event.target.value)}
              />
            </label>
            <div className="row">
              <button type="button" className="primary" disabled={!canStart} onClick={() => void start()}>
                Phân tích
              </button>
              <button type="button" disabled={!busy} onClick={() => void sidecar("cancel")}>Hủy</button>
            </div>
            {startBlocker && <p className="muted">{startBlocker}</p>}
            {blocked.length > 0 && (
              <div className="banner warn">
                Agent sửa file ngoài edit/: {blocked.join(", ")}
                <div className="row">
                  <button type="button" onClick={() => void dismissWrites()}>Bỏ qua và tiếp tục</button>
                  <button type="button" onClick={() => void runAgent("Rewrite only inside edit/.")}>Chạy lại</button>
                </div>
              </div>
            )}
            {turn?.kind === "questions" && (
              <div className="stack">
                <h2>Agent hỏi</h2>
                {fields.map((question) => (
                  <label className="field" key={question.id}>
                    {question.prompt}
                    <textarea
                      value={drafts[question.id] || ""}
                      onChange={(event) => setDrafts((prev) => ({ ...prev, [question.id]: event.target.value }))}
                    />
                  </label>
                ))}
                <button type="button" className="primary" disabled={busy || !answersReady} onClick={() => void sendAnswers()}>
                  Gửi trả lời
                </button>
              </div>
            )}
            {turn?.kind === "strategy" && (
              <div className="stack">
                <h2>Chiến lược</h2>
                <p>{turn.strategy}</p>
                <div className="row">
                  <button type="button" className="primary" disabled={busy} onClick={() => void approve()}>Duyệt chiến lược</button>
                </div>
                <label className="field">
                  Bảo viết lại
                  <textarea value={rewrite} onChange={(event) => setRewrite(event.target.value)} />
                </label>
                <button
                  type="button"
                  disabled={busy || !rewrite.trim()}
                  onClick={() => void runAgent(rewrite, true)}
                >
                  Viết lại
                </button>
              </div>
            )}
          </section>
        )}
        {view === "board" && (
          <Board
            ranges={ranges}
            words={words}
            durations={durations}
            frames={frames}
            validation={validation}
            busy={busy}
            previewReady={previewReady}
            previewUrl={previewUrl}
            finalPath={finalPath}
            onRanges={(next) => void persistRanges(next)}
            onPreview={() => void render("preview")}
            onFinal={() => void render("final")}
          />
        )}
      </main>
    </div>
  );
}
