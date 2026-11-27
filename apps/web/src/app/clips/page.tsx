import MilestonePanel from "@/components/MilestonePanel";

export default function Page() {
  return (
    <MilestonePanel
      title="Clip Library"
      milestone={2}
      summary="AI clip discovery and scoring"
      planned={[
        "Transcription with word-level timestamps",
        "Scene, speaker and face analysis",
        "Clip candidates with hook, category and reasoning",
        "Configurable scoring (hook, value, standalone context, retention)",
        "Select, reject, search, sort and filter candidates",
        "Duplicate and overlap prevention",
      ]}
    />
  );
}
