import type { Metadata } from "next";
import { Suspense } from "react";

import { CardPayView } from "@/components/site/card-pay-view";

export const metadata: Metadata = { title: "Secure checkout", robots: { index: false } };

export default function Page({ params }: { params: Promise<{ token: string }> }) {
  return (
    <Suspense fallback={<div className="h-dvh bg-surface" />}>
      <Resolve params={params} />
    </Suspense>
  );
}

async function Resolve({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <CardPayView token={token} />;
}
