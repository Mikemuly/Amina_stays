"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { List, Map as MapIcon, Maximize2, Minimize2, SlidersHorizontal, X } from "lucide-react";
import dynamic from "next/dynamic";
import { useRouter, useSearchParams } from "next/navigation";
import { Dialog as D } from "radix-ui";
import * as React from "react";

import { SiteHeader } from "@/components/site/header";
import { ListingCard, ListingCardSkeleton } from "@/components/site/listing-card";
import { useMoney } from "@/components/site/locale";
import { searchQuery, useAreas, useSearchState } from "@/components/site/search-bar";
import { Button } from "@/components/ui/button";
import { Icon3D, type Icon3DName } from "@/components/ui/icon3d";
import { Stepper } from "@/components/ui/misc";
import { get, qs } from "@/lib/api";
import type { ListingCard as Card } from "@/lib/types";
import { cn } from "@/lib/utils";

const ListingsMap = dynamic(() => import("@/components/site/maps"), { ssr: false, loading: () => <div className="size-full animate-pulse bg-surface" /> });

type Results = { results: Card[]; count: number; nights: number | null };
type Filters = {
  tag?: string; type?: string; bedrooms?: string; amenities?: string; min_price?: string; max_price?: string; free_cancellation?: string; guest_favourite?: string; sort?: string;
};
const FILTER_PARAMS: (keyof Filters)[] = ["tag", "type", "bedrooms", "amenities", "min_price", "max_price", "free_cancellation", "guest_favourite", "sort"];

// Quick filters in the bar: Airbnb's booking-confidence chips first, then categories (tags) and the
// amenities people filter on most.
const QUICK: { label: string; tag?: string; amenity?: string; flag?: "free_cancellation" | "guest_favourite" }[] = [
  { label: "Free cancellation", flag: "free_cancellation" },
  { label: "Guest favourite", flag: "guest_favourite" },
  { label: "Beachfront", tag: "beachfront" },
  { label: "Pool", amenity: "pool" },
  { label: "Family-friendly", tag: "family" },
  { label: "Breakfast", amenity: "breakfast_service" },
  { label: "Self check-in", amenity: "self_checkin" },
  { label: "Air conditioning", amenity: "ac" },
  { label: "Kitchen", amenity: "kitchen" },
  { label: "Workspace", amenity: "workspace" },
  { label: "Ocean views", tag: "ocean-view" },
  { label: "Historic", tag: "historic" },
  { label: "Creek & nature", tag: "creek" },
  { label: "Backup power", amenity: "backup_power" },
  { label: "Great value", tag: "budget" },
];

const AMENITIES: { code: string; label: string }[] = [
  { code: "wifi", label: "Wi-Fi" }, { code: "kitchen", label: "Kitchen" }, { code: "washer", label: "Washer" }, { code: "ac", label: "Air conditioning" },
  { code: "pool", label: "Pool" }, { code: "parking", label: "Free parking" }, { code: "workspace", label: "Workspace" }, { code: "tv", label: "TV" },
  { code: "backup_power", label: "Backup power" }, { code: "beach_access", label: "Beach access" }, { code: "ocean_view", label: "Ocean view" },
  { code: "crib", label: "Cot" }, { code: "bbq", label: "BBQ grill" }, { code: "garden", label: "Garden" }, { code: "security_guard", label: "24h security" },
  { code: "mosquito_nets", label: "Mosquito nets" },
];

const TYPES: { code: string; label: string; icon: Icon3DName }[] = [
  { code: "apartment", label: "Apartment", icon: "classical-building" },
  { code: "house", label: "House", icon: "house" },
  { code: "cottage", label: "Cottage", icon: "hut" },
  { code: "studio", label: "Studio", icon: "bed" },
];

function readFilters(p: URLSearchParams): Filters {
  const f: Filters = {};
  FILTER_PARAMS.forEach((k) => {
    const v = p.get(k);
    if (v) f[k] = v;
  });
  return f;
}

const csv = (v?: string) => (v ? v.split(",").filter(Boolean) : []);
const toggleCsv = (v: string | undefined, item: string) => {
  const list = csv(v);
  const next = list.includes(item) ? list.filter((x) => x !== item) : [...list, item];
  return next.length ? next.join(",") : undefined;
};

