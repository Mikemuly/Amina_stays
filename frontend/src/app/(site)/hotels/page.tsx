import type { Metadata } from "next";

import { HotelsView } from "@/components/site/hotels-view";

export const metadata: Metadata = { title: "Hotel-style stays" };

export default function HotelsPage() {
  return <HotelsView />;
}
