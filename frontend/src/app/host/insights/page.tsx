import type { Metadata } from "next";
import { Suspense } from "react";

import { LoadingBlock } from "@/components/host/common";
import { InsightsPage } from "@/components/host/biz/insights";

// The console shell renders after a client-side auth check, so this segment is never prerendered.
export const instant = false;

export const metadata: Metadata = { title: "Insights" };

export default function Page() {
  return (
    <Suspense fallback={<LoadingBlock rows={6} />}>
      <InsightsPage />
    </Suspense>
  );
}
