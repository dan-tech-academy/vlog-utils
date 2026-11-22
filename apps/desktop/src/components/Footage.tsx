import type { CSSProperties } from "react";
import type { Inventory } from "../api";
import { fmtShort, fmtSize, pad2 } from "../format";
import { Icon } from "../icons";
import type { Range } from "../storyboard";
import { videoStem } from "../ui";

type Props = {
  assets: Inventory;
  posters: Record<string, string>;
  ranges: Range[];
  transcribing: boolean;
};

function sceneRefs(ranges: Range[], stem: string): string[] {
  return ranges
    .map((range, at) => (range.source === stem ? pad2(at + 1) : null))
    .filter(Boolean) as string[];
}

function SectionTitle({ icon, label }: { icon: Parameters<typeof Icon>[0]["name"]; label: string }) {
  return (
    <h3 className="fsec">
      <Icon name={icon} small />
      {label}
    </h3>
  );
}

export function Footage({ assets, posters, ranges, transcribing }: Props) {
  return (
    <>
      {assets.videos.length > 0 && (
        <>
          <SectionTitle icon="film" label={`Video · ${assets.videos.length}`} />
          <div className="grid3">
            {assets.videos.map((video, index) => {
              const stem = videoStem(video.name);
              const scenes = sceneRefs(ranges, stem);
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
        </>
      )}
      {assets.images.length > 0 && (
        <>
          <SectionTitle icon="image" label={`Ảnh · ${assets.images.length}`} />
          <div className="grid3">
            {assets.images.map((image) => {
              const stem = videoStem(image.name);
              const scenes = sceneRefs(ranges, stem);
              const poster = posters[image.path];
              return (
                <article className="fcard" key={image.path}>
                  <div className="pv">
                    {poster ? <img className="frame" src={poster} alt="" /> : <div className="frame empty" />}
                    <span className="num mono">{stem}</span>
                    {image.width && image.height && (
                      <span className="dur mono">{image.width}×{image.height}</span>
                    )}
                  </div>
                  <div className="fb">
                    <b>{image.name}</b>
                    <span className="meta">
                      {fmtSize(image.size)}
                      {scenes.length > 0 && ` · dùng ở cảnh ${scenes.join(", ")}`}
                    </span>
                  </div>
                </article>
              );
            })}
          </div>
        </>
      )}
      {assets.audio.length > 0 && (
        <>
          <SectionTitle icon="music" label={`Âm thanh · ${assets.audio.length}`} />
          <div className="grid3">
            {assets.audio.map((track) => {
              const stem = videoStem(track.name);
              return (
                <article className="fcard" key={track.path}>
                  <div className="pv audio">
                    <span className="big"><Icon name="wave" /></span>
                    <span className="num mono">{stem}</span>
                    {track.duration !== null && <span className="dur mono">{fmtShort(track.duration)}</span>}
                  </div>
                  <div className="fb">
                    <b>{track.name}</b>
                    <span className="meta">{fmtSize(track.size)} · nhạc nền / SFX</span>
                  </div>
                </article>
              );
            })}
          </div>
        </>
      )}
      {assets.docs.length > 0 && (
        <>
          <SectionTitle icon="doc" label={`Kịch bản · ${assets.docs.length}`} />
          <div className="grid3">
            {assets.docs.map((doc) => (
              <article className="fcard" key={doc.path}>
                <div className="pv doc">
                  <span className="big"><Icon name="doc" /></span>
                  <span className="num mono">{videoStem(doc.name)}</span>
                </div>
                <div className="fb">
                  <b>{doc.name}</b>
                  <span className="meta">{fmtSize(doc.size)} · nội dung đưa cho agent</span>
                  {doc.preview && <em className="st">{doc.preview}…</em>}
                </div>
              </article>
            ))}
          </div>
        </>
      )}
      {assets.videos.length + assets.images.length + assets.audio.length + assets.docs.length === 0 && (
        <p className="meta">Folder trống — thả video, ảnh, nhạc hay file kịch bản vào.</p>
      )}
    </>
  );
}
