import { Suspense } from "react";

import { HomeView } from "@/components/site/home-view";

export default function HomePage() {
  return (
    <Suspense fallback={<div className="h-dvh" />}>
      <HomeView />
    </Suspense>
  );
}
