import { useState } from "react";
import type { Validation } from "./api";
import {
  removeAt,
  reorder,
  totalDuration,
  trimRange,
  type Range,
  type Word,
} from "./storyboard";

type Frame = { index: number; url: string | null };

type Props = {
  ranges: Range[];
  words: Record<string, Word[]>;
  durations: Record<string, number>;
  frames: Frame[];
  validation: Validation | null;
  busy: boolean;
  previewReady: boolean;
  previewUrl: string | null;
  finalPath: string | null;
  onRanges: (ranges: Range[]) => void;
  onPreview: () => void;
  onFinal: () => void;
};

export function Board({
  ranges,
  words,
  durations,
  frames,
  validation,
  busy,
  previewReady,
  previewUrl,
  finalPath,
  onRanges,
  onPreview,
  onFinal,
}: Props) {
  const [dragIndex, setDragIndex] = useState<number | null>(null);

  function move(from: number, to: number) {
    onRanges(reorder(ranges, from, to));
  }

  return (
    <section className="stack">
      <div className="row">
        <h2>Storyboard</h2>
        <span className="muted">{totalDuration(ranges).toFixed(2)}s</span>
      </div>
      {validation?.warnings.map((warning) => (
        <div className="banner warn" key={warning}>{warning}</div>
      ))}
      <div className="cards">
        {ranges.map((range, index) => {
          const frame = frames.find((item) => item.index === index);
          return (
            <article
              className="card"
              key={`${range.source}-${index}`}
              draggable
              onDragStart={() => setDragIndex(index)}
              onDragOver={(event) => event.preventDefault()}
              onDrop={() => {
                if (dragIndex !== null) move(dragIndex, index);
                setDragIndex(null);
              }}
            >
              <div className="still">
                {frame?.url ? <img src={frame.url} alt="" /> : <span>không có frame</span>}
              </div>
              <header>
                <span>{String(index + 1).padStart(2, "0")} {range.beat || range.source}</span>
                <span>{range.source}</span>
              </header>
              <div className="body stack">
                <p className="quote">{range.quote || "—"}</p>
                <div className="times">
                  <label>
                    Vào
                    <input
                      type="number"
                      step="0.01"
                      defaultValue={range.start}
                      key={`in-${range.source}-${range.start}-${index}`}
                      onBlur={(event) => {
                        const time = Number(event.target.value);
                        if (Number.isNaN(time)) return;
                        const next = ranges.slice();
                        next[index] = trimRange(range, "start", time, words[range.source] || [], durations[range.source]);
                        onRanges(next);
                      }}
                    />
                  </label>
                  <label>
                    Ra
                    <input
                      type="number"
                      step="0.01"
                      defaultValue={range.end}
                      key={`out-${range.source}-${range.end}-${index}`}
                      onBlur={(event) => {
                        const time = Number(event.target.value);
                        if (Number.isNaN(time)) return;
                        const next = ranges.slice();
                        next[index] = trimRange(range, "end", time, words[range.source] || [], durations[range.source]);
                        onRanges(next);
                      }}
                    />
                  </label>
                </div>
                <div className="row">
                  <button type="button" className="quiet" disabled={busy || index === 0} onClick={() => move(index, index - 1)}>Lên</button>
                  <button type="button" className="quiet" disabled={busy || index === ranges.length - 1} onClick={() => move(index, index + 1)}>Xuống</button>
                  <button type="button" className="quiet" disabled={busy} onClick={() => onRanges(removeAt(ranges, index))}>Xóa</button>
                </div>
              </div>
            </article>
          );
        })}
      </div>
      <div className="row">
        <button type="button" className="primary" disabled={busy || ranges.length === 0} onClick={onPreview}>
          Duyệt và xem preview
        </button>
        <button type="button" disabled={busy || !previewReady} onClick={onFinal}>
          Xuất final.mp4
        </button>
      </div>
      {previewUrl && (
        <div className="player stack">
          <p className="muted">Preview</p>
          <video src={previewUrl} controls />
        </div>
      )}
      {finalPath && <p className="muted">Đã xuất {finalPath}</p>}
    </section>
  );
}
