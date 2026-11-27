import type { Metadata } from "next";
import { Suspense } from "react";

import { SearchView } from "@/components/site/search-view";

export const metadata: Metadata = { title: "Homes on the Kenyan coast" };

export default function SearchPage() {
  return (
    <Suspense fallback={<div className="h-dvh" />}>
      <SearchView />
    </Suspense>
  );
}
