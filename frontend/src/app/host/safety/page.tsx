import type { Metadata } from "next";
import { Suspense } from "react";

import { LoadingBlock } from "@/components/host/common";
import { SafetyPage } from "@/components/host/biz/safety";

// The console shell renders after a client-side auth check, so this segment is never prerendered.
export const instant = false;

export const metadata: Metadata = { title: "Safety & compliance" };

export default function Page() {
  return (
    <Suspense fallback={<LoadingBlock rows={6} />}>
      <SafetyPage />
    </Suspense>
  );
}
