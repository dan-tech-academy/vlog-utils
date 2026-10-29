import { Icon } from "../icons";

type Props = {
  folder: string;
  transcripts: number;
  scenes: number;
  outputs: string[];
  working: boolean;
  onConfirm: () => void;
  onClose: () => void;
};

export function RestartSheet({ folder, transcripts, scenes, outputs, working, onConfirm, onClose }: Props) {
  return (
    <>
      <div className="scrim" onClick={working ? undefined : onClose} />
      <div className="sheet" role="dialog" aria-modal="true" aria-label="Làm lại từ đầu">
        <div className="sheet-h">
          Làm lại từ đầu?
          <button type="button" className="ibtn" onClick={onClose} disabled={working} aria-label="Đóng"><Icon name="x" /></button>
        </div>
        <div className="sheet-b">
          <section>
            <p>Bắt đầu brief mới cho <b>{folder}</b>. Không file nào bị xóa.</p>
          </section>
          <section>
            <h4>Giữ nguyên</h4>
            <ul className="keep">
              <li>
                <Icon name="check" small />
                <span>
                  {transcripts > 0
                    ? `Transcript của ${transcripts} video. Không cần transcribe lại, không tốn thêm tiền ElevenLabs.`
                    : "Transcript đã có. Không cần transcribe lại."}
                </span>
              </li>
            </ul>
          </section>
          <section>
            <h4>Cất vào <span className="mono">edit/archive/&lt;ngày-giờ&gt;/</span></h4>
            <ul className="keep moved">
              <li><Icon name="folder" small /><span>Brief, câu trả lời và chiến lược đã duyệt</span></li>
              {scenes > 0 && <li><Icon name="folder" small /><span>Storyboard {scenes} cảnh và các góp ý</span></li>}
              {outputs.length > 0 && <li><Icon name="folder" small /><span>{outputs.join(", ")}</span></li>}
              <li><Icon name="folder" small /><span>Phiên trò chuyện với agent. Lần sau agent bắt đầu phiên mới.</span></li>
            </ul>
          </section>
        </div>
        <div className="sheet-f">
          <button type="button" className="btn ghost" onClick={onClose} disabled={working}>Hủy</button>
          <button type="button" className="btn primary" onClick={onConfirm} disabled={working}>
            {working ? <span className="spin sm" /> : <Icon name="refresh" small />}
            Làm lại từ đầu
          </button>
        </div>
      </div>
    </>
  );
}
