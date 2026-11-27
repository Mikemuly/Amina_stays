import type { Metadata } from "next";
import { Suspense } from "react";

import { LoadingBlock } from "@/components/host/common";
import { CalendarView } from "@/components/host/ops/calendar";

export const metadata: Metadata = { title: "Calendar" };

// Client-side auth gate + browser data fetching: navigations here may block.
export const instant = false;

export default function CalendarPage() {
  return (
    <Suspense fallback={<LoadingBlock rows={6} />}>
      <CalendarView />
    </Suspense>
  );
}
