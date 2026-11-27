import type { Metadata } from "next";
import { Suspense } from "react";

import { CheckoutView } from "@/components/site/checkout-view";

export const metadata: Metadata = { title: "Confirm and pay" };

export default function BookPage({ params }: { params: Promise<{ slug: string }> }) {
  return (
    <Suspense fallback={<div className="h-dvh" />}>
      <Resolve params={params} />
    </Suspense>
  );
}

async function Resolve({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <CheckoutView slug={slug} />;
}
