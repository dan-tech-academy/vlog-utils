export type Question = { id: string; prompt: string };

export type Turn =
  | { kind: "questions"; questions: Question[] }
  | { kind: "strategy"; strategy: string }
  | { kind: "edl" };

export function questionFields(turn: Turn | null): Question[] {
  if (!turn || turn.kind !== "questions") return [];
  return turn.questions.filter((question) => question.id.trim() && question.prompt.trim());
}

export function acceptsEdl(turn: Turn | null, strategyApproved: boolean): boolean {
  return Boolean(turn && turn.kind === "edl" && strategyApproved);
}
