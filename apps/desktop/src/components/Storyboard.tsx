import { cardKey, type Comments, type Words } from "../revise";
import type { Range } from "../storyboard";
import type { ClipMap } from "../ui";
import { SceneCard } from "./SceneCard";

export type Compose = { key: string; editingId: string | null };
export type Play = { key: string; playing: boolean };

type Props = {
  ranges: Range[];
  words: Words;
  colorOf: (source: string) => string;
  clips: ClipMap;
  clipsRunning: boolean;
  comments: Comments;
  changed: Record<string, string>;
  revising: boolean;
  locked: boolean;
  play: Play | null;
  compose: Compose | null;
  focusKey: string | null;
  onPlay: (key: string) => void;
  onEnded: () => void;
  onCompose: (compose: Compose | null) => void;
  onSubmit: (key: string, text: string, editingId: string | null) => void;
  onDelete: (key: string, id: string) => void;
};

export function Storyboard(props: Props) {
  return (
    <div className="grid3">
      {props.ranges.map((range, index) => {
        const key = cardKey(range);
        const comments = props.comments[key] || [];
        const media = props.clips[key];
        const composing = props.compose?.key === key;
        return (
          <SceneCard
            key={`${key}#${index}`}
            index={index}
            range={range}
            words={props.words}
            color={props.colorOf(range.source)}
            media={media}
            clipPending={props.clipsRunning && !media?.clip}
            comments={comments}
            changed={props.changed[key] ?? null}
            revising={props.revising && comments.some((comment) => comment.status === "sent")}
            locked={props.locked}
            active={props.play?.key === key}
            playing={props.play?.key === key && props.play.playing}
            composing={composing}
            editingId={composing ? props.compose?.editingId ?? null : null}
            focus={props.focusKey === key}
            onToggle={() => props.onPlay(key)}
            onEnded={props.onEnded}
            onCompose={() => props.onCompose({ key, editingId: null })}
            onCancelCompose={() => props.onCompose(null)}
            onSubmit={(text) => props.onSubmit(key, text, composing ? props.compose?.editingId ?? null : null)}
            onEdit={(id) => props.onCompose({ key, editingId: id })}
            onDelete={(id) => props.onDelete(key, id)}
          />
        );
      })}
    </div>
  );
}

export function StoryboardSkeleton() {
  return (
    <div className="grid3">
      {Array.from({ length: 6 }, (_, index) => (
        <div className="skel" aria-hidden="true" key={index}>
          <div className="pvs" />
          <div className="ls">
            <i style={{ width: "40%" }} />
            <i />
            <i style={{ width: "75%" }} />
          </div>
        </div>
      ))}
    </div>
  );
}
