export const pad2 = (n: number) => String(n).padStart(2, "0");

export function fmt(seconds: number): string {
  const t = Math.max(0, seconds);
  const minutes = Math.floor(t / 60);
  return `${pad2(minutes)}:${(t - minutes * 60).toFixed(2).padStart(5, "0")}`;
}

export function fmtShort(seconds: number): string {
  const t = Math.max(0, seconds);
  return `${Math.floor(t / 60)}:${pad2(Math.floor(t % 60))}`;
}

export function fmtSize(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  return `${Math.max(1, Math.round(bytes / 1024 ** 2))} MB`;
}

export function folderName(path: string): string {
  const parts = path.replace(/\/+$/, "").split("/");
  return parts[parts.length - 1] || path;
}

export function shortPath(path: string): string {
  return path.replace(/^\/Users\/[^/]+/, "~");
}

export function parentPath(path: string): string {
  const trimmed = shortPath(path).replace(/\/+$/, "");
  const cut = trimmed.lastIndexOf("/");
  return cut > 0 ? trimmed.slice(0, cut) : trimmed;
}
