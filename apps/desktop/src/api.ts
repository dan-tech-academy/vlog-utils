import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import type { Turn } from "./conversation";
import type { ProjectStatus } from "./project";
import type { Range, Word } from "./storyboard";

export type SidecarMessage = {
  id?: string;
  type: string;
  ok?: boolean;
  error?: string;
  data?: AgentPayload & Record<string, unknown>;
};

export type AgentInfo = {
  id: string;
  label: string;
  found: boolean;
  path: string | null;
  logged_in: boolean | null;
  detail: string;
};

export type Deps = {
  ffmpeg: { found: boolean; path: string | null };
  ffprobe: { found: boolean; path: string | null };
  uv: { found: boolean; path: string | null };
  python_deps: boolean;
  agents: AgentInfo[];
};

export type VideoItem = {
  name: string;
  path: string;
  size: number;
  cached: boolean;
  duration: number | null;
  poster: string | null;
};

export type Validation = {
  ok: boolean;
  errors: string[];
  warnings: string[];
};

export type AgentPayload = {
  turn?: Turn;
  storyboard_ready?: boolean;
  blocked?: boolean;
  unexpected_writes?: string[];
  strategy_approved?: boolean;
  strategy?: string;
  validation?: Validation;
  error?: string;
};

export type Progress = {
  phase: string;
  done: number;
  total: number;
};

export type ClipItem = {
  index: number;
  source: string | null;
  start: number;
  end: number;
  clip: string | null;
  poster: string | null;
};

export type StoryboardData = {
  edl: { ranges: Range[]; grade?: string; total_duration_s?: number };
  validation: Validation;
  words: Record<string, Word[]>;
  durations: Record<string, number>;
  strategy: string;
};

export function sidecar(cmd: string, extra: Record<string, unknown> = {}): Promise<SidecarMessage> {
  const id = crypto.randomUUID();
  return invoke<SidecarMessage>("sidecar_call", { req: { id, cmd, ...extra } });
}

export function onSidecar(handler: (message: SidecarMessage) => void): Promise<UnlistenFn> {
  return listen<SidecarMessage>("sidecar-event", (event) => handler(event.payload));
}

export async function projectStatus(folder: string): Promise<ProjectStatus> {
  const result = await sidecar("project_status", { folder });
  if (!result.ok || !result.data) throw new Error(result.error || "Không đọc được trạng thái dự án");
  return result.data as unknown as ProjectStatus;
}

export const hasApiKey = () => invoke<boolean>("has_api_key");
export const setApiKey = (key: string) => invoke<void>("set_api_key", { key });
export const clearApiKey = () => invoke<void>("clear_api_key");
export const setMediaRoot = (folder: string) => invoke<void>("set_media_root", { folder });
export const mediaUrl = (path: string) => invoke<string>("media_url", { path });
export const revealPath = (path: string) => invoke<void>("reveal_path", { path });
