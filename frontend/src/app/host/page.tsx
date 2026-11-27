import type { Metadata } from "next";
import { Suspense } from "react";

import { LoadingBlock } from "@/components/host/common";
import { TodayView } from "@/components/host/ops/today";

export const metadata: Metadata = { title: "Today" };

// The console renders behind a client-side auth gate and loads its data in the browser, so
// navigations into it are allowed to block (opts out of Next's instant-navigation validation).
export const instant = false;

export default function TodayPage() {
  return (
    <Suspense fallback={<LoadingBlock rows={6} />}>
      <TodayView />
    </Suspense>
  );
}
