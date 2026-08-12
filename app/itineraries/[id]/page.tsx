import { ItineraryDetailClient } from "@/components/itineraries/itinerary-detail-client";

export const metadata = {
  title: "Travel Compass — Saved itinerary",
  description: "View a saved day-by-day travel plan.",
};

type PageProps = {
  params: Promise<{ id: string }>;
};

export default async function ItineraryDetailPage({ params }: PageProps) {
  const { id } = await params;
  return <ItineraryDetailClient itineraryId={id} />;
}
