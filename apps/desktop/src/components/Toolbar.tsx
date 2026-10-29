import type { AgentInfo } from "../api";
import { folderName, parentPath } from "../format";
import { Icon } from "../icons";
import { STEPS } from "../project";
import { agentDot } from "../ui";

type Props = {
  folder: string | null;
  step: number;
  agent: AgentInfo | undefined;
  projectMenuOpen: boolean;
  agentMenuOpen: boolean;
  consoleOpen: boolean;
  onProjectMenu: () => void;
  onAgentMenu: () => void;
  onConsole: () => void;
  onSettings: () => void;
};

export function Toolbar(props: Props) {
  const { folder, step, agent } = props;
  return (
    <header className="toolbar" data-tauri-drag-region>
      <div className="tb-left" data-tauri-drag-region>
        {folder ? (
          <button
            type="button"
            className="proj"
            onClick={props.onProjectMenu}
            aria-haspopup="menu"
            aria-expanded={props.projectMenuOpen}
          >
            <Icon name="folder" />
            <div>
              <b>{folderName(folder)}</b>
              <small>{parentPath(folder)}</small>
            </div>
            <Icon name="chevDown" small />
          </button>
        ) : (
          <div className="proj">
            <div>
              <b>Vlog Utils</b>
              <small>Chưa mở folder</small>
            </div>
          </div>
        )}
      </div>
      <ol className="steps" aria-label="Tiến trình" data-tauri-drag-region>
        {STEPS.map((name, index) => (
          <li
            key={name}
            className={index < step ? "done" : index === step ? "cur" : ""}
            aria-current={index === step ? "step" : undefined}
          >
            <span className="n">{index < step ? <Icon name="check" /> : index + 1}</span>
            <span className="label">{name}</span>
          </li>
        ))}
      </ol>
      <div className="tb-right" data-tauri-drag-region>
        <button
          type="button"
          className="agent-chip"
          onClick={props.onAgentMenu}
          aria-haspopup="menu"
          aria-expanded={props.agentMenuOpen}
        >
          <i className={`dot ${agentDot(agent)}`} />
          {agent?.found ? agent.label : "Chưa có agent"}
          <Icon name="chevDown" small />
        </button>
        <button
          type="button"
          className="ibtn"
          onClick={props.onConsole}
          aria-pressed={props.consoleOpen}
          title="Console"
          aria-label="Console"
        >
          <Icon name="terminal" />
        </button>
        <button type="button" className="ibtn" onClick={props.onSettings} title="Cài đặt" aria-label="Cài đặt">
          <Icon name="sliders" />
        </button>
      </div>
    </header>
  );
}
