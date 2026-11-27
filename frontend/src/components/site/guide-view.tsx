"use client";

import { useQuery } from "@tanstack/react-query";
import { CalendarDays, Clock, Lightbulb, MapPin, Navigation, Phone, Ticket } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { useConfig } from "@/components/providers";
import { SiteHeader } from "@/components/site/header";
import { Intro } from "@/components/site/extras";
import { Icon3D, type Icon3DName } from "@/components/ui/icon3d";
import { Badge } from "@/components/ui/misc";
import { get } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { GuideData, GuideEvent, GuidePlace } from "@/lib/types";
import { cn } from "@/lib/utils";

export const CATEGORY_ICON: Record<string, Icon3DName> = {
  sights: "classical-building",
  beaches: "beach",
  nature: "palm-tree",
  food: "cooking",
  markets: "shopping-cart",
  culture: "sparkles",
  evenings: "sunset",
  transport: "train",
  essentials: "shield",
};

function useGuide() {
  return useQuery({ queryKey: ["guide"], queryFn: () => get<GuideData>("/api/guide"), staleTime: 5 * 60_000 });
}

/** The public local guide: the same places guests get by USSD (More → Explore), SMS (EXPLORE) or a call (press 6). */
export function GuideView() {
  const { data, isLoading } = useGuide();
  const { data: config } = useConfig();
  const [category, setCategory] = React.useState("all");
  const [area, setArea] = React.useState("all");
  const c = config?.channels;

  // deep links from the footer (/guide#fort-jesus): scroll once the places have loaded
  React.useEffect(() => {
    if (!data || !window.location.hash) return;
    const el = document.getElementById(decodeURIComponent(window.location.hash.slice(1)));
    if (el) el.scrollIntoView({ block: "start" });
  }, [data]);
  // ...and when the link is followed from this page: clear the filters first, or the place may be hidden
  React.useEffect(() => {
    const go = () => {
      const id = decodeURIComponent(window.location.hash.slice(1));
      if (!id) return;
      setCategory("all");
      setArea("all");
      setTimeout(() => document.getElementById(id)?.scrollIntoView({ block: "start" }), 60);
    };
    window.addEventListener("hashchange", go);
    return () => window.removeEventListener("hashchange", go);
  }, []);

  const places = (data?.places ?? []).filter((p) => (category === "all" || p.category === category) && (area === "all" || p.area?.slug === area));
  const featured = category === "all" && area === "all" ? places.filter((p) => p.featured) : [];
  const rest = featured.length ? places.filter((p) => !p.featured) : places;

  return (
    <>
      <SiteHeader mode="compact" />
      <main className="container-site pb-20">
        <Intro
          title="Explore the coast like a local"
          text="Amina's own guide to Mombasa and the south and north coast: what to see, where to eat, how to get around, and what's on this week."
        />
        <div className="mt-5 flex flex-wrap gap-2 text-[13px] text-ink-2">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-surface px-3 py-1.5">
            <Icon3D name="mobile-phone" size={18} /> No data? Dial {c?.ussd_code || "our USSD code"} → More → Explore
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-surface px-3 py-1.5">
            <Icon3D name="speech-balloon" size={18} /> Text EXPLORE{c?.sms_number ? ` to ${c.sms_number}` : ""}
          </span>
          {c?.voice_number && (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-surface px-3 py-1.5">
              <Phone className="size-3.5" /> Call {c.voice_number} and press 6
            </span>
          )}
        </div>

        <div className="no-scrollbar -mx-6 mt-8 flex gap-2 overflow-x-auto px-6 pb-1 md:mx-0 md:flex-wrap md:px-0" role="tablist" aria-label="Categories">
          <Chip on={category === "all"} onClick={() => setCategory("all")} icon="globe">Everything</Chip>
          {(data?.categories ?? []).map((cat) => (
            <Chip key={cat.key} on={category === cat.key} onClick={() => setCategory(cat.key)} icon={CATEGORY_ICON[cat.key] ?? "pushpin"}>
              {cat.label} <span className="text-ink-3">{cat.count}</span>
            </Chip>
          ))}
        </div>
        {(data?.areas.length ?? 0) > 1 && (
          <div className="no-scrollbar -mx-6 mt-3 flex gap-2 overflow-x-auto px-6 md:mx-0 md:flex-wrap md:px-0" aria-label="Areas">
            {[{ slug: "all", name: "All areas" }, ...(data?.areas ?? [])].map((a) => (
              <button
                key={a.slug}
                type="button"
                onClick={() => setArea(a.slug)}
                className={cn(
                  "h-8 shrink-0 rounded-full border px-3 text-[13px] whitespace-nowrap transition-colors",
                  area === a.slug ? "border-ink bg-ink text-white" : "border-line text-ink hover:border-ink",
                )}
              >
                {a.name}
              </button>
            ))}
          </div>
        )}

        {isLoading ? (
          <div className="mt-8 grid gap-6 sm:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => <div key={i} className="h-56 animate-pulse rounded-2xl bg-line-soft" />)}
          </div>
        ) : places.length === 0 ? (
          <p className="mt-10 text-ink-2">Nothing here yet — try another category, or text Amina for her personal tips.</p>
        ) : (
          <>
            {featured.length > 0 && (
              <section className="mt-10">
                <h2 className="text-[22px] font-semibold tracking-tight">Top picks</h2>
                <div className="mt-4 grid gap-6 sm:grid-cols-2 xl:grid-cols-3">
                  {featured.map((p) => <PlaceCard key={p.id} place={p} />)}
                </div>
              </section>
            )}
            {rest.length > 0 && (
              <section className="mt-12">
                {featured.length > 0 && <h2 className="text-[22px] font-semibold tracking-tight">More to discover</h2>}
                <div className={cn("grid gap-6 sm:grid-cols-2 xl:grid-cols-3", featured.length > 0 ? "mt-4" : "mt-8")}>
                  {rest.map((p) => <PlaceCard key={p.id} place={p} />)}
                </div>
              </section>
            )}
          </>
        )}

        {(data?.events.length ?? 0) > 0 && (
          <section className="mt-16">
            <h2 className="text-[22px] font-semibold tracking-tight">What&apos;s on</h2>
            <p className="mt-0.5 text-sm text-ink-2">The next two weeks. Text EVENTS any time for the list.</p>
            <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {data!.events.map((e) => <EventCard key={`${e.id}-${e.date}`} event={e} />)}
            </div>
          </section>
        )}
      </main>
    </>
  );
}

