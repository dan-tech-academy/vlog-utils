import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import type { Progress } from "../api";
import type { Question } from "../conversation";
import { fmt } from "../format";
import { Icon, type IconName } from "../icons";
import type { ThreadItem } from "../project";
import type { Busy } from "../ui";

export type LiveCard =
  | {
      kind: "questions";
      questions: Question[];
      answers: Record<string, string>;
      onAnswer: (id: string, text: string) => void;
      onSubmit: () => void;
    }
  | { kind: "strategy"; text: string; onApprove: () => void; onRevise: () => void }
  | { kind: "blocked"; files: string[]; onDismiss: () => void; onRerun: () => void }
  | { kind: "stalled"; title: string; message: string; action: string; onRun: () => void }
  | null;

export type ComposerConfig =
  | { kind: "note"; text: string }
  | {
      kind: "input";
      placeholder: string;
      button: string;
      icon: IconName;
      primary: boolean;
      hint: string;
      chips: string[];
      blocker: ReactNode;
      onSend: (text: string) => void;
    };

type Props = {
  agentLabel: string;
  items: ThreadItem[];
  live: LiveCard;
  busy: Busy | null;
  progress: Progress | null;
  locked: boolean;
  composer: ComposerConfig;
  draft: string;
  focusSignal: number;
  onDraft: (text: string) => void;
  onCancel: () => void;
  onOpenPlayer: () => void;
  onReveal: (path: string) => void;
};

function Elapsed({ since }: { since: number }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return <span className="mono el">{Math.max(0, Math.floor((now - since) / 1000))}s</span>;
}

function BusyCard({ busy, progress, onCancel }: { busy: Busy; progress: Progress | null; onCancel: () => void }) {
  let title = busy.title;
  let sub = busy.sub;
  let bar = <div className="bar indet"><i /></div>;
  if (busy.kind === "ingest" && progress?.phase === "transcribe" && progress.total > 0) {
    sub = `${progress.done}/${progress.total} video có transcript`;
    bar = <div className="bar"><i style={{ width: `${(progress.done / progress.total) * 100}%` }} /></div>;
  } else if (busy.kind === "ingest" && progress?.phase === "pack") {
    title = "Đóng gói transcript";
    sub = "transcripts/*.json → takes_packed.md";
  }
  return (
    <div className="busy" role="status">
      <span className="spin" />
      <div>
        <b>{title}</b>
        <small>{sub}</small>
        {bar}
      </div>
      <Elapsed since={busy.t0} />
      <button type="button" className="btn ghost sm" onClick={onCancel} disabled={busy.kind === "reset"}>
        Hủy
      </button>
    </div>
  );
}

