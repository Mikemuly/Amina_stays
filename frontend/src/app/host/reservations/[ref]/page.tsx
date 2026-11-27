import type { Metadata } from "next";
import { Suspense } from "react";

import { LoadingBlock } from "@/components/host/common";
import { ReservationView } from "@/components/host/ops/reservation-detail";

export const metadata: Metadata = { title: "Reservation" };

// Client-side auth gate + browser data fetching: navigations here may block.
export const instant = false;

export default function ReservationPage({ params }: { params: Promise<{ ref: string }> }) {
  return (
    <Suspense fallback={<LoadingBlock rows={6} />}>
      <Resolve params={params} />
    </Suspense>
  );
}

async function Resolve({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  return <ReservationView refId={ref} />;
}
