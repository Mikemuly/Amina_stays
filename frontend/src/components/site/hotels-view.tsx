"use client";

import * as React from "react";

import { CarouselRow } from "@/components/site/carousel";
import { ExtraCard, ExtraDialog, Intro, useAddons } from "@/components/site/extras";
import { MobileTabs, SiteHeader } from "@/components/site/header";
import { useHomes, WhyDirect } from "@/components/site/home-view";
import { ListingCard, ListingCardSkeleton } from "@/components/site/listing-card";
import type { Addon } from "@/lib/types";

// Amina has no hotels: this tab gathers the serviced apartments and studios, plus the services that make them hotel-like.
const SERVICED_TYPES = ["apartment", "studio", "penthouse", "room"];
const HOTEL_SERVICES = ["breakfast", "cleaning", "transport", "flexibility"];

export function HotelsView() {
  const { data, isLoading } = useHomes();
  const { data: addons } = useAddons();
  const [open, setOpen] = React.useState<Addon | null>(null);
  const stays = (data?.results ?? []).filter((l) => SERVICED_TYPES.includes(l.property_type)).sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0));
  const services = (addons ?? []).filter((a) => HOTEL_SERVICES.includes(a.category));
  return (
    <>
      <SiteHeader mode="home" tab="hotels" mobileSearch />
      <MobileTabs active="hotels" />
      <main className="container-site pb-16">
        <Intro
          title="Hotel comforts, home space"
          text="Serviced apartments and studios with breakfast on your veranda, fresh towels mid-stay, airport pickups and a HELP line that rings Amina day or night — at a home's price."
        />
        <div className="mt-8 grid gap-x-6 gap-y-10 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {isLoading ? Array.from({ length: 4 }).map((_, i) => <ListingCardSkeleton key={i} />) : stays.map((l, i) => <ListingCard key={l.id} listing={l} priority={i < 4} />)}
        </div>
        {services.length > 0 && (
          <CarouselRow title="Hotel-style services" subtitle="Add them at checkout, from your trip page or with a one-word SMS" href="/services" className="pt-14 md:pt-16">
            {services.map((a) => <ExtraCard key={a.code} addon={a} onOpen={() => setOpen(a)} />)}
          </CarouselRow>
        )}
        <WhyDirect />
      </main>
      <ExtraDialog addon={open} onClose={() => setOpen(null)} />
    </>
  );
}
