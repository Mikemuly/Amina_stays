"use client";

import { useQuery } from "@tanstack/react-query";
import { Heart } from "lucide-react";
import Link from "next/link";

import { AuthGate } from "@/components/site/auth-gate";
import { SiteHeader } from "@/components/site/header";
import { ListingCard, ListingCardSkeleton } from "@/components/site/listing-card";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/misc";
import { get } from "@/lib/api";
import type { ListingCard as Card } from "@/lib/types";

export function WishlistsView() {
  return (
    <AuthGate title="Log in to see your wishlist">
      <Wishlist />
    </AuthGate>
  );
}

function Wishlist() {
  const { data, isLoading } = useQuery({ queryKey: ["wishlist"], queryFn: () => get<Card[]>("/api/me/wishlist") });
  return (
    <>
      <SiteHeader />
      <main className="container-site pt-10 pb-24">
        <h1 className="text-[32px] font-bold tracking-tight">Wishlist</h1>
        {isLoading ? (
          <div className="mt-8 grid gap-x-6 gap-y-10 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">{[0, 1, 2, 3].map((i) => <ListingCardSkeleton key={i} />)}</div>
        ) : !data?.length ? (
          <div className="mt-8 rounded-2xl border border-line-soft">
            <EmptyState icon={<Heart className="size-10" strokeWidth={1.3} />} title="Save the homes you love" action={<Button asChild size="lg"><Link href="/">Explore homes</Link></Button>}>
              Tap the heart on any home to keep it here — handy when you&apos;re planning with family or waiting for dates to open up.
            </EmptyState>
          </div>
        ) : (
          <div className="mt-8 grid gap-x-6 gap-y-10 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {data.map((l, i) => <ListingCard key={l.slug} listing={l} priority={i < 4} />)}
          </div>
        )}
      </main>
    </>
  );
}
