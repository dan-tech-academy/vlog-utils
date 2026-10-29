import type { AgentInfo } from "../api";
import { folderName, shortPath } from "../format";
import { Icon } from "../icons";
import { agentDot, loginLabel } from "../ui";

export function ProjectMenu({ folder, canRestart, onOpenOther, onRestart, onReveal, onClose }: {
  folder: string;
  canRestart: boolean;
  onOpenOther: () => void;
  onRestart: () => void;
  onReveal: () => void;
  onClose: () => void;
}) {
  return (
    <>
      <div className="scrim clear" onClick={onClose} />
      <div className="pop left" role="menu">
        <div className="ph">{folderName(folder)}</div>
        <button type="button" className="opt" role="menuitem" onClick={onOpenOther}>
          <Icon name="folder" />
          <span><b>Mở folder khác…</b><small>Folder đã làm dở sẽ mở lại đúng bước</small></span>
          <span />
        </button>
        <button type="button" className="opt" role="menuitem" onClick={onRestart} disabled={!canRestart}>
          <Icon name="refresh" />
          <span><b>Làm lại từ đầu…</b><small>Brief mới, giữ transcript</small></span>
          <span />
        </button>
        <button type="button" className="opt" role="menuitem" onClick={onReveal}>
          <Icon name="external" />
          <span><b>Mở trong Finder</b><small className="mono">{shortPath(folder)}</small></span>
          <span />
        </button>
      </div>
    </>
  );
}

export function AgentMenu({ agents, provider, onPick, onSettings, onClose }: {
  agents: AgentInfo[];
  provider: string;
  onPick: (id: string) => void;
  onSettings: () => void;
  onClose: () => void;
}) {
  return (
    <>
      <div className="scrim clear" onClick={onClose} />
      <div className="pop" role="menu">
        <div className="ph">Agent cắt dựng</div>
        {agents.length === 0 && <p className="hint" style={{ padding: "0 8px 6px" }}>Đang kiểm tra agent…</p>}
        {agents.map((agent) => (
          <button
            type="button"
            className="opt"
            role="menuitemradio"
            aria-checked={provider === agent.id}
            key={agent.id}
            disabled={!agent.found}
            onClick={() => onPick(agent.id)}
          >
            <i className={`dot ${agentDot(agent)}`} />
            <span><b>{agent.label}</b><small>{loginLabel(agent)}</small></span>
            {provider === agent.id ? <Icon name="check" /> : <span />}
          </button>
        ))}
        <div className="pf">
          <button type="button" onClick={onSettings}>Cài đặt agent và key…</button>
        </div>
      </div>
    </>
  );
}
