import type { CSSProperties } from "react";
import type { VideoItem } from "../api";
import { fmtShort, fmtSize, pad2 } from "../format";
import type { Range } from "../storyboard";
import { videoStem } from "../ui";

type Props = {
  videos: VideoItem[];
  posters: Record<string, string>;
  ranges: Range[];
  transcribing: boolean;
};

export function Footage({ videos, posters, ranges, transcribing }: Props) {
  return (
    <div className="grid3">
      {videos.map((video, index) => {
        const stem = videoStem(video.name);
        const scenes = ranges
          .map((range, at) => (range.source === stem ? pad2(at + 1) : null))
          .filter(Boolean);
        const poster = posters[video.path];
        return (
          <article className="fcard" key={video.path} style={{ "--c": `var(--s${(index % 6) + 1})` } as CSSProperties}>
            <div className="pv">
              {poster ? <img className="frame" src={poster} alt="" /> : <div className="frame empty" />}
              <span className="num mono">{stem}</span>
              {video.duration !== null && <span className="dur mono">{fmtShort(video.duration)}</span>}
              {transcribing && !video.cached && (
                <div className="rev">
                  <span className="spin" />
                  Đang transcribe
                </div>
              )}
            </div>
            <div className="fb">
              <b>{video.name}</b>
              <span className="meta">
                {fmtSize(video.size)}
                {scenes.length > 0 && ` · dùng ở cảnh ${scenes.join(", ")}`}
              </span>
              <em className={video.cached ? "st ok" : "st"}>
                {video.cached ? "Đã có transcript" : transcribing ? "Đang transcribe…" : "Chưa transcript"}
              </em>
            </div>
          </article>
        );
      })}
    </div>
  );
}