export function SearchView() {
  const params = useSearchParams();
  const router = useRouter();
  const s = useSearchState();
  const guests = s.adults + s.children;
  const filters = readFilters(params);
  const base = { check_in: s.checkIn, check_out: s.checkOut, guests: guests || undefined, area: s.area };
  const apiQuery = qs({ ...base, ...filters });
  const { data, isLoading, isFetching, error } = useQuery({
    queryKey: ["listings", apiQuery],
    queryFn: () => get<Results>(`/api/listings${apiQuery}`),
    placeholderData: keepPreviousData,
  });
  const { data: areas } = useAreas();
  const [hoverId, setHoverId] = React.useState<number | null>(null);
  const [mapOnly, setMapOnly] = React.useState(false);
  const [mobileMap, setMobileMap] = React.useState(false);
  const [filtersOpen, setFiltersOpen] = React.useState(false);

  const listings = data?.results ?? [];
  const linkQuery = searchQuery(s);
  const areaName = areas?.find((a) => a.slug === s.area)?.name;
  const count = data?.count ?? 0;
  const activeCount = [filters.type, filters.bedrooms, filters.min_price || filters.max_price, filters.free_cancellation, filters.guest_favourite, ...csv(filters.amenities)].filter(Boolean).length;

  const setFilters = (patch: Partial<Filters>) => {
    const q = new URLSearchParams(params.toString());
    Object.entries(patch).forEach(([k, v]) => (v ? q.set(k, v) : q.delete(k)));
    const out = q.toString();
    router.replace(`/s${out ? `?${out}` : ""}`, { scroll: false });
  };
  const clearFilters = () => setFilters(Object.fromEntries(FILTER_PARAMS.map((k) => [k, undefined])));

  const heading = isLoading ? "Finding homes…" : `${count} home${count === 1 ? "" : "s"} ${areaName ? `in ${areaName}` : "on the Mombasa coast"}`;

  return (
    <>
      <SiteHeader mode="compact" mobileSearch>
        <div className="border-b border-line-soft bg-white">
          <div className="container-site flex h-16 items-center gap-3">
            <button
              type="button"
              onClick={() => setFiltersOpen(true)}
              className="relative flex h-10 shrink-0 items-center gap-2 rounded-full border border-line px-4 text-xs font-medium transition-colors hover:border-ink"
            >
              <SlidersHorizontal className="size-4" strokeWidth={2} /> Filters
              {activeCount > 0 && <span className="absolute -top-1 -right-1 grid size-5 place-items-center rounded-full bg-ink text-[10px] font-semibold text-white">{activeCount}</span>}
            </button>
            <span className="h-8 w-px shrink-0 bg-line" />
            <div className="no-scrollbar -mr-6 flex flex-1 gap-2 overflow-x-auto pr-6 md:mr-0 md:pr-0">
              {QUICK.map((q) => {
                const on = q.flag ? !!filters[q.flag] : q.tag ? filters.tag === q.tag : csv(filters.amenities).includes(q.amenity!);
                const toggle = (): Partial<Filters> =>
                  q.flag ? { [q.flag]: on ? undefined : "1" } : q.tag ? { tag: on ? undefined : q.tag } : { amenities: toggleCsv(filters.amenities, q.amenity!) };
                return (
                  <button
                    key={q.label}
                    type="button"
                    aria-pressed={on}
                    onClick={() => setFilters(toggle())}
                    className={cn(
                      "h-[34px] shrink-0 rounded-3xl border px-3 text-xs whitespace-nowrap transition-colors",
                      on ? "border-ink bg-surface font-medium shadow-[inset_0_0_0_1px_var(--color-ink)]" : "border-line hover:border-ink",
                    )}
                  >
                    {q.label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </SiteHeader>

      <main className={cn("container-site pb-10", mapOnly ? "lg:grid-cols-1" : "lg:grid lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] lg:gap-12")}>
        <div className={cn(mapOnly && "lg:hidden")}>
          <div className="flex items-end justify-between gap-4 pt-6 pb-5">
            <h1 className="text-lg font-semibold tracking-[-0.18px] md:text-xl">{heading}</h1>
            <p className="hidden shrink-0 items-center gap-1 text-sm text-ink-2 sm:flex">
              <Icon3D name="label" size={20} /> Prices include all fees
            </p>
          </div>
          {error ? (
            <NoResults title="We couldn't load homes" text={(error as Error).message} action={<Button variant="soft" onClick={() => location.reload()}>Try again</Button>} />
          ) : (
            <div className={cn("grid gap-x-6 gap-y-10 transition-opacity sm:grid-cols-2 min-[1880px]:grid-cols-3", isFetching && !isLoading && "opacity-60")}>
              {isLoading
                ? Array.from({ length: 4 }).map((_, i) => <ListingCardSkeleton key={i} />)
                : listings.map((l, i) => (
                    <ListingCard key={l.id} listing={l} query={linkQuery} priority={i < 2} checkIn={s.checkIn} checkOut={s.checkOut} onHover={setHoverId} />
                  ))}
              {!isLoading && !listings.length && (
                <div className="col-span-full">
                  <NoResults
                    title="No exact matches"
                    text={
                      activeCount || filters.tag
                        ? "Try changing or removing some of your filters, or adjusting your dates."
                        : "Nothing is free for those dates. Try nearby dates or another neighbourhood — or text Amina your dates and she'll SMS you the moment something opens up."
                    }
                    action={
                      activeCount || filters.tag ? (
                        <Button variant="outline" onClick={clearFilters}>Remove all filters</Button>
                      ) : (
                        <Button variant="outline" onClick={() => router.push("/s")}>Clear search</Button>
                      )
                    }
                  />
                </div>
              )}
            </div>
          )}
        </div>

        <div className="hidden lg:block">
          <div className="sticky top-[168px] mt-6 h-[calc(100dvh-192px)] overflow-hidden rounded-3xl">
            <ListingsMap listings={listings} query={linkQuery} hoverId={hoverId} resizeToken={mapOnly} />
            <button
              type="button"
              onClick={() => setMapOnly(!mapOnly)}
              aria-label={mapOnly ? "Show list" : "Expand map"}
              className="absolute top-4 left-4 z-[500] grid size-10 place-items-center rounded-lg bg-white shadow-[0_0_0_1px_rgb(0_0_0/0.08),0_2px_4px_rgb(0_0_0/0.18)] transition-transform hover:scale-105"
            >
              {mapOnly ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
            </button>
          </div>
        </div>
      </main>

      {/* phones: full-screen map toggle */}
      {!!listings.length && (
        <div className="pointer-events-none fixed inset-x-0 bottom-24 z-30 flex justify-center lg:hidden">
          <Button onClick={() => setMobileMap(true)} className="pointer-events-auto h-12 rounded-full px-5 shadow-float">
            Map <MapIcon className="size-4" />
          </Button>
        </div>
      )}
      {mobileMap && (
        <div className="fixed inset-0 z-50 bg-white lg:hidden">
          <ListingsMap listings={listings} query={linkQuery} resizeToken={mobileMap} />
          <div className="pointer-events-none absolute inset-x-0 bottom-8 z-[500] flex justify-center">
            <Button onClick={() => setMobileMap(false)} className="pointer-events-auto h-12 rounded-full px-5 shadow-float">
              List <List className="size-4" />
            </Button>
          </div>
        </div>
      )}

      <FiltersDialog open={filtersOpen} onOpenChange={setFiltersOpen} base={base} filters={filters} onApply={(f) => setFilters(f)} />
    </>
  );
}

function NoResults({ title, text, action }: { title: string; text: string; action: React.ReactNode }) {
  return (
    <div className="max-w-md py-10">
      <h2 className="text-[22px] font-semibold">{title}</h2>
      <p className="mt-2 text-ink-2">{text}</p>
      <div className="mt-6">{action}</div>
    </div>
  );
}

// ---------------------------------------------------------------- filters dialog

function FiltersDialog({ open, onOpenChange, base, filters, onApply }: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  base: Record<string, string | number | undefined>;
  filters: Filters;
  onApply: (f: Partial<Filters>) => void;
}) {
  const [draft, setDraft] = React.useState<Filters>(filters);
  const [wasOpen, setWasOpen] = React.useState(open);
  if (open !== wasOpen) {
    // re-seed the draft from the URL every time the dialog opens
    setWasOpen(open);
    if (open) setDraft(filters);
  }
  const [allAmenities, setAllAmenities] = React.useState(false);
  const set = (patch: Partial<Filters>) => setDraft((d) => ({ ...d, ...patch }));

  // every home for this search (no filters) drives the price histogram; the filtered count drives the button
  const pool = useQuery({ queryKey: ["listings", qs(base)], queryFn: () => get<Results>(`/api/listings${qs(base)}`), enabled: open });
  const countQuery = qs({ ...base, ...draft });
  const preview = useQuery({ queryKey: ["listings", countQuery], queryFn: () => get<Results>(`/api/listings${countQuery}`), enabled: open, placeholderData: keepPreviousData });

  const prices = (pool.data?.results ?? []).map((l) => l.price.avg_nightly ?? l.price.from_nightly);
  const floor = prices.length ? Math.floor(Math.min(...prices) / 500) * 500 : 0;
  const ceil = prices.length ? Math.ceil(Math.max(...prices) / 500) * 500 : 20000;
  const lo = Number(draft.min_price || floor);
  const hi = Number(draft.max_price || ceil);
  const amenityList = allAmenities ? AMENITIES : AMENITIES.slice(0, 8);

  const recommended: { label: string; icon: Icon3DName; on: boolean; toggle: () => void }[] = [
    { label: "Free cancellation", icon: "spiral-calendar", on: !!draft.free_cancellation, toggle: () => set({ free_cancellation: draft.free_cancellation ? undefined : "1" }) },
    { label: "Guest favourite", icon: "trophy", on: !!draft.guest_favourite, toggle: () => set({ guest_favourite: draft.guest_favourite ? undefined : "1" }) },
    { label: "Self check-in", icon: "key", on: csv(draft.amenities).includes("self_checkin"), toggle: () => set({ amenities: toggleCsv(draft.amenities, "self_checkin") }) },
    { label: "Breakfast", icon: "croissant", on: csv(draft.amenities).includes("breakfast_service"), toggle: () => set({ amenities: toggleCsv(draft.amenities, "breakfast_service") }) },
  ];

  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-50 bg-black/50 animate-fade-in" />
        <D.Content
          aria-describedby={undefined}
          className="fixed inset-x-0 bottom-0 z-50 flex max-h-[94dvh] flex-col rounded-t-2xl bg-white shadow-float outline-none animate-slide-up sm:top-1/2 sm:left-1/2 sm:max-h-[86dvh] sm:w-full sm:max-w-[780px] sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl"
        >
          <div className="relative flex h-16 shrink-0 items-center justify-center border-b border-line-soft">
            <D.Close className="absolute left-5 grid size-8 place-items-center rounded-full hover:bg-chip" aria-label="Close">
              <X className="size-4" strokeWidth={2.4} />
            </D.Close>
            <D.Title className="text-base font-semibold">Filters</D.Title>
          </div>
          <div className="min-h-0 flex-1 divide-y divide-line-soft overflow-y-auto px-6">
            <Section title="Recommended for you">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {recommended.map((r) => (
                  <button
                    key={r.label}
                    type="button"
                    aria-pressed={r.on}
                    onClick={r.toggle}
                    className={cn("flex flex-col items-center gap-2 rounded-xl border px-2 py-4 text-sm transition-colors", r.on ? "border-ink bg-surface shadow-[inset_0_0_0_1px_var(--color-ink)]" : "border-line hover:border-ink")}
                  >
                    <Icon3D name={r.icon} size={40} />
                    {r.label}
                  </button>
                ))}
              </div>
            </Section>

            <Section title="Price range" subtitle="Nightly prices, including cleaning and the tourism levy">
              <PriceRange prices={prices} floor={floor} ceil={ceil} lo={lo} hi={hi} onChange={(a, b) => set({ min_price: a > floor ? String(a) : undefined, max_price: b < ceil ? String(b) : undefined })} />
            </Section>

            <Section title="Rooms">
              <div className="flex items-center justify-between">
                <span>Bedrooms</span>
                <div className="flex items-center gap-3">
                  {!draft.bedrooms && <span className="text-sm text-ink-2">Any</span>}
                  <Stepper value={Number(draft.bedrooms || 0)} max={5} label="bedrooms" onChange={(v) => set({ bedrooms: v ? String(v) : undefined })} />
                </div>
              </div>
            </Section>

            <Section title="Amenities">
              <div className="flex flex-wrap gap-2">
                {amenityList.map((a) => {
                  const on = csv(draft.amenities).includes(a.code);
                  return (
                    <button
                      key={a.code}
                      type="button"
                      aria-pressed={on}
                      onClick={() => set({ amenities: toggleCsv(draft.amenities, a.code) })}
                      className={cn("h-10 rounded-full border px-4 text-sm transition-colors", on ? "border-ink bg-surface shadow-[inset_0_0_0_1px_var(--color-ink)]" : "border-line hover:border-ink")}
                    >
                      {a.label}
                    </button>
                  );
                })}
              </div>
              <button type="button" onClick={() => setAllAmenities(!allAmenities)} className="mt-4 text-sm font-semibold underline underline-offset-2">
                {allAmenities ? "Show less" : "Show more"}
              </button>
            </Section>

            <Section title="Property type">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {TYPES.map((t) => {
                  const on = csv(draft.type).includes(t.code);
                  return (
                    <button
                      key={t.code}
                      type="button"
                      aria-pressed={on}
                      onClick={() => set({ type: toggleCsv(draft.type, t.code) })}
                      className={cn("flex flex-col items-start gap-6 rounded-xl border p-4 text-left text-sm font-medium transition-colors", on ? "border-ink bg-surface shadow-[inset_0_0_0_1px_var(--color-ink)]" : "border-line hover:border-ink")}
                    >
                      <Icon3D name={t.icon} size={34} />
                      {t.label}
                    </button>
                  );
                })}
              </div>
            </Section>
          </div>
          <div className="flex shrink-0 items-center justify-between border-t border-line-soft px-6 py-4">
            <button type="button" className="text-base font-semibold underline underline-offset-2" onClick={() => setDraft({ tag: draft.tag })}>
              Clear all
            </button>
            <Button
              size="lg"
              onClick={() => {
                onApply({ ...Object.fromEntries(FILTER_PARAMS.map((k) => [k, undefined])), ...draft });
                onOpenChange(false);
              }}
            >
              {preview.data ? `Show ${preview.data.count} home${preview.data.count === 1 ? "" : "s"}` : "Show homes"}
            </Button>
          </div>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}

function Section({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="py-8">
      <h3 className="text-[22px] font-semibold tracking-tight">{title}</h3>
      {subtitle && <p className="mt-1 text-sm text-ink-2">{subtitle}</p>}
      <div className="mt-6">{children}</div>
    </section>
  );
}

/** Histogram of nightly prices with a two-thumb slider and min/max boxes. */
function PriceRange({ prices, floor, ceil, lo, hi, onChange }: { prices: number[]; floor: number; ceil: number; lo: number; hi: number; onChange: (lo: number, hi: number) => void }) {
  const bins = 24;
  const span = Math.max(ceil - floor, 1);
  const counts = Array.from({ length: bins }, () => 0);
  prices.forEach((p) => counts[Math.min(bins - 1, Math.floor(((p - floor) / span) * bins))]++);
  const peak = Math.max(1, ...counts);
  const pct = (v: number) => ((v - floor) / span) * 100;
  const step = 500;
  return (
    <div>
      <div className="flex h-16 items-end gap-[3px] px-4">
        {counts.map((c, i) => {
          const binLo = floor + (span / bins) * i;
          const inRange = binLo >= lo - 1 && binLo < hi;
          return <div key={i} className={cn("flex-1 rounded-t-sm", inRange ? "bg-brand-500" : "bg-line")} style={{ height: c ? `${18 + (c / peak) * 82}%` : 0 }} />;
        })}
      </div>
      <div className="relative mx-4 h-8">
        <div className="absolute inset-x-0 top-1/2 h-0.5 -translate-y-1/2 bg-line" />
        <div className="absolute top-1/2 h-0.5 -translate-y-1/2 bg-ink" style={{ left: `${pct(lo)}%`, right: `${100 - pct(hi)}%` }} />
        <input
          type="range"
          aria-label="Minimum price"
          className="dual-range"
          min={floor}
          max={ceil}
          step={step}
          value={lo}
          onChange={(e) => onChange(Math.min(Number(e.target.value), hi - step), hi)}
        />
        <input
          type="range"
          aria-label="Maximum price"
          className="dual-range"
          min={floor}
          max={ceil}
          step={step}
          value={hi}
          onChange={(e) => onChange(lo, Math.max(Number(e.target.value), lo + step))}
        />
      </div>
      <div className="mt-6 flex items-center justify-between gap-6">
        <PriceBox label="Minimum" value={lo} />
        <PriceBox label="Maximum" value={hi} plus={hi >= ceil} />
      </div>
    </div>
  );
}

function PriceBox({ label, value, plus }: { label: string; value: number; plus?: boolean }) {
  const money = useMoney();
  return (
    <div className="w-36 rounded-full border border-line px-5 py-2 text-center">
      <p className="text-xs text-ink-2">{label}</p>
      <p className="text-sm font-medium">{money(value)}{plus ? "+" : ""}</p>
    </div>
  );
}
