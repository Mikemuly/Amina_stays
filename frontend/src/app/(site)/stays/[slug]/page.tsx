import { Suspense } from "react";

import { ListingView } from "@/components/site/listing-view";

export default function StayPage({ params }: { params: Promise<{ slug: string }> }) {
  return (
    <Suspense fallback={<div className="h-dvh" />}>
      <Resolve params={params} />
    </Suspense>
  );
}

async function Resolve({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <ListingView slug={slug} />;
}
