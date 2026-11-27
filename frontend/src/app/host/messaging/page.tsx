import type { Metadata } from "next";
import { Suspense } from "react";

import { LoadingBlock } from "@/components/host/common";
import { MessagingPage } from "@/components/host/biz/messaging";

// The console shell renders after a client-side auth check, so this segment is never prerendered.
export const instant = false;

export const metadata: Metadata = { title: "Messaging & automations" };

export default function Page() {
  return (
    <Suspense fallback={<LoadingBlock rows={6} />}>
      <MessagingPage />
    </Suspense>
  );
}
