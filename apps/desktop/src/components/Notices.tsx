import type { ReactNode } from "react";
import { Icon, type IconName } from "../icons";

export type NoticeItem = {
  id: string;
  tone: "info" | "warn" | "err";
  icon: IconName | "spin";
  body: ReactNode;
  detail?: string;
  actions?: { label: string; icon?: IconName; ghost?: boolean; run: () => void; disabled?: boolean }[];
  onDismiss?: () => void;
};

export function Notices({ items }: { items: NoticeItem[] }) {
  return (
    <>
      {items.map((item) => (
        <div
          key={item.id}
          className={item.tone === "info" ? "notice" : `notice ${item.tone}`}
          role={item.tone === "err" ? "alert" : undefined}
        >
          {item.icon === "spin" ? <span className="spin" /> : <Icon name={item.icon} />}
          <span className="t">
            {item.body}
            {item.detail && <pre>{item.detail}</pre>}
          </span>
          {item.actions?.map((action) => (
            <button
              type="button"
              key={action.label}
              className={action.ghost ? "btn ghost sm" : "btn sm"}
              onClick={action.run}
              disabled={action.disabled}
            >
              {action.icon && <Icon name={action.icon} small />}
              {action.label}
            </button>
          ))}
          {item.onDismiss && (
            <button type="button" className="ibtn sm" onClick={item.onDismiss} aria-label="Ẩn thông báo">
              <Icon name="x" small />
            </button>
          )}
        </div>
      ))}
    </>
  );
}
