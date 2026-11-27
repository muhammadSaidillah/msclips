import MilestonePanel from "@/components/MilestonePanel";

export default function Page() {
  return (
    <MilestonePanel
      title="Publishing Calendar"
      milestone={7}
      summary="Scheduling through official platform APIs"
      planned={[
        "Drafts, scheduled, published and failed posts",
        "TikTok and Instagram Reels via authorized accounts",
        "Status verified against the platform response",
        "Manual publishing workflow when direct publishing is unavailable",
      ]}
    />
  );
}
