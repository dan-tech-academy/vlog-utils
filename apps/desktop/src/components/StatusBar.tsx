import type { Deps } from "../api";
import { shortPath } from "../format";
import { Icon } from "../icons";

type Props = {
  text: string;
  tone: "ok" | "unk" | "err" | "off";
  hasKey: boolean;
  deps: Deps | null;
  folder: string | null;
  onConsole: () => void;
};

export function StatusBar({ text, tone, hasKey, deps, folder, onConsole }: Props) {
  return (
    <footer className="statusbar">
      <span className="s"><i className={`dot ${tone}`} />{text}</span>
      <span className="sp" />
      <span className="s">ElevenLabs {hasKey ? "đã có key" : "chưa có key"}</span>
      {deps && <span className="s">{deps.ffmpeg.found ? "ffmpeg có" : "thiếu ffmpeg"}</span>}
      {folder && <span className="s path mono">{shortPath(folder)}/edit</span>}
      <button type="button" onClick={onConsole}><Icon name="terminal" />Console</button>
    </footer>
  );
}
