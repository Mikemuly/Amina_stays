import type { Metadata } from "next";
import { Suspense } from "react";

import { LoadingBlock } from "@/components/host/common";
import { NoticesPage } from "@/components/host/biz/notices";

// The console shell renders after a client-side auth check, so this segment is never prerendered.
export const instant = false;

export const metadata: Metadata = { title: "Service alerts" };

export default function Page() {
  return (
    <Suspense fallback={<LoadingBlock rows={6} />}>
      <NoticesPage />
    </Suspense>
  );
}
