import type { Metadata } from "next";
import { Suspense } from "react";

import { HomeView } from "@/components/site/home-view";

export const metadata: Metadata = { title: "Homes on the coast" };

export default function HomesPage() {
  return (
    <Suspense fallback={<div className="h-dvh" />}>
      <HomeView tab="homes" />
    </Suspense>
  );
}
