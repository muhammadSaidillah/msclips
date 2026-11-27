import MilestonePanel from "@/components/MilestonePanel";

export default function Page() {
  return (
    <MilestonePanel
      title="Analytics"
      milestone={7}
      summary="Performance data from connected platforms"
      planned={[
        "Views, watch time, retention, likes, comments, shares, saves",
        "Performance by clip, hook and subtitle style",
        "Only data returned by platform APIs is shown, never estimates",
      ]}
    />
  );
}
