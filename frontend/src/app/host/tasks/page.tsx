import type { Metadata } from "next";
import { Suspense } from "react";

import { LoadingBlock } from "@/components/host/common";
import { TasksView } from "@/components/host/ops/tasks";

export const metadata: Metadata = { title: "Housekeeping & tasks" };

// Client-side auth gate + browser data fetching: navigations here may block.
export const instant = false;

export default function TasksPage() {
  return (
    <Suspense fallback={<LoadingBlock rows={6} />}>
      <TasksView />
    </Suspense>
  );
}
