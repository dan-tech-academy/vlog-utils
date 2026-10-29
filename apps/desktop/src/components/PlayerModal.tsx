import { useEffect, useMemo, useRef, useState, type MouseEvent } from "react";
import { fmt, pad2 } from "../format";
import { Icon } from "../icons";
import { cardKey } from "../revise";
import type { Range } from "../storyboard";
import type { ClipMap } from "../ui";

type Props = {
  ranges: Range[];
  clips: ClipMap;
  previewUrl: string | null;
  grade: string;
  onClose: () => void;
  onComment: (index: number) => void;
};

function sceneAt(starts: number[], t: number): number {
  let index = 0;
  starts.forEach((start, at) => {
    if (t >= start - 1e-6) index = at;
  });
  return index;
}

export function PlayerModal({ ranges, clips, previewUrl, grade, onClose, onComment }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const pendingSeek = useRef<number | null>(null);
  const [index, setIndex] = useState(0);
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);

  const starts = useMemo(() => {
    let acc = 0;
    return ranges.map((range) => {
      const start = acc;
      acc += Math.max(0, range.end - range.start);
      return start;
    });
  }, [ranges]);
  const total = ranges.reduce((sum, range) => sum + Math.max(0, range.end - range.start), 0);
  const preview = previewUrl !== null;
  const current = ranges[index];
  const src = preview ? previewUrl : (current && clips[cardKey(current)]?.clip) || null;
  const poster = current ? clips[cardKey(current)]?.poster || undefined : undefined;

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    if (playing) video.play().catch(() => setPlaying(false));
    else video.pause();
  }, [playing, src]);

  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    const tick = () => {
      const video = videoRef.current;
      if (video) {
        const global = preview ? video.currentTime : (starts[index] ?? 0) + video.currentTime;
        setTime(global);
        if (preview) setIndex(sceneAt(starts, global));
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, preview, index, starts]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
      const typing = event.target instanceof HTMLTextAreaElement || event.target instanceof HTMLInputElement;
      if (event.key === " " && !typing && !(event.target instanceof HTMLButtonElement)) {
        event.preventDefault();
        setPlaying((value) => !value);
      }
      if (event.key === "ArrowRight") jump(Math.min(ranges.length - 1, index + 1));
      if (event.key === "ArrowLeft") jump(Math.max(0, index - 1));
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  function seek(global: number) {
    const target = Math.max(0, Math.min(total, global));
    const scene = sceneAt(starts, target);
    setTime(target);
    setIndex(scene);
    const video = videoRef.current;
    if (preview) {
      if (video) video.currentTime = target;
      return;
    }
    const local = target - starts[scene];
    if (scene === index && video) video.currentTime = local;
    else pendingSeek.current = local;
  }

  function jump(scene: number) {
    seek(starts[scene] ?? 0);
  }

  function onScrub(event: MouseEvent<HTMLDivElement>) {
    const box = event.currentTarget.getBoundingClientRect();
    seek(((event.clientX - box.left) / box.width) * total);
  }

  function onEnded() {
    if (preview || index >= ranges.length - 1) {
      setPlaying(false);
      return;
    }
    pendingSeek.current = 0;
    setIndex(index + 1);
    setTime(starts[index + 1]);
  }

  return (
    <>
      <div className="scrim" onClick={onClose} />
      <div className="player" role="dialog" aria-modal="true" aria-label="Xem cả video">
        <div className="pl-h">
          <b>{preview ? "Preview 720p" : "Xem liền mạch"}</b>
          <span className="hint">
            {preview ? "edit/preview.mp4 · đã grade và burn phụ đề" : "Phát nối clip từng cảnh, chưa grade, chưa phụ đề"}
          </span>
          <span className="sp" />
          {current && (
            <span className="hint mono">
              Cảnh {pad2(index + 1)}{current.beat ? ` · ${current.beat}` : ""}
            </span>
          )}
          <button type="button" className="btn sm" onClick={() => onComment(index)}>
            <Icon name="comment" small />Góp ý cảnh này
          </button>
          <button type="button" className="ibtn" onClick={onClose} aria-label="Đóng">
            <Icon name="x" />
          </button>
        </div>
        <div className="pl-screen">
          {src ? (
            <video
              ref={videoRef}
              className="frame"
              src={src}
              poster={preview ? undefined : poster}
              playsInline
              onClick={() => setPlaying((value) => !value)}
              onEnded={onEnded}
              onLoadedMetadata={(event) => {
                if (pendingSeek.current !== null) {
                  event.currentTarget.currentTime = pendingSeek.current;
                  pendingSeek.current = null;
                }
              }}
            />
          ) : poster ? (
            <img className="frame" src={poster} alt="" />
          ) : (
            <div className="frame empty" />
          )}
          <span className="osd">
            {preview ? `PREVIEW 720p${grade ? ` · ${grade}` : ""}` : src ? "CHƯA RENDER" : "CLIP CẢNH NÀY CHƯA SẴN SÀNG"}
          </span>
        </div>
        <div className="pl-t">
          <button type="button" className="ibtn" onClick={() => jump(Math.max(0, index - 1))} aria-label="Cảnh trước">
            <Icon name="prev" />
          </button>
          <button
            type="button"
            className="ibtn play"
            onClick={() => setPlaying((value) => !value)}
            disabled={!src}
            aria-label={playing ? "Dừng" : "Phát"}
          >
            <Icon name={playing ? "pause" : "play"} />
          </button>
          <button
            type="button"
            className="ibtn"
            onClick={() => jump(Math.min(ranges.length - 1, index + 1))}
            aria-label="Cảnh sau"
          >
            <Icon name="next" />
          </button>
          <span className="tc mono"><b>{fmt(time)}</b> / {fmt(total)}</span>
          <div className="scrub" onClick={onScrub}>
            <div className="rail">
              <div className="fill" style={{ width: `${total ? (time / total) * 100 : 0}%` }} />
            </div>
            {starts.slice(1).map((start, at) => (
              <span className="cut" key={at} style={{ left: `${(start / total) * 100}%` }} />
            ))}
          </div>
        </div>
        <div className="pl-strip">
          {ranges.map((range, at) => {
            const thumb = clips[cardKey(range)]?.poster;
            return (
              <button type="button" key={`${cardKey(range)}#${at}`} className={at === index ? "on" : ""} onClick={() => jump(at)}>
                <span className="th">{thumb && <img src={thumb} alt="" />}</span>
                <span>{pad2(at + 1)} {range.beat || ""}</span>
              </button>
            );
          })}
        </div>
      </div>
    </>
  );
}
