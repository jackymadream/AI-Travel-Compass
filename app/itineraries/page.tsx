import { ItinerariesClient } from "@/components/itineraries/itineraries-client";

export const metadata = {
  title: "Travel Compass — My Itineraries",
  description: "Browse and re-open your saved AI travel itineraries.",
};

export default function ItinerariesPage() {
  return <ItinerariesClient />;
}