function Item({ item, agentLabel, onOpenPlayer, onReveal }: {
  item: ThreadItem;
  agentLabel: string;
  onOpenPlayer: () => void;
  onReveal: (path: string) => void;
}) {
  switch (item.k) {
    case "user":
      return <div className="msg user"><p>{item.text}</p></div>;
    case "batch":
      return (
        <div className="msg user">
          <p className="bt">Góp ý {item.items.length} cảnh</p>
          <ul>
            {item.items.map((entry, index) => (
              <li key={index}><b>{entry.num}</b><span>{entry.text}</span></li>
            ))}
          </ul>
        </div>
      );
    case "ev":
      return (
        <div className={`ev ${item.tone || ""}`}>
          <Icon name={item.icon} />
          <span>{item.text}</span>
        </div>
      );
    case "divider":
      return <div className="divider">{item.text}</div>;
    case "qa":
      return (
        <div className="card">
          <div className="card-h">
            <Icon name="sparkle" />
            <b>{agentLabel} hỏi {item.items.length} câu trước khi cắt</b>
            <span className="tag ok"><Icon name="check" />Đã trả lời</span>
          </div>
          <div className="card-b">
            {item.items.map((entry, index) => (
              <div className="qa" key={index}>
                <p className="qp">{index + 1}. {entry.prompt}</p>
                <p>{entry.answer}</p>
              </div>
            ))}
          </div>
        </div>
      );
    case "strategy":
      return (
        <div className={`card ${item.status}`}>
          <div className="card-h">
            <Icon name="sparkle" />
            <b>Chiến lược đề xuất</b>
            {item.status === "approved"
              ? <span className="tag ok"><Icon name="check" />Đã duyệt</span>
              : <span className="tag">Đã thay</span>}
          </div>
          <div className="card-b"><p>{item.text}</p></div>
        </div>
      );
    case "ready":
      return (
        <div className="card success">
          <div className="card-h">
            <Icon name="check" />
            <b>Preview 720p sẵn sàng</b>
            {item.seconds > 0 && <span className="tag">{fmt(item.seconds)}</span>}
          </div>
          <div className="card-b"><p className="quiet">Đã grade và burn phụ đề. Xem lại trước khi xuất bản cuối.</p></div>
          <div className="card-f">
            <button type="button" className="btn sm" onClick={onOpenPlayer}><Icon name="play" small />Xem preview</button>
          </div>
        </div>
      );
    case "final":
      return (
        <div className="card success">
          <div className="card-h">
            <Icon name="check" />
            <b>Đã xuất final.mp4</b>
            <span className="tag ok">1080p</span>
          </div>
          <div className="card-b"><p className="path">{item.path}</p></div>
          <div className="card-f">
            <button type="button" className="btn sm" onClick={() => onReveal(item.path)}>
              <Icon name="external" small />Mở trong Finder
            </button>
          </div>
        </div>
      );
  }
}

function Live({ live, agentLabel, locked }: { live: NonNullable<LiveCard>; agentLabel: string; locked: boolean }) {
  if (live.kind === "questions") {
    const ready = live.questions.every((question) => (live.answers[question.id] || "").trim());
    return (
      <div className="card pending">
        <div className="card-h">
          <Icon name="sparkle" />
          <b>{agentLabel} hỏi {live.questions.length} câu trước khi cắt</b>
        </div>
        <div className="card-b">
          {live.questions.map((question, index) => (
            <label className="qf" key={question.id}>
              <span>{index + 1}. {question.prompt}</span>
              <textarea
                rows={2}
                value={live.answers[question.id] || ""}
                onChange={(event) => live.onAnswer(question.id, event.target.value)}
              />
            </label>
          ))}
        </div>
        <div className="card-f">
          <span className="hint">Trả lời đủ {live.questions.length} câu để tiếp tục</span>
          <button type="button" className="btn primary sm" disabled={!ready || locked} onClick={live.onSubmit}>
            Gửi trả lời
          </button>
        </div>
      </div>
    );
  }
  if (live.kind === "strategy") {
    return (
      <div className="card pending">
        <div className="card-h">
          <Icon name="sparkle" />
          <b>Chiến lược đề xuất</b>
          <span className="tag warn">Chờ bạn duyệt</span>
        </div>
        <div className="card-b"><p>{live.text}</p></div>
        <div className="card-f">
          <button type="button" className="btn ghost sm" disabled={locked} onClick={live.onRevise}>
            <Icon name="edit" small />Yêu cầu sửa
          </button>
          <button type="button" className="btn primary sm" disabled={locked} onClick={live.onApprove}>
            <Icon name="check" small />Duyệt và dựng
          </button>
        </div>
      </div>
    );
  }
  if (live.kind === "blocked") {
    return (
      <div className="card alert" role="alert">
        <div className="card-h">
          <Icon name="alert" />
          <b>Agent ghi file ra ngoài edit/</b>
        </div>
        <div className="card-b">
          <p>App đã chặn lại để giữ nguyên footage gốc. Các file bị đụng tới:</p>
          <ul className="files mono">
            {live.files.map((file) => <li key={file}>{file}</li>)}
          </ul>
        </div>
        <div className="card-f">
          <button type="button" className="btn ghost sm" disabled={locked} onClick={live.onDismiss}>Bỏ qua và tiếp tục</button>
          <button type="button" className="btn sm" disabled={locked} onClick={live.onRerun}>
            <Icon name="refresh" small />Chạy lại agent
          </button>
        </div>
      </div>
    );
  }
  return (
    <div className="card alert">
      <div className="card-h">
        <Icon name="alert" />
        <b>{live.title}</b>
      </div>
      <div className="card-b"><p>{live.message}</p></div>
      <div className="card-f">
        <button type="button" className="btn sm" disabled={locked} onClick={live.onRun}>
          <Icon name="refresh" small />{live.action}
        </button>
      </div>
    </div>
  );
}

