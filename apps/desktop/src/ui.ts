import type { AgentInfo } from "./api";

export type Busy = {
  kind: "ingest" | "agent" | "render" | "reset";
  title: string;
  sub: string;
  t0: number;
  mode?: "preview" | "final";
  /** A batch of card comments is being applied. */
  scenes?: boolean;
  /** The first storyboard is being built. */
  edl?: boolean;
};

export type ClipUrls = { clip: string | null; poster: string | null };
/** Media URLs per card, keyed by cardKey. */
export type ClipMap = Record<string, ClipUrls>;

export type Overlay = "settings" | "agentmenu" | "projmenu" | "restart" | "player" | null;

export function loginLabel(agent: AgentInfo): string {
  if (!agent.found) return agent.detail || "Không có trên PATH";
  if (agent.logged_in === true) return "Đã đăng nhập";
  if (agent.logged_in === false) return "Chưa đăng nhập";
  return agent.detail || "Chưa kiểm tra đăng nhập";
}

export function agentDot(agent: AgentInfo | undefined): "ok" | "unk" | "off" | "err" {
  if (!agent || !agent.found) return "off";
  if (agent.logged_in === true) return "ok";
  if (agent.logged_in === false) return "err";
  return "unk";
}

export function videoStem(name: string): string {
  return name.replace(/\.[^.]+$/, "");
}
