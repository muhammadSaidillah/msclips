import MilestonePanel from "@/components/MilestonePanel";

export default function Page() {
  return (
    <MilestonePanel
      title="Editing Studio"
      milestone={5}
      summary="Interactive timeline editor"
      planned={[
        "Preview, playback and timeline scrubbing",
        "Trim, split, undo and redo",
        "Subtitle, crop, animation, audio and B-roll controls",
        "Natural-language edit instructions with a change preview",
        "Regenerate one element without re-rendering the whole clip",
      ]}
    />
  );
}
