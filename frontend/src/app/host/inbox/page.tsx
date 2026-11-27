import type { Metadata } from "next";
import { Suspense } from "react";

import { LoadingBlock } from "@/components/host/common";
import { InboxView } from "@/components/host/ops/inbox";

export const metadata: Metadata = { title: "Inbox" };

// Client-side auth gate + browser data fetching: navigations here may block.
export const instant = false;

// InboxView reads the selected thread from ?t= (useSearchParams), so it must sit under Suspense.
export default function InboxPage() {
  return (
    <Suspense fallback={<LoadingBlock rows={8} />}>
      <InboxView />
    </Suspense>
  );
}
