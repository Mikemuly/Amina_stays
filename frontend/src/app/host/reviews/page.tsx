import type { Metadata } from "next";
import { Suspense } from "react";

import { LoadingBlock } from "@/components/host/common";
import { ReviewsPage } from "@/components/host/biz/reviews";

// The console shell renders after a client-side auth check, so this segment is never prerendered.
export const instant = false;

export const metadata: Metadata = { title: "Reviews" };

export default function Page() {
  return (
    <Suspense fallback={<LoadingBlock rows={5} />}>
      <ReviewsPage />
    </Suspense>
  );
}
