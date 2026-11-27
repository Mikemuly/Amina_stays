import type { Metadata } from "next";
import { Suspense } from "react";

import { LoadingBlock } from "@/components/host/common";
import { KitchenView } from "@/components/host/ops/kitchen";

export const metadata: Metadata = { title: "Breakfast & kitchen" };

// Client-side auth gate + browser data fetching: navigations here may block.
export const instant = false;

export default function KitchenPage() {
  return (
    <Suspense fallback={<LoadingBlock rows={6} />}>
      <KitchenView />
    </Suspense>
  );
}
