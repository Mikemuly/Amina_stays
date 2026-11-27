import type { Metadata } from "next";

import { TripsView } from "@/components/site/trips-view";

export const metadata: Metadata = { title: "Trips" };

export default function Page() {
  return <TripsView />;
}