function Chip({ on, onClick, icon, children }: { on: boolean; onClick: () => void; icon: Icon3DName; children: React.ReactNode }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={on}
      onClick={onClick}
      className={cn(
        "flex h-10 shrink-0 items-center gap-1.5 rounded-full border pr-3.5 pl-2 text-sm whitespace-nowrap transition-colors",
        on ? "border-ink bg-chip font-medium text-ink" : "border-line bg-white text-ink hover:border-ink",
      )}
    >
      <Icon3D name={icon} size={24} />
      {children}
    </button>
  );
}

export function PlaceCard({ place: p, compact = false }: { place: GuidePlace; compact?: boolean }) {
  return (
    <article id={p.slug} className="flex scroll-mt-28 flex-col rounded-2xl border border-line-soft bg-white p-5">
      <div className="flex items-start gap-3">
        <span className="grid size-12 shrink-0 place-items-center rounded-xl bg-surface">
          <Icon3D name={CATEGORY_ICON[p.category] ?? "pushpin"} size={32} />
        </span>
        <div className="min-w-0">
          <h3 className="text-[17px] leading-snug font-semibold">{p.name}</h3>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-[13px] text-ink-2">
            {p.area && <span>{p.area.name}</span>}
            {p.area && <span aria-hidden>·</span>}
            <span>{p.category_label}</span>
            {p.distance_km != null && (
              <>
                <span aria-hidden>·</span>
                <span>{p.distance_km < 1 ? "under 1 km" : `${p.distance_km} km`} away</span>
              </>
            )}
          </p>
        </div>
        {p.featured && !compact && <Badge tone="brand" className="ml-auto shrink-0">Top pick</Badge>}
      </div>
      <p className="mt-3 text-[15px] leading-relaxed text-ink">{p.summary}</p>
      {!compact && p.description && <p className="mt-2 text-[14px] leading-relaxed text-ink-2">{p.description}</p>}
      {!compact && (p.hours || p.price) && (
        <dl className="mt-3 space-y-1 text-[13.5px] text-ink-2">
          {p.hours && (
            <div className="flex gap-2">
              <dt className="sr-only">Hours</dt>
              <Clock className="mt-0.5 size-4 shrink-0" aria-hidden />
              <dd>{p.hours}</dd>
            </div>
          )}
          {p.price && (
            <div className="flex gap-2">
              <dt className="sr-only">Price</dt>
              <Ticket className="mt-0.5 size-4 shrink-0" aria-hidden />
              <dd>{p.price}</dd>
            </div>
          )}
        </dl>
      )}
      {!compact && p.tips && (
        <p className="mt-3 flex gap-2 rounded-xl bg-sand-50 px-3 py-2 text-[13.5px] text-ink">
          <Lightbulb className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
          <span>{p.tips}</span>
        </p>
      )}
      <div className="mt-auto pt-4">
        <a href={p.map_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 text-sm font-semibold underline underline-offset-2">
          <Navigation className="size-4" aria-hidden /> Directions
        </a>
      </div>
    </article>
  );
}

function EventCard({ event: e }: { event: GuideEvent }) {
  return (
    <div className="flex gap-4 rounded-2xl border border-line-soft bg-white p-4">
      <div className="grid w-14 shrink-0 place-items-center rounded-xl bg-surface py-2 text-center">
        <span className="text-[11px] font-semibold text-brand-600 uppercase">{fmtDate(e.date, "EEE")}</span>
        <span className="text-xl leading-none font-semibold">{fmtDate(e.date, "d")}</span>
        <span className="text-[11px] text-ink-2">{fmtDate(e.date, "MMM")}</span>
      </div>
      <div className="min-w-0">
        <p className="font-semibold">{e.title}</p>
        {e.summary && <p className="mt-0.5 text-[14px] text-ink-2">{e.summary}</p>}
        <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-ink-2">
          {e.time && <span className="inline-flex items-center gap-1"><Clock className="size-3.5" aria-hidden /> {e.time}</span>}
          {(e.place || e.area) && (
            <span className="inline-flex items-center gap-1">
              <MapPin className="size-3.5" aria-hidden />
              {e.place ? <a href={`#${e.place.slug}`} className="underline">{e.place.name}</a> : e.area}
            </span>
          )}
          {e.weekly && <span className="inline-flex items-center gap-1"><CalendarDays className="size-3.5" aria-hidden /> Every week</span>}
        </p>
        {e.price && <p className="mt-1 text-[13px] text-ink">{e.price}</p>}
        {e.addon_code && <Link href="/experiences" className="mt-1 inline-block text-[13px] font-semibold underline">See the experience</Link>}
      </div>
    </div>
  );
}

/** "Near your home" on a trip page: the four closest things to do, by distance from the home. */
export function NearbyPlaces({ unitSlug }: { unitSlug: string }) {
  const { data } = useQuery({
    queryKey: ["guide", "nearby", unitSlug],
    queryFn: () => get<GuidePlace[]>(`/api/guide/nearby/${unitSlug}?limit=4`),
    staleTime: 10 * 60_000,
  });
  if (!data?.length) return null;
  return (
    <div>
      <div className="grid gap-4 sm:grid-cols-2">
        {data.map((p) => <PlaceCard key={p.id} place={p} compact />)}
      </div>
      <Link href="/guide" className="mt-4 inline-block text-sm font-semibold underline underline-offset-2">
        The full local guide
      </Link>
    </div>
  );
}
