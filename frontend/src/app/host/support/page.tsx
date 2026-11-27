import type { Metadata } from "next";
import { Suspense } from "react";

import { LoadingBlock } from "@/components/host/common";
import { SupportPage } from "@/components/host/biz/support";

// The console shell renders after a client-side auth check, so this segment is never prerendered.
export const instant = false;

export const metadata: Metadata = { title: "Support desk" };

export default function Page() {
  return (
    <Suspense fallback={<LoadingBlock rows={6} />}>
      <SupportPage />
    </Suspense>
  );
}
