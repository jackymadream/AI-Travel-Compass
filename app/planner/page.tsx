import { PlannerClient } from "@/components/planner/planner-client";

export const metadata = {
  title: "Travel Compass — Itinerary Planner",
  description:
    "Generate a day-by-day itinerary with the tool-calling agent: POIs, pace, and budget.",
};

export default function PlannerPage() {
  return <PlannerClient />;
}
