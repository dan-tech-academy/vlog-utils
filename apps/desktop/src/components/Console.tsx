import { useEffect, useRef } from "react";
import { Icon } from "../icons";

export function Console({ open, lines, onClose }: { open: boolean; lines: string[]; onClose: () => void }) {
  const preRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    const pre = preRef.current;
    if (open && pre) pre.scrollTop = pre.scrollHeight;
  }, [open, lines]);

  return (
    <section className={open ? "console open" : "console"} aria-label="Console" aria-hidden={!open}>
      <div className="ch">
        Console
        <span className="sp" />
        <button type="button" className="btn ghost sm" onClick={() => void navigator.clipboard.writeText(lines.join("\n"))}>
          <Icon name="copy" small />Sao chép
        </button>
        <button type="button" className="ibtn sm" onClick={onClose} aria-label="Đóng console"><Icon name="x" small /></button>
      </div>
      <pre ref={preRef}>
        {lines.map((line, index) => {
          const tag = /^\[([\w-]+)\]/.exec(line);
          return (
            <span key={index}>
              {tag ? <><span className="k">{tag[0]}</span>{line.slice(tag[0].length)}</> : line}
              {"\n"}
            </span>
          );
        })}
      </pre>
    </section>
  );
}
