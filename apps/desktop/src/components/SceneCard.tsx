import { useEffect, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import { fmt, pad2 } from "../format";
import { Icon } from "../icons";
import { keptWords, type Comment, type Words } from "../revise";
import type { Range } from "../storyboard";
import type { ClipUrls } from "../ui";

const COMMENT_CHIPS = ["Ngắn lại", "Bỏ cảnh này", "Giữ thêm ở cuối", "Đổi take khác"];

type Props = {
  index: number;
  range: Range;
  words: Words;
  color: string;
  media: ClipUrls | undefined;
  clipPending: boolean;
  comments: Comment[];
  /** What the last revision did to this card, or null if it was left alone. */
  changed: string | null;
  revising: boolean;
  locked: boolean;
  active: boolean;
  playing: boolean;
  composing: boolean;
  editingId: string | null;
  focus: boolean;
  onToggle: () => void;
  onEnded: () => void;
  onCompose: () => void;
  onCancelCompose: () => void;
  onSubmit: (text: string) => void;
  onEdit: (id: string) => void;
  onDelete: (id: string) => void;
};

export function SceneCard(props: Props) {
  const { index, range, media, comments, active, playing } = props;
  const videoRef = useRef<HTMLVideoElement>(null);
  const cardRef = useRef<HTMLElement>(null);
  const [time, setTime] = useState(0);
  const [text, setText] = useState("");
  const length = Math.max(0, range.end - range.start);
  const clip = media?.clip || null;
  const editing = comments.find((comment) => comment.id === props.editingId) || null;

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    if (active && playing) {
      video.play().catch(() => props.onEnded());
    } else {
      video.pause();
      if (!active) {
        video.currentTime = 0;
        setTime(0);
      }
    }
  }, [active, playing, clip]);

  useEffect(() => {
    if (!active || !playing) return;
    let frame = 0;
    const tick = () => {
      if (videoRef.current) setTime(videoRef.current.currentTime);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [active, playing]);

  useEffect(() => {
    if (props.composing) setText(editing?.text ?? "");
  }, [props.composing, props.editingId]);

  useEffect(() => {
    if (props.focus) cardRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [props.focus]);

  const spoken = keptWords(range, props.words).filter((word) => word.text);
  const sourceTime = range.start + time;
  let current = spoken.findIndex((word) => sourceTime < word.end);
  if (current < 0) current = spoken.length - 1;
  const hasDraft = comments.some((comment) => comment.status === "draft");

  function submit() {
    const trimmed = text.trim();
    if (trimmed) props.onSubmit(trimmed);
  }

  function onKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      submit();
    } else if (event.key === "Escape") {
      event.preventDefault();
      props.onCancelCompose();
    }
  }

  function toggle() {
    if (clip) props.onToggle();
  }

  const className = [
    "scard",
    hasDraft ? "has-draft" : "",
    active ? "playing" : "",
    active && !playing ? "paused" : "",
    props.focus ? "flash" : "",
  ].filter(Boolean).join(" ");

  return (
    <article className={className} ref={cardRef} style={{ "--c": props.color } as CSSProperties}>
      <div
        className="pv"
        role="button"
        tabIndex={0}
        aria-label={`Phát cảnh ${pad2(index + 1)}`}
        aria-disabled={!clip}
        onClick={toggle}
        onKeyDown={(event) => {
          if (event.key === " " || event.key === "Enter") {
            event.preventDefault();
            toggle();
          }
        }}
      >
        {clip ? (
          <video
            ref={videoRef}
            className="frame"
            src={clip}
            poster={media?.poster || undefined}
            preload="metadata"
            playsInline
            onEnded={props.onEnded}
          />
        ) : media?.poster ? (
          <img className="frame" src={media.poster} alt="" />
        ) : (
          <div className="frame empty" />
        )}
        <span className="num mono">{pad2(index + 1)}</span>
        {props.changed && (
          <span className="chg" title={props.changed}>
            <Icon name="sparkle" />
            {props.changed === "Cảnh mới" ? "Cảnh mới" : "Đã sửa"}
          </span>
        )}
        {clip ? (
          <span className="pbtn">
            <Icon name={active && playing ? "pause" : "play"} />
          </span>
        ) : (
          <span className="wait">
            {props.clipPending ? <span className="spin sm" /> : <Icon name="alert" small />}
            {props.clipPending ? "Đang tạo clip…" : "Chưa có clip"}
          </span>
        )}
        <span className="dur mono">
          {active ? `${time.toFixed(1)} / ` : ""}
          {length.toFixed(1)}s
        </span>
        <div className="prog">
          <i style={{ width: `${length ? Math.min(100, (time / length) * 100) : 0}%` }} />
        </div>
        {props.revising && (
          <div className="rev">
            <span className="spin" />
            Agent đang sửa cảnh này
          </div>
        )}
      </div>
      <div className="sc-b">
        <div className="sc-h">
          <b>{range.beat || `Cảnh ${pad2(index + 1)}`}</b>
          <span className="src mono">
            {range.source} · {fmt(range.start)}–{fmt(range.end)}
          </span>
        </div>
        {spoken.length > 0 ? (
          <p className={active ? "quote live" : "quote"}>
            {spoken.map((word, at) => (
              <span key={`${word.start}-${at}`} className={!active ? "" : at < current ? "past" : at === current ? "on" : ""}>
                {word.text}
                {at < spoken.length - 1 ? " " : ""}
              </span>
            ))}
          </p>
        ) : (
          range.quote && <p className="quote">{range.quote}</p>
        )}
        {range.reason && (
          <p className="why">
            <Icon name="sparkle" />
            <span>{range.reason}</span>
          </p>
        )}
        {props.changed && !comments.some((comment) => comment.result === props.changed) && (
          <p className="why">
            <Icon name="refresh" />
            <span>{props.changed}</span>
          </p>
        )}
      </div>
      <div className="cm">
        {comments.map((comment) => {
          if (comment.status === "done") {
            return (
              <div className="cmt done" key={comment.id}>
                <p className="ct">{comment.text}</p>
                <p className="cr">
                  <Icon name="check" />
                  <span>{comment.result}</span>
                </p>
              </div>
            );
          }
          if (props.composing && comment.id === props.editingId) return null;
          return (
            <div className={`cmt ${comment.status}`} key={comment.id}>
              <div className="cm-meta">
                <span>Bạn</span>
                {comment.status === "draft" ? (
                  <span className="tag warn">Chưa gửi</span>
                ) : (
                  <span className="tag acc">
                    <span className="spin sm" />
                    Agent đang sửa
                  </span>
                )}
                <span className="sp" />
                {comment.status === "draft" && (
                  <>
                    <button
                      type="button"
                      className="ibtn xs"
                      onClick={() => props.onEdit(comment.id)}
                      title="Sửa góp ý"
                      aria-label="Sửa góp ý"
                    >
                      <Icon name="edit" small />
                    </button>
                    <button
                      type="button"
                      className="ibtn xs"
                      onClick={() => props.onDelete(comment.id)}
                      title="Xóa góp ý"
                      aria-label="Xóa góp ý"
                    >
                      <Icon name="x" small />
                    </button>
                  </>
                )}
              </div>
              <p className="ct">{comment.text}</p>
            </div>
          );
        })}
        {props.composing ? (
          <div className="cm-in">
            <textarea
              rows={2}
              autoFocus
              value={text}
              placeholder="Muốn agent sửa gì ở cảnh này?"
              aria-label="Góp ý cho cảnh"
              onChange={(event) => setText(event.target.value)}
              onKeyDown={onKey}
            />
            <div className="chips">
              {COMMENT_CHIPS.map((chip) => (
                <button
                  type="button"
                  className="chip"
                  key={chip}
                  onClick={() => setText((prev) => (prev.trim() ? `${prev.trim()}. ${chip}` : chip))}
                >
                  {chip}
                </button>
              ))}
            </div>
            <div className="cm-in-f">
              <span className="hint">⌘↵ để thêm</span>
              <button type="button" className="btn ghost sm" onClick={props.onCancelCompose}>
                Hủy
              </button>
              <button type="button" className="btn primary sm" onClick={submit} disabled={!text.trim()}>
                {editing ? "Lưu" : "Thêm góp ý"}
              </button>
            </div>
          </div>
        ) : (
          <button type="button" className="cm-open" onClick={props.onCompose} disabled={props.locked}>
            <Icon name="comment" small />
            {comments.length ? "Thêm góp ý" : "Góp ý cho cảnh này"}
          </button>
        )}
      </div>
    </article>
  );
}
