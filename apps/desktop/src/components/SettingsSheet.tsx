import { useState } from "react";
import type { Deps } from "../api";
import { Icon } from "../icons";
import { agentDot, loginLabel } from "../ui";

type Props = {
  deps: Deps | null;
  provider: string;
  hasKey: boolean;
  checkingLogin: boolean;
  onProvider: (id: string) => void;
  onSaveKey: (key: string) => Promise<void>;
  onClearKey: () => void;
  onCheckLogin: () => void;
  onClose: () => void;
};

export function SettingsSheet(props: Props) {
  const [key, setKey] = useState("");
  const [saving, setSaving] = useState(false);
  const deps = props.deps;
  const tools: Array<[string, boolean, string]> = deps
    ? [
        ["ffmpeg", deps.ffmpeg.found, deps.ffmpeg.path || "Không thấy. Cài bằng brew install ffmpeg"],
        ["ffprobe", deps.ffprobe.found, deps.ffprobe.path || "Không thấy. Đi kèm ffmpeg"],
        ["uv", deps.uv.found, deps.uv.path || "Không thấy"],
        ["Python deps", deps.python_deps, deps.python_deps ? "Đã cài" : "Thiếu. Chạy uv sync trong repo"],
      ]
    : [];

  async function save() {
    const trimmed = key.trim();
    if (!trimmed) return;
    setSaving(true);
    try {
      await props.onSaveKey(trimmed);
      setKey("");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="scrim" onClick={props.onClose} />
      <div className="sheet" role="dialog" aria-modal="true" aria-label="Cài đặt">
        <div className="sheet-h">
          Cài đặt
          <button type="button" className="ibtn" onClick={props.onClose} aria-label="Đóng"><Icon name="x" /></button>
        </div>
        <div className="sheet-b">
          <section>
            <h4>Agent cắt dựng</h4>
            <p className="sub">Chạy bằng CLI đã đăng nhập trên máy bạn.</p>
            <div className="radios">
              {(deps?.agents || []).map((agent) => (
                <label className={agent.found ? "radio" : "radio off"} key={agent.id}>
                  <input
                    type="radio"
                    name="agent"
                    value={agent.id}
                    checked={props.provider === agent.id}
                    disabled={!agent.found}
                    onChange={() => props.onProvider(agent.id)}
                  />
                  <span className="rb" />
                  <span><b>{agent.label}</b><small>{loginLabel(agent)}</small></span>
                  <i className={`dot ${agentDot(agent)}`} />
                </label>
              ))}
            </div>
            <div>
              <button type="button" className="btn sm" onClick={props.onCheckLogin} disabled={props.checkingLogin}>
                {props.checkingLogin ? <span className="spin sm" /> : <Icon name="refresh" small />}
                Kiểm tra đăng nhập
              </button>
            </div>
          </section>
          <section>
            <h4>ElevenLabs</h4>
            <p className="sub">Dùng để transcribe. Lưu trong Keychain, không đưa vào process agent.</p>
            {props.hasKey ? (
              <div className="keyrow">
                <span className="mono">••••••••••••••••</span>
                <span className="tag ok"><Icon name="check" />Đã lưu</span>
                <button type="button" className="btn sm ghost" onClick={props.onClearKey}>Xóa key</button>
              </div>
            ) : (
              <div className="keyrow">
                <input
                  className="field"
                  type="password"
                  autoComplete="off"
                  placeholder="Dán API key"
                  aria-label="ElevenLabs API key"
                  value={key}
                  onChange={(event) => setKey(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") void save();
                  }}
                />
                <button type="button" className="btn sm" onClick={() => void save()} disabled={!key.trim() || saving}>
                  Lưu
                </button>
              </div>
            )}
          </section>
          <section>
            <h4>Máy</h4>
            {deps ? (
              <ul className="deps">
                {tools.map(([name, found, detail]) => (
                  <li key={name} className={found ? "" : "miss"}>
                    <Icon name={found ? "check" : "alert"} small />
                    <b>{name}</b>
                    <span className="mono">{detail}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="sub">Đang kiểm tra…</p>
            )}
          </section>
        </div>
      </div>
    </>
  );
}
