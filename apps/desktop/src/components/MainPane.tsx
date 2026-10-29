import type { ReactNode } from "react";
import { Icon } from "../icons";

export type View = "board" | "footage";

type Props = {
  folder: string | null;
  view: View;
  sceneCount: number | null;
  videoCount: number;
  stat: string | null;
  stale: boolean;
  previewReady: boolean;
  rendering: "preview" | "final" | null;
  canPlay: boolean;
  renderBlock: string | null;
  exportBlock: string | null;
  dragOver: boolean;
  notices: ReactNode;
  overlay: ReactNode;
  children: ReactNode;
  onView: (view: View) => void;
  onPick: () => void;
  onPlayer: () => void;
  onPreview: () => void;
  onExport: () => void;
};

export function MainPane(props: Props) {
  const { folder, view, sceneCount } = props;
  const hasBoard = sceneCount !== null;
  return (
    <section className="main" aria-label="Storyboard">
      <div className="mh">
        <div className="seg" role="tablist" aria-label="Khu chính">
          <button
            type="button"
            role="tab"
            aria-pressed={view === "board"}
            disabled={!hasBoard}
            title={hasBoard ? undefined : "Chưa có storyboard"}
            onClick={() => props.onView("board")}
          >
            Storyboard <small>{sceneCount ?? "–"}</small>
          </button>
          <button
            type="button"
            role="tab"
            aria-pressed={view === "footage"}
            disabled={!folder}
            onClick={() => props.onView("footage")}
          >
            Footage <small>{folder ? props.videoCount : "–"}</small>
          </button>
        </div>
        {view === "board" && props.stat && <span className="stat mono">{props.stat}</span>}
        {props.stale && (
          <span className="tag warn"><Icon name="alert" />Storyboard đã đổi, cần render lại</span>
        )}
        <span className="sp" />
        {hasBoard && view === "board" && (
          <>
            <button type="button" className="btn ghost" onClick={props.onPlayer} disabled={!props.canPlay}>
              <Icon name="play" small />
              {props.previewReady ? "Xem preview" : "Xem liền mạch"}
            </button>
            {props.rendering === "preview" ? (
              <button type="button" className="btn" disabled><span className="spin sm" />Đang render…</button>
            ) : (
              <button
                type="button"
                className={props.previewReady ? "btn" : "btn primary"}
                onClick={props.onPreview}
                disabled={Boolean(props.renderBlock)}
                title={props.renderBlock || "Render bản 720p có grade và phụ đề"}
              >
                {props.previewReady || props.stale ? "Render lại" : "Render preview"}
              </button>
            )}
            {props.rendering === "final" ? (
              <button type="button" className="btn primary" disabled><span className="spin sm" />Đang xuất…</button>
            ) : (
              <button
                type="button"
                className={props.previewReady ? "btn primary" : "btn"}
                onClick={props.onExport}
                disabled={Boolean(props.exportBlock)}
                title={props.exportBlock || "Xuất bản 1080p"}
              >
                <Icon name="export" small />Xuất final.mp4
              </button>
            )}
          </>
        )}
      </div>
      {folder ? (
        <div className="mscroll" id="mscroll">
          {props.notices}
          {props.children}
        </div>
      ) : (
        <div className="mscroll center">
          {props.notices}
          <div className={props.dragOver ? "dropzone over" : "dropzone"}>
            <span className="big"><Icon name="folder" /></span>
            <h2>Mở folder footage</h2>
            <p>
              Kéo folder từ Finder vào đây, hoặc chọn bằng nút bên dưới. App chỉ đọc video, mọi file làm ra nằm
              trong <span className="mono">edit/</span> của folder đó.
            </p>
            <button type="button" className="btn primary lg" onClick={props.onPick}>
              <Icon name="folder" />Chọn folder…
            </button>
            <div className="exts">
              <span>.mp4</span><span>.mov</span><span>.mkv</span><span>.avi</span><span>.m4v</span>
            </div>
          </div>
        </div>
      )}
      {props.overlay}
    </section>
  );
}
