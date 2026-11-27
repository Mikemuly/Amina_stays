import type { Metadata } from "next";
import { Suspense } from "react";

import { LoadingBlock } from "@/components/host/common";
import { ReservationsView } from "@/components/host/ops/reservations";

export const metadata: Metadata = { title: "Reservations" };

// Client-side auth gate + browser data fetching: navigations here may block.
export const instant = false;

export default function ReservationsPage() {
  return (
    <Suspense fallback={<LoadingBlock rows={8} />}>
      <ReservationsView />
    </Suspense>
  );
}