export function AgentPanel(props: Props) {
  const threadRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const { busy, composer, draft } = props;
  const showBusy = busy && !busy.scenes;
  const scrollKey = `${props.items.length}|${busy?.kind ?? ""}|${props.live?.kind ?? ""}`;

  useEffect(() => {
    const thread = threadRef.current;
    if (thread) thread.scrollTop = thread.scrollHeight;
  }, [scrollKey]);

  useEffect(() => {
    if (props.focusSignal) inputRef.current?.focus();
  }, [props.focusSignal]);

  const empty = !props.items.length && !props.live && !showBusy;
  const canSend = composer.kind === "input" && !composer.blocker && !props.locked && draft.trim().length > 0;

  function send() {
    if (composer.kind === "input" && canSend) composer.onSend(draft.trim());
  }

  function onKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      send();
    }
  }

  return (
    <aside className="agent" aria-label="Trao đổi với agent">
      <div className="panel-h">
        <span>Trao đổi</span>
        <span className="who"><Icon name="sparkle" />{props.agentLabel}</span>
      </div>
      <div className="thread" ref={threadRef}>
        {empty ? (
          <div className="intro">
            <h3>Agent cắt, bạn duyệt.</h3>
            <p>Mô tả video bạn muốn ở ô bên dưới. App transcribe footage, agent đọc transcript rồi hỏi lại trước khi dựng storyboard.</p>
            <ol className="flow">
              <li><b>1</b>Transcribe lời thoại bằng ElevenLabs</li>
              <li><b>2</b>Agent hỏi vài câu về video</li>
              <li><b>3</b>Bạn duyệt chiến lược cắt</li>
              <li><b>4</b>Agent dựng storyboard, bạn góp ý từng cảnh</li>
              <li><b>5</b>Render preview, rồi xuất final.mp4</li>
            </ol>
          </div>
        ) : (
          <>
            {props.items.map((item, index) => (
              <Item
                key={index}
                item={item}
                agentLabel={props.agentLabel}
                onOpenPlayer={props.onOpenPlayer}
                onReveal={props.onReveal}
              />
            ))}
            {props.live && <Live live={props.live} agentLabel={props.agentLabel} locked={props.locked} />}
            {showBusy && <BusyCard busy={busy} progress={props.progress} onCancel={props.onCancel} />}
          </>
        )}
      </div>
      {composer.kind === "note" ? (
        <div className="composer-note">{composer.text}</div>
      ) : (
        <div className="composer">
          {composer.chips.length > 0 && (
            <div className="chips">
              {composer.chips.map((chip) => (
                <button
                  type="button"
                  className="chip"
                  key={chip}
                  disabled={props.locked}
                  onClick={() => props.onDraft(draft.trim() ? `${draft.trim()}, ${chip.toLowerCase()}` : chip)}
                >
                  + {chip}
                </button>
              ))}
            </div>
          )}
          <textarea
            ref={inputRef}
            value={draft}
            placeholder={composer.placeholder}
            disabled={props.locked}
            aria-label="Tin nhắn cho agent"
            onChange={(event) => props.onDraft(event.target.value)}
            onKeyDown={onKey}
          />
          <div className="composer-f">
            <span className="hint">{composer.hint}</span>
            <button
              type="button"
              className={composer.primary ? "btn primary" : "btn"}
              disabled={!canSend}
              onClick={send}
            >
              <Icon name={composer.icon} />
              {composer.button}
            </button>
          </div>
          {composer.blocker && <p className="blocker">{composer.blocker}</p>}
        </div>
      )}
    </aside>
  );
}
