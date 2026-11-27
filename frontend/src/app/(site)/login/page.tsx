import type { Metadata } from "next";
import { Suspense } from "react";

import { LoginView } from "@/components/site/login-view";

export const metadata: Metadata = { title: "Log in" };

export default function Page() {
  return (
    <Suspense fallback={<div className="h-dvh" />}>
      <LoginView />
    </Suspense>
  );
}
