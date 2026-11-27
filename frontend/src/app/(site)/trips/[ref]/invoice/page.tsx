import type { Metadata } from "next";
import { Suspense } from "react";

import { InvoiceView } from "@/components/site/invoice-view";

export const metadata: Metadata = { title: "Tax invoice", robots: { index: false } };

export default function Page({ params }: { params: Promise<{ ref: string }> }) {
  return (
    <Suspense fallback={<div className="h-dvh" />}>
      <Resolve params={params} />
    </Suspense>
  );
}

async function Resolve({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  return <InvoiceView bookingRef={ref.toUpperCase()} />;
}
