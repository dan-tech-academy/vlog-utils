import { Icon } from "../icons";

type Props = {
  drafts: number;
  scenes: number;
  revising: string | null;
  blocked: string | null;
  onSend: () => void;
  onClear: () => void;
  onCancel: () => void;
};

export function BatchBar({ drafts, scenes, revising, blocked, onSend, onClear, onCancel }: Props) {
  if (revising) {
    return (
      <div className="batchbar" role="status">
        <span className="spin" />
        <div>
          <b>{revising}</b>
          <small>Agent đọc góp ý rồi viết lại edl.json</small>
        </div>
        <button type="button" className="btn ghost sm" onClick={onCancel}>
          Hủy
        </button>
      </div>
    );
  }
  if (!drafts) return null;
  return (
    <div className="batchbar">
      <span className="bc">{drafts}</span>
      <div>
        <b>{drafts} góp ý chưa gửi</b>
        <small>{blocked || `Agent sẽ sửa cả ${scenes} cảnh trong một lượt`}</small>
      </div>
      <button type="button" className="btn ghost sm" onClick={onClear}>
        Bỏ hết
      </button>
      <button type="button" className="btn primary" onClick={onSend} disabled={Boolean(blocked)}>
        <Icon name="arrowUp" small />
        Gửi {drafts} góp ý
      </button>
    </div>
  );
}
