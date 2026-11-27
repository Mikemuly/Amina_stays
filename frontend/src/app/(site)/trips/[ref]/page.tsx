import type { Metadata } from "next";
import { Suspense } from "react";

import { TripView } from "@/components/site/trip-view";

export const metadata: Metadata = { title: "Your trip" };

export default function Page({ params }: { params: Promise<{ ref: string }> }) {
  return (
    <Suspense fallback={<div className="h-dvh" />}>
      <Resolve params={params} />
    </Suspense>
  );
}

async function Resolve({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  return <TripView tripRef={ref} />;
}
