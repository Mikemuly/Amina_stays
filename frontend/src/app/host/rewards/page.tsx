import type { Metadata } from "next";
import { Suspense } from "react";

import { LoadingBlock } from "@/components/host/common";
import { RewardsPage } from "@/components/host/biz/rewards";

// The console shell renders after a client-side auth check, so this segment is never prerendered.
export const instant = false;

export const metadata: Metadata = { title: "Rewards & airtime" };

export default function Page() {
  return (
    <Suspense fallback={<LoadingBlock rows={6} />}>
      <RewardsPage />
    </Suspense>
  );
}
