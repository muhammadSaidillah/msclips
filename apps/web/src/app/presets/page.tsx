import MilestonePanel from "@/components/MilestonePanel";

export default function Page() {
  return (
    <MilestonePanel
      title="Brand Presets"
      milestone={4}
      summary="Reusable creator style profiles"
      planned={[
        "Subtitle style, font and highlight colour",
        "Zoom and animation intensity, cutting pace",
        "B-roll frequency, music preference, hook style",
        "Default clip duration and output ratio",
        "Built-ins: My Style, Viral Podcast, Clean Educational, Storytelling, Business, Comedy",
      ]}
    />
  );
}
