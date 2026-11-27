"use client";

import { useQuery } from "@tanstack/react-query";
import {
  BellRing, ChevronDown, ChevronLeft, CircleCheck, Flag, Grid2x2, KeyRound, Map as MapIcon, MessageSquare, Share, SprayCan, Tag, type LucideIcon,
} from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Icon } from "@/components/icon";
import { useAuthDialog, useConfig, useMe, usePayOptions } from "@/components/providers";
import { GuestPicker, guestsLabel, type Guests } from "@/components/site/guest-picker";
import { SiteHeader } from "@/components/site/header";
import { Photo, PhotoCarousel, StarIcon, WishlistHeart, typeLabel } from "@/components/site/listing-card";
import { useMoney } from "@/components/site/locale";
import { RangeCalendar, type Range } from "@/components/site/range-calendar";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Icon3D, type Icon3DName } from "@/components/ui/icon3d";
import { Avatar, Skeleton } from "@/components/ui/misc";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/overlays";
import { ApiError, get, post } from "@/lib/api";
import { approx, fmtDate, fmtRange, fmtShort, freeCancelUntil, hhmm, kes, nightsBetween } from "@/lib/format";
import type { CalendarData, ListingDetail, Quote, Review, WaitlistEntry } from "@/lib/types";
import { cn, flag } from "@/lib/utils";

const LocationMap = dynamic(() => import("@/components/site/maps").then((m) => m.LocationMap), {
  ssr: false,
  loading: () => <div className="h-[480px] animate-pulse rounded-card bg-surface" />,
});

const CATEGORIES: { key: string; label: string; icon: LucideIcon }[] = [
  { key: "cleanliness", label: "Cleanliness", icon: SprayCan },
  { key: "accuracy", label: "Accuracy", icon: CircleCheck },
  { key: "check_in", label: "Check-in", icon: KeyRound },
  { key: "communication", label: "Communication", icon: MessageSquare },
  { key: "location", label: "Location", icon: MapIcon },
  { key: "value", label: "Value", icon: Tag },
];

const ROOM_LABEL: Record<string, string> = {
  view: "The view", living: "Living room", bedroom: "Bedrooms", kitchen: "Full kitchen", bathroom: "Bathroom", pool: "Pool", exterior: "Exterior",
  garden: "Garden", balcony: "Balcony", dining: "Dining area", workspace: "Workspace",
};

// Highlight icons (lucide names in the data) → 3D art, as Airbnb's listing highlights now use.
const HIGHLIGHT_ICON: Record<string, Icon3DName> = {
  sunrise: "sunrise", sunset: "sunset", waves: "wave", umbrella: "beach", "battery-charging": "light-bulb", croissant: "croissant",
  "key-round": "key", baby: "baby-bottle", "shield-check": "shield", laptop: "wifi", "map-pin": "pushpin", sailboat: "sailboat",
  utensils: "kitchen", landmark: "classical-building", "building-2": "homes", coffee: "hot-beverage", wifi: "wifi",
};

// Essentials guests look for; any this home lacks are listed struck through, as on the big platforms.
const ESSENTIALS: [string, string][] = [["wifi", "Wi-Fi"], ["kitchen", "Kitchen"], ["washer", "Washer"], ["ac", "Air conditioning"], ["tv", "TV"], ["smoke_alarm", "Smoke alarm"], ["first_aid", "First-aid kit"]];

// "Guests mention": themes counted across reviews in the languages our guests write in.
const THEMES: { label: string; icon: Icon3DName; words: string[] }[] = [
  { label: "Hospitality", icon: "party-popper", words: ["amina", "host", "welcom", "ospital", "gastfreund", "accueil", "karibu", "helpful"] },
  { label: "Cleanliness", icon: "sparkles", words: ["clean", "pulit", "sauber", "propre", "safi", "spotless"] },
  { label: "Breakfast", icon: "croissant", words: ["breakfast", "colazion", "frühstück", "fruhstuck", "petit", "chai", "mahamri"] },
  { label: "Beach", icon: "beach", words: ["beach", "spiaggia", "strand", "plage", "ufuo", "sea", "ocean"] },
  { label: "Peace & quiet", icon: "palm-tree", words: ["quiet", "tranquill", "ruhig", "calme", "peace", "utulivu"] },
  { label: "Views", icon: "sunset", words: ["view", "vista", "aussicht", "vue", "sunset", "sunrise"] },
  { label: "Pool", icon: "wave", words: ["pool", "piscin", "swim"] },
  { label: "Location", icon: "pushpin", words: ["location", "posizione", "lage", "emplacement", "walk", "close to"] },
  { label: "Safety", icon: "shield", words: ["safe", "secur", "sicher", "sicur", "guard"] },
];

const regionName = (code: string) => {
  try {
    return new Intl.DisplayNames(["en"], { type: "region" }).of(code.toUpperCase()) ?? code;
  } catch {
    return code;
  }
};

export function ListingView({ slug }: { slug: string }) {
  const params = useSearchParams();
  const router = useRouter();
  const money = useMoney();
  const { data: l, isLoading, error } = useQuery({ queryKey: ["listing", slug], queryFn: () => get<ListingDetail>(`/api/listings/${slug}`) });
  const { data: cal } = useQuery({ queryKey: ["calendar", slug], queryFn: () => get<CalendarData>(`/api/listings/${slug}/calendar`) });
  const { data: reviews } = useQuery({ queryKey: ["reviews", slug], queryFn: () => get<Review[]>(`/api/listings/${slug}/reviews`) });
  const [range, setRange] = React.useState<Range>({ from: params.get("check_in") || undefined, to: params.get("check_out") || undefined });
  const [guests, setGuests] = React.useState<Guests>({
    adults: Number(params.get("adults") || 0) || 1,
    children: Number(params.get("children") || 0),
    infants: Number(params.get("infants") || 0),
  });
  const unavailable = React.useMemo(() => new Set(cal?.unavailable ?? []), [cal]);

  const galleryRef = React.useRef<HTMLDivElement>(null);
  const columnsEndRef = React.useRef<HTMLDivElement>(null);
  const [nav, setNav] = React.useState({ show: false, cta: false });
  React.useEffect(() => {
    if (!l) return;
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        const past = !e.isIntersecting && e.boundingClientRect.top < 0;
        if (e.target === galleryRef.current) setNav((n) => ({ ...n, show: past }));
        if (e.target === columnsEndRef.current) setNav((n) => ({ ...n, cta: past }));
      });
    });
    if (galleryRef.current) io.observe(galleryRef.current);
    if (columnsEndRef.current) io.observe(columnsEndRef.current);
    return () => io.disconnect();
  }, [l]);

  if (error) {
    return (
      <>
        <SiteHeader width="narrow" />
        <main className="container-narrow py-24 text-center">
          <h1 className="text-2xl font-semibold">We couldn&apos;t find that home</h1>
          <p className="mt-2 text-ink-2">{(error as Error).message}</p>
          <Button asChild className="mt-6"><Link href="/s">Browse all homes</Link></Button>
        </main>
      </>
    );
  }
  if (isLoading || !l) return <ListingSkeleton />;

  const card: CardProps = { listing: l, range, setRange, guests, setGuests, unavailable, prices: cal?.prices, cal };
  const share = async () => {
    const url = window.location.href;
    if (navigator.share) await navigator.share({ title: l.name, url }).catch(() => {});
    else {
      await navigator.clipboard.writeText(url);
      toast.success("Link copied");
    }
  };
  const overview = `${l.property_type === "room" ? "Room" : `Entire ${l.property_type}`} in ${l.area.name}, Kenya`;
  const facts = `${l.max_guests} guests · ${l.bedrooms} bedroom${l.bedrooms !== 1 ? "s" : ""} · ${l.beds} bed${l.beds !== 1 ? "s" : ""} · ${l.bathrooms} bath${l.bathrooms !== 1 ? "s" : ""}`;

  return (
    <>
      <SiteHeader width="narrow" />
      <SectionNav listing={l} show={nav.show} cta={nav.cta} card={card} />

      {/* phones: full-bleed carousel with floating actions */}
      <div className="relative md:hidden">
        <PhotoTour listing={l}>
          <div
            role="button"
            tabIndex={0}
            aria-label="Show all photos"
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                e.currentTarget.click();
              }
            }}
            className="block w-full cursor-pointer"
          >
            <PhotoCarousel photos={l.photos.map((p) => p.src)} alt={l.name} priority className="aspect-[20/19]" sizes="100vw" dotsClassName="bottom-9" counter />
          </div>
        </PhotoTour>
        <div className="pointer-events-none absolute inset-x-0 top-0 flex items-center justify-between p-4">
          <button type="button" onClick={() => (history.length > 1 ? router.back() : router.push("/s"))} aria-label="Back" className="pointer-events-auto grid size-10 place-items-center rounded-full bg-white shadow-badge">
            <ChevronLeft className="size-4" strokeWidth={2.6} />
          </button>
          <div className="pointer-events-auto flex gap-3">
            <button type="button" onClick={share} aria-label="Share" className="grid size-10 place-items-center rounded-full bg-white shadow-badge">
              <Share className="size-4" />
            </button>
            <span className="grid size-10 place-items-center rounded-full bg-white shadow-badge">
              <WishlistHeart slug={l.slug} saved={l.wishlisted} className="[&_path:not(.fill-brand-500)]:fill-transparent [&_path]:stroke-ink [&_svg]:size-[18px]" />
            </span>
          </div>
        </div>
      </div>

      <main className="container-narrow relative z-10 -mt-6 rounded-t-[24px] bg-white pb-28 md:mt-0 md:rounded-none lg:pb-0">
        <div className="flex items-end justify-between gap-3 pt-7 max-md:flex-col max-md:items-center max-md:text-center md:pt-6">
          <h1 className="text-[26px] leading-[30px] font-semibold tracking-tight">{l.name}</h1>
          <div className="hidden items-center gap-1 md:flex">
            <Button variant="ghost" size="sm" className="font-semibold underline" onClick={share}>
              <Share className="size-4" /> Share
            </Button>
            <span className="flex h-8 items-center rounded-lg pr-2 text-sm font-semibold underline hover:bg-chip">
              <WishlistHeart slug={l.slug} saved={l.wishlisted} className="[&_path:not(.fill-brand-500)]:fill-transparent [&_path]:stroke-ink [&_svg]:size-4" /> Save
            </span>
          </div>
        </div>

        <div ref={galleryRef} id="photos" className="scroll-mt-24">
          <Gallery listing={l} />
        </div>

        <div className="grid gap-x-24 lg:grid-cols-[minmax(0,1fr)_372px]">
          <div className="min-w-0">
            <section className="pt-6 pb-8 max-md:text-center md:pt-8">
              <h2 className="text-[22px] leading-[26px] font-medium">{overview}</h2>
              <p className="mt-1 text-base">{facts}</p>
              {!l.guest_favourite && l.rating && (
                <a href="#reviews" className="mt-2 inline-flex items-center gap-1.5 text-base font-semibold">
                  <StarIcon className="size-3.5" /> {l.rating.toFixed(2)} · <span className="underline">{l.reviews_count} reviews</span>
                </a>
              )}
              {l.guest_favourite && <FavouriteBox rating={l.rating ?? 0} count={l.reviews_count} />}
            </section>

            <Section>
              <div className="flex items-center gap-5">
                <Avatar name={`${l.host.name} Mohamed`} size={40} className="bg-ink!" />
                <div>
                  <p className="font-medium">Hosted by {l.host.name}</p>
                  <p className="text-sm text-ink-2">{l.host.superhost ? "Superhost · " : ""}{2026 - l.host.since} years hosting</p>
                </div>
              </div>
            </Section>

            <Section>
              <div className="space-y-6">
                {l.highlights.map((h) => (
                  <div key={h.title} className="flex items-center gap-5">
                    <Icon3D name={HIGHLIGHT_ICON[h.icon] ?? "sparkles"} size={40} />
                    <div>
                      <p className="text-sm font-medium">{h.title}</p>
                      <p className="text-sm text-ink-2">{h.text}</p>
                    </div>
                  </div>
                ))}
              </div>
            </Section>

            <Section>
              <About listing={l} />
            </Section>

            {!!l.sleeping.length && (
              <Section title="Where you'll sleep">
                <div className="grid grid-cols-2 gap-4">
                  {l.sleeping.map((s, i) => {
                    const photo = l.photos.filter((p) => p.room === "bedroom")[i];
                    return (
                      <div key={s.room}>
                        <div className="aspect-[3/2] overflow-hidden rounded-lg bg-surface">
                          {photo && <Photo src={photo.src} alt={s.room} className="size-full" sizes="240px" />}
                        </div>
                        <p className="mt-3 font-medium">{s.room}</p>
                        <p className="text-sm text-ink-2">{s.beds}</p>
                      </div>
                    );
                  })}
                </div>
              </Section>
            )}

            <Section id="amenities" title="What this place offers">
              <Amenities listing={l} />
            </Section>

            {!!l.addons.length && (
              <Section title="Make it yours" subtitle="Add extras when you book, or later from your trip — on the web, by SMS or USSD.">
                <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
                  {l.addons.slice(0, 8).map((a) => (
                    <div key={a.code} className="flex items-center gap-4">
                      <div className="size-14 shrink-0 overflow-hidden rounded-xl bg-surface">
                        <Photo src={a.photo_url} alt="" className="size-full" sizes="56px" />
                      </div>
                      <div className="min-w-0">
                        <p className="truncate font-medium">{a.name}</p>
                        <p className="text-sm text-ink-2">{a.price ? `${money(a.price)} ${a.pricing_label}` : "Free"}{a.requires_approval ? " · on request" : ""}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            <section id="calendar" className="scroll-mt-28 border-t border-line py-12">
              <h2 className="text-[22px] leading-[26px] font-medium">
                {range.from && range.to ? `${nightsBetween(range.from, range.to)} nights in ${l.area.name}` : range.from ? "Select checkout date" : "Select check-in date"}
              </h2>
              <p className="mt-1 text-sm text-ink-2">
                {range.from && range.to ? fmtRange(range.from, range.to) : `Add your travel dates for exact pricing · minimum stay ${l.min_nights} night${l.min_nights > 1 ? "s" : ""}`}
              </p>
              <div className="mt-6">
                <RangeCalendar value={range} onChange={setRange} unavailable={unavailable} prices={cal?.prices} minNights={l.min_nights} />
              </div>
              <div className="mt-4 flex justify-end">
                <button type="button" className="text-sm font-semibold underline underline-offset-2" onClick={() => setRange({})}>Clear dates</button>
              </div>
            </section>
          </div>

          <aside className="hidden lg:block">
            <div className="sticky top-[112px] pt-8 pb-12">
              <TipCard cal={cal} />
              <BookingCard {...card} />
              <UssdNote />
            </div>
          </aside>
        </div>
        <div ref={columnsEndRef} />

        <Divider />
        <Reviews listing={l} reviews={reviews ?? []} />
        <Divider />

        <section id="location" className="scroll-mt-24 py-12">
          <h2 className="text-[22px] leading-[26px] font-medium">Where you&apos;ll be</h2>
          <p className="mt-6 mb-6 text-base">{l.area.name}, Mombasa, Kenya</p>
          {l.location && <LocationMap lat={l.location.lat} lng={l.location.lng} />}
          <p className="mt-6 text-base font-medium">{l.area_info.name}, Mombasa, Kenya</p>
          <p className="mt-2 line-clamp-3 text-base text-ink">{l.area_info.description}</p>
          <p className="mt-4 text-sm text-ink-2"><b className="font-medium text-ink">Getting there · </b>{l.area_info.getting_there}</p>
          <p className="mt-4 text-sm text-ink-2">Exact location is shared once you&apos;ve booked.</p>
        </section>
        <Divider />

        <MeetHost listing={l} />
        <Divider />

        <ThingsToKnow listing={l} />
      </main>

      <MobileReserveBar {...card} />
    </>
  );
}

function Section({ id, title, subtitle, children }: { id?: string; title?: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section id={id} className={cn("scroll-mt-24 border-t border-line", title ? "py-12" : "py-8")}>
      {title && <h2 className="text-[22px] leading-[26px] font-medium">{title}</h2>}
      {subtitle && <p className="mt-1 text-sm text-ink-2">{subtitle}</p>}
      <div className={cn(title && "mt-6")}>{children}</div>
    </section>
  );
}

const Divider = () => <hr className="border-line" />;

/** Laurel branch for the "Guest favourite" marks (mirrored for the right side). */
function Laurel({ className, flip }: { className?: string; flip?: boolean }) {
  return (
    <svg viewBox="0 0 26 64" className={cn("h-9 w-auto", flip && "-scale-x-100", className)} fill="currentColor" aria-hidden>
      <path d="M21 63C10 53 6.5 38 8.5 22 9.6 13 13 6 18 1" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
      <ellipse cx="7.5" cy="47" rx="2.7" ry="6.4" transform="rotate(-42 7.5 47)" />
      <ellipse cx="4.6" cy="34" rx="2.7" ry="6.4" transform="rotate(-24 4.6 34)" />
      <ellipse cx="4.4" cy="21" rx="2.7" ry="6.4" transform="rotate(-6 4.4 21)" />
      <ellipse cx="8.4" cy="9" rx="2.6" ry="6" transform="rotate(16 8.4 9)" />
      <ellipse cx="19.5" cy="52" rx="2.6" ry="6" transform="rotate(42 19.5 52)" />
      <ellipse cx="15" cy="39" rx="2.6" ry="6" transform="rotate(30 15 39)" />
      <ellipse cx="14.2" cy="26" rx="2.6" ry="6" transform="rotate(24 14.2 26)" />
      <ellipse cx="16.8" cy="13.5" rx="2.4" ry="5.6" transform="rotate(32 16.8 13.5)" />
    </svg>
  );
}

function FavouriteBox({ rating, count }: { rating: number; count: number }) {
  return (
    <a href="#reviews" className="mt-6 flex items-center rounded-xl border border-line px-6 py-5 text-left transition-shadow hover:shadow-soft">
      <div className="flex items-center gap-0.5">
        <Laurel />
        <span className="text-center text-lg leading-5 font-medium">Guest<br />favourite</span>
        <Laurel flip />
      </div>
      <p className="hidden flex-1 px-6 text-base font-medium md:block">One of the most loved homes on Amina Stays, according to guests</p>
      <div className="ml-auto flex items-center">
        <div className="px-5 text-center">
          <p className="text-[22px] leading-[26px] font-medium">{rating.toFixed(2)}</p>
          <span className="flex gap-px"><StarIcon className="size-2.5" /><StarIcon className="size-2.5" /><StarIcon className="size-2.5" /><StarIcon className="size-2.5" /><StarIcon className="size-2.5" /></span>
        </div>
        <span className="h-10 w-px bg-line" />
        <div className="pl-5 text-center">
          <p className="text-[22px] leading-[26px] font-medium">{count}</p>
          <p className="text-xs font-medium underline">Reviews</p>
        </div>
      </div>
    </a>
  );
}

function SectionNav({ listing: l, show, cta, card }: { listing: ListingDetail; show: boolean; cta: boolean; card: CardProps }) {
  const { data: q } = useQuote(card.listing.slug, card.range, card.guests);
  const money = useMoney();
  const links: [string, string][] = [["#photos", "Photos"], ["#amenities", "Amenities"], ["#reviews", "Reviews"], ["#location", "Location"]];
  return (
    <div className={cn("fixed inset-x-0 top-0 z-50 hidden border-b border-line bg-white transition-transform duration-200 md:block", show ? "translate-y-0" : "-translate-y-full")} aria-hidden={!show}>
      <div className="container-narrow flex h-20 items-center justify-between">
        <nav className="flex h-full gap-6">
          {links.map(([href, label]) => (
            <a key={href} href={href} tabIndex={show ? 0 : -1} className="flex h-full items-center border-b-4 border-transparent pt-1 text-sm font-medium hover:border-ink">{label}</a>
          ))}
        </nav>
        {cta && (
          <div className="flex items-center gap-6 animate-fade-in">
            <div className="text-right">
              <p className="text-base">
                {q ? <><b className="font-semibold underline">{money(q.total)}</b> for {q.nights} nights</> : <><b className="font-semibold">{money(l.price.from_nightly)}</b> a night</>}
              </p>
              {l.rating && <p className="flex items-center justify-end gap-1 text-xs"><StarIcon className="size-2.5" /> {l.rating.toFixed(2)} · <span className="text-ink-2 underline">{l.reviews_count} reviews</span></p>}
            </div>
            <ReserveButton {...card} className="h-12 w-40" />
          </div>
        )}
      </div>
    </div>
  );
}

function Gallery({ listing: l }: { listing: ListingDetail }) {
  const photos = l.photos;
  return (
    <PhotoTour listing={l}>
      <div className="relative mt-6 hidden h-[clamp(320px,34vw,460px)] grid-cols-4 grid-rows-2 gap-2 overflow-hidden rounded-xl md:grid">
        {photos.slice(0, 5).map((p, i) => (
          <button key={i} type="button" className={cn("group relative overflow-hidden bg-surface", i === 0 && "col-span-2 row-span-2")} aria-label={`Open photo ${i + 1}`}>
            <Photo src={p.src} alt={p.caption || l.name} className="size-full transition-[filter] duration-300 group-hover:brightness-[0.85]" sizes={i === 0 ? "50vw" : "25vw"} priority={i === 0} />
          </button>
        ))}
        <span className="absolute right-6 bottom-6 flex h-8 items-center gap-2 rounded-lg border border-ink bg-white px-3 text-xs font-medium">
          <Grid2x2 className="size-3.5" /> Show all photos
        </span>
      </div>
    </PhotoTour>
  );
}

/** Airbnb-style photo tour: room thumbnails up top, then every room's photos grouped below. */
function PhotoTour({ listing: l, children }: { listing: ListingDetail; children: React.ReactNode }) {
  const rooms = React.useMemo(() => {
    const out: { room: string; photos: ListingDetail["photos"] }[] = [];
    l.photos.forEach((p) => {
      const g = out.find((x) => x.room === p.room);
      if (g) g.photos.push(p);
      else out.push({ room: p.room, photos: [p] });
    });
    return out;
  }, [l.photos]);
  return (
    <Dialog>
      <DialogTrigger asChild>{children}</DialogTrigger>
      <DialogContent title="Photo tour" size="full" className="sm:h-[94dvh]">
        <div className="mx-auto max-w-4xl px-5 py-8 sm:px-10">
          <h2 className="text-[26px] font-semibold">Photo tour</h2>
          <div className="mt-6 grid grid-cols-3 gap-4 sm:grid-cols-5">
            {rooms.map((r) => (
              <a key={r.room} href={`#tour-${r.room}`} className="group">
                <div className="aspect-[4/3] overflow-hidden rounded-lg bg-surface">
                  <Photo src={r.photos[0].src} alt="" className="size-full transition-transform group-hover:scale-105" sizes="160px" />
                </div>
                <p className="mt-2 text-sm font-medium">{ROOM_LABEL[r.room] ?? typeLabel(r.room)}</p>
              </a>
            ))}
          </div>
          {rooms.map((r) => (
            <section key={r.room} id={`tour-${r.room}`} className="mt-14 grid scroll-mt-4 gap-6 md:grid-cols-[220px_1fr]">
              <h3 className="text-[22px] font-medium">{ROOM_LABEL[r.room] ?? typeLabel(r.room)}</h3>
              <div className="grid grid-cols-2 gap-2">
                {r.photos.map((p, i) => (
                  <figure key={i} className={cn(i % 3 === 0 && "col-span-2")}>
                    <Photo src={p.src} alt={p.caption || l.name} className="aspect-[4/3] w-full rounded-lg" sizes="(min-width: 768px) 600px, 100vw" />
                    {p.caption && <figcaption className="mt-1.5 text-sm text-ink-2">{p.caption}</figcaption>}
                  </figure>
                ))}
              </div>
            </section>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function About({ listing: l }: { listing: ListingDetail }) {
  return (
    <div>
      <p className="line-clamp-6 text-base leading-6 whitespace-pre-line">{l.description}</p>
      <Dialog>
        <DialogTrigger asChild>
          <Button variant="soft" size="lg" className="mt-6">Show more</Button>
        </DialogTrigger>
        <DialogContent title="About this place" size="lg">
          <div className="space-y-8 p-6 text-base leading-relaxed sm:p-8">
            <p className="whitespace-pre-line">{l.description}</p>
            {l.the_space && <div><h3 className="mb-2 text-lg font-semibold">The space</h3><p>{l.the_space}</p></div>}
            {l.guest_access && <div><h3 className="mb-2 text-lg font-semibold">Guest access</h3><p>{l.guest_access}</p></div>}
            {l.neighbourhood && <div><h3 className="mb-2 text-lg font-semibold">The neighbourhood</h3><p>{l.neighbourhood}</p></div>}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Amenities({ listing: l }: { listing: ListingDetail }) {
  const have = new Set(l.amenities.map((a) => a.code));
  const missing = ESSENTIALS.filter(([code]) => !have.has(code)).slice(0, 2);
  const groups = l.amenities.reduce<Record<string, typeof l.amenities>>((acc, a) => {
    (acc[a.category] ||= []).push(a);
    return acc;
  }, {});
  return (
    <div>
      <div className="grid gap-x-8 gap-y-6 sm:grid-cols-2">
        {l.amenities.slice(0, 10 - missing.length).map((a) => (
          <div key={a.code} className="flex items-center gap-4 text-base">
            <Icon name={a.icon} className="size-6 shrink-0" /> {a.name}
          </div>
        ))}
        {missing.map(([code, label]) => (
          <div key={code} className="flex items-center gap-4 text-base">
            <Icon name="check" className="size-6 shrink-0 opacity-0" /> <span className="line-through"><span className="sr-only">Unavailable: </span>{label}</span>
          </div>
        ))}
      </div>
      <Dialog>
        <DialogTrigger asChild>
          <Button variant="soft" size="lg" className="mt-10">Show all {l.amenities.length} amenities</Button>
        </DialogTrigger>
        <DialogContent title="What this place offers" size="md">
          <div className="space-y-8 p-6">
            {Object.entries(groups).map(([cat, items]) => (
              <div key={cat}>
                <h3 className="mb-2 text-lg font-semibold capitalize">{cat.replace("_", " ")}</h3>
                {items.map((a) => (
                  <div key={a.code} className="flex items-center gap-4 border-b border-line-soft py-5 text-base">
                    <Icon name={a.icon} className="size-6" /> {a.name}
                  </div>
                ))}
              </div>
            ))}
            {!!missing.length && (
              <div>
                <h3 className="mb-2 text-lg font-semibold">Not included</h3>
                {missing.map(([code, label]) => (
                  <div key={code} className="border-b border-line-soft py-5 text-base line-through">{label}</div>
                ))}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function useQuote(slug: string, range: Range, guests: Guests) {
  const ready = !!(range.from && range.to);
  return useQuery({
    queryKey: ["quote", slug, range.from, range.to, guests.adults, guests.children],
    queryFn: () => post<Quote>(`/api/listings/${slug}/quote`, { check_in: range.from, check_out: range.to, adults: guests.adults, children: guests.children }),
    enabled: ready,
  });
}

type CardProps = {
  listing: ListingDetail; range: Range; setRange: (r: Range) => void; guests: Guests; setGuests: (g: Guests) => void;
  unavailable: Set<string>; prices?: Record<string, number>; cal?: CalendarData;
};

function useReserve({ listing: l, range, guests }: CardProps) {
  const router = useRouter();
  return () => {
    const s = new URLSearchParams({ check_in: range.from!, check_out: range.to!, adults: String(guests.adults) });
    if (guests.children) s.set("children", String(guests.children));
    if (guests.infants) s.set("infants", String(guests.infants));
    router.push(`/book/${l.slug}?${s}`);
  };
}

function ReserveButton(props: CardProps & { className?: string; onNeedDates?: () => void }) {
  const { data: q, isFetching } = useQuote(props.listing.slug, props.range, props.guests);
  const ready = !!(props.range.from && props.range.to);
  const taken = ready && q?.available === false;
  const reserve = useReserve(props);
  return (
    <Button
      variant="brand"
      size="lg"
      className={props.className}
      loading={isFetching && ready}
      onClick={() => {
        if (ready && !taken) reserve();
        else if (props.onNeedDates) props.onNeedDates();
        else document.getElementById("calendar")?.scrollIntoView({ behavior: "smooth" });
      }}
    >
      {taken ? "Change dates" : ready ? "Reserve" : "Check availability"}
    </Button>
  );
}

/** Dates taken: join the waitlist; we text the guest (with a booking link) the moment the dates free up. */
function NotifyMe({ listing: l, range, guests }: Pick<CardProps, "listing" | "range" | "guests">) {
  const { data: me } = useMe();
  const { requireLogin } = useAuthDialog();
  const [joined, setJoined] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const key = `${range.from}|${range.to}`;
  const join = async () => {
    setBusy(true);
    try {
      await post<WaitlistEntry>("/api/waitlist", { slug: l.slug, check_in: range.from, check_out: range.to, adults: guests.adults, children: guests.children });
      setJoined(key);
      toast.success("You're on the waitlist — we'll text you the moment these dates open up.");
    } catch (e) {
      const err = e as ApiError;
      if ((err.data as { code?: string } | undefined)?.code === "available") toast.success(err.message);
      else toast.error(err.message);
    } finally {
      setBusy(false);
    }
  };
  if (joined === key) {
    return (
      <p className="mt-3 flex items-center justify-center gap-2 text-sm">
        <CircleCheck className="size-4 text-success" /> You&apos;re on the waitlist — we&apos;ll text you
      </p>
    );
  }
  return (
    <Button variant="soft" size="lg" className="mt-3 h-12 w-full" loading={busy} onClick={() => (me?.authenticated ? join() : requireLogin("Log in to join the waitlist", join))}>
      <BellRing className="size-4" /> Notify me if these dates open up
    </Button>
  );
}

/** The tip card above the booking card: "Rare find!" when the next months are mostly booked, else the all-in price promise. */
function TipCard({ cal }: { cal?: CalendarData }) {
  const booked = cal ? cal.unavailable.filter((d) => d < (cal.end ?? "9999")).length : 0;
  const span = cal ? nightsBetween(cal.start, cal.end) || 120 : 120;
  const rare = !!cal && booked / span >= 0.45;
  return (
    <div className="mb-6 flex items-center gap-4 rounded-xl border border-line px-5 py-3.5">
      <p className="flex-1 text-sm">{rare ? <><b className="font-medium">Rare find!</b> This place is usually booked</> : <b className="font-medium">Prices include all fees</b>}</p>
      <Icon3D name={rare ? "glowing-star" : "label"} size={28} />
    </div>
  );
}

/** "Price details": the itemised breakdown behind the underlined total, as on Airbnb. */
function PriceDetails({ q, depositPercent, children }: { q: Quote; depositPercent: number; children: React.ReactNode }) {
  const { data: config } = useConfig();
  return (
    <Popover>
      <PopoverTrigger asChild>{children}</PopoverTrigger>
      <PopoverContent align="start" sideOffset={12} className="w-[360px] rounded-3xl border-0 bg-white/95 p-6 shadow-[0_0_0_1px_rgb(0_0_0/0.02),0_4px_8px_rgb(0_0_0/0.08),0_12px_30px_rgb(0_0_0/0.18)] backdrop-blur-md">
        <p className="text-base font-semibold">Price details</p>
        <div className="mt-4 space-y-3 text-sm">
          {q.lines.map((line) => (
            <div key={line.label} className={cn("flex justify-between gap-4", line.amount < 0 && "text-success")}>
              <span>{line.label}</span>
              <span className="shrink-0">{line.amount < 0 ? `−${kes(-line.amount)}` : kes(line.amount)}</span>
            </div>
          ))}
          <div className="flex justify-between gap-4 border-t border-line pt-3 font-semibold">
            <span>Total</span>
            <span>{kes(q.total)}</span>
          </div>
        </div>
        <p className="mt-3 text-xs text-ink-2">
          {q.deposit_available ? `Pay ${kes(q.deposit)} today (${depositPercent}%) and the rest before you arrive — no extra fees.` : "No extra fees — cleaning and the 2% tourism levy are included."}
        </p>
        {config && <p className="mt-1 text-xs text-ink-2">{approx(q.total, config.currencies, "USD")} · {approx(q.total, config.currencies, "EUR")} · {approx(q.total, config.currencies, "GBP")}</p>}
      </PopoverContent>
    </Popover>
  );
}

function BookingCard(props: CardProps & { flat?: boolean }) {
  const { listing: l, range, setRange, guests, setGuests, unavailable, prices, flat } = props;
  const { data: q } = useQuote(l.slug, range, guests);
  const money = useMoney();
  const { mpesa } = usePayOptions();
  const [datesOpen, setDatesOpen] = React.useState(false);
  const ready = !!(range.from && range.to);
  const freeUntil = freeCancelUntil(l.cancellation.policy, range.from);
  return (
    <div className={cn("bg-white", !flat && "rounded-xl border border-black/5 p-6 shadow-card")}>
      {q ? (
        <p className="text-[22px] leading-[26px]">
          <PriceDetails q={q} depositPercent={l.deposit_percent}>
            <button type="button" className="font-medium underline decoration-1 underline-offset-4" aria-label="Show price breakdown">{money(q.total)}</button>
          </PriceDetails>{" "}
          <span className="text-base">for {q.nights} night{q.nights !== 1 ? "s" : ""}</span>
        </p>
      ) : (
        <p className="text-[22px] leading-[26px] font-medium">Add dates for prices</p>
      )}
      <div className="mt-6 rounded-xl border border-ink-3">
        <Popover open={datesOpen} onOpenChange={setDatesOpen}>
          <PopoverTrigger asChild>
            <button type="button" className="grid w-full grid-cols-2 text-left">
              <span className="border-r border-ink-3 px-3 py-2.5">
                <span className="block text-[10px] leading-3 font-bold uppercase">Check-in</span>
                <span className={cn("mt-1 block text-sm", !range.from && "text-ink-2")}>{range.from ? fmtShort(range.from) : "Add date"}</span>
              </span>
              <span className="px-3 py-2.5">
                <span className="block text-[10px] leading-3 font-bold uppercase">Checkout</span>
                <span className={cn("mt-1 block text-sm", !range.to && "text-ink-2")}>{range.to ? fmtShort(range.to) : "Add date"}</span>
              </span>
            </button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-[min(720px,95vw)] rounded-[32px] border-0 p-8 shadow-pop">
            <RangeCalendar value={range} onChange={(r) => { setRange(r); if (r.from && r.to) setDatesOpen(false); }} unavailable={unavailable} prices={prices} minNights={l.min_nights} />
            <div className="mt-5 flex items-center justify-end gap-3">
              <Button variant="soft" size="sm" onClick={() => setRange({})}>Clear dates</Button>
              <Button size="sm" onClick={() => setDatesOpen(false)}>Close</Button>
            </div>
          </PopoverContent>
        </Popover>
        <Popover>
          <PopoverTrigger asChild>
            <button type="button" className="flex w-full items-center justify-between border-t border-ink-3 px-3 py-2.5 text-left">
              <span>
                <span className="block text-[10px] leading-3 font-bold uppercase">Guests</span>
                <span className="mt-1 block text-sm">{guestsLabel(guests)}</span>
              </span>
              <ChevronDown className="size-4" />
            </button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-[340px] rounded-xl border-0 px-6 py-2 shadow-pop">
            <GuestPicker value={guests} onChange={setGuests} max={l.max_guests} />
            <p className="pb-3 text-xs text-ink-2">This place has a maximum of {l.max_guests} guests, not including infants.</p>
          </PopoverContent>
        </Popover>
      </div>
      {ready && q && q.available !== false && (q.deposit_available || freeUntil) && (
        <p className="mt-4 rounded-lg bg-chip px-3 py-2 text-xs">
          {q.deposit_available && <>{money(q.deposit)} today</>}
          {q.deposit_available && freeUntil && " · "}
          {freeUntil && <>Free cancellation before <b className="font-medium">{fmtDate(freeUntil, "d MMMM")}</b></>}
        </p>
      )}
      <ReserveButton {...props} className="mt-4 h-12 w-full text-base" onNeedDates={() => setDatesOpen(true)} />
      {ready && q?.available === false && <NotifyMe listing={l} range={range} guests={guests} />}
      {q?.problems?.length ? (
        <p className="mt-3 text-center text-sm text-danger">{q.problems[0]}</p>
      ) : (
        <p className="mt-3 text-center text-sm text-ink-2">{ready ? "You won't be charged yet" : `${mpesa ? "M-Pesa or card" : "Pay by card"} · ${l.deposit_percent}% deposit option`}</p>
      )}
    </div>
  );
}

function UssdNote() {
  const { data: config } = useConfig();
  return (
    <div className="mt-6 flex items-center justify-center gap-2 text-sm text-ink-2">
      {config?.channels.ussd_code ? (
        <>
          <Icon3D name="mobile-phone" size={20} /> No data? Dial <b className="font-semibold text-ink">{config.channels.ussd_code}</b> to book
        </>
      ) : (
        <>
          <Flag className="size-4" /> <Link href="/help" className="underline">Report this listing</Link>
        </>
      )}
    </div>
  );
}

function MobileReserveBar(props: CardProps) {
  const { listing: l, range } = props;
  const { data: q } = useQuote(l.slug, range, props.guests);
  const money = useMoney();
  const [open, setOpen] = React.useState(false);
  return (
    <div className="fixed inset-x-0 bottom-0 z-40 flex items-center justify-between gap-4 border-t border-line bg-white px-6 py-4 pb-[max(16px,env(safe-area-inset-bottom))] max-[379px]:gap-3 max-[379px]:px-4 lg:hidden">
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogTrigger asChild>
          <button type="button" className="min-w-0 text-left">
            {q ? (
              <>
                <p className="text-base max-[379px]:text-[15px]"><b className="font-semibold underline">{money(q.total)}</b> for {q.nights} nights</p>
                <p className="text-sm font-medium underline max-[379px]:text-[13px]">{fmtRange(range.from, range.to)}</p>
              </>
            ) : (
              <>
                <p className="text-base max-[379px]:text-[15px]"><b className="font-semibold">{money(l.price.from_nightly)}</b> night</p>
                <p className="flex items-center gap-1 text-sm font-medium whitespace-nowrap max-[379px]:text-[13px]"><span className="underline">Add dates</span>{l.rating && <> · <StarIcon className="size-2.5" /> {l.rating.toFixed(2)}</>}</p>
              </>
            )}
          </button>
        </DialogTrigger>
        <DialogContent title="Your stay" size="md">
          <div className="p-5">
            <BookingCard {...props} flat />
          </div>
        </DialogContent>
      </Dialog>
      <ReserveButton {...props} className="h-12 shrink-0 px-7 text-base max-[379px]:px-4 max-[379px]:text-sm" onNeedDates={() => setOpen(true)} />
    </div>
  );
}

function Reviews({ listing: l, reviews }: { listing: ListingDetail; reviews: Review[] }) {
  const cats = l.reviews_summary.categories;
  const dist = [5, 4, 3, 2, 1].map((n) => reviews.filter((r) => Math.round(r.rating) === n).length);
  const mentions = THEMES.map((t) => ({ ...t, count: reviews.filter((r) => t.words.some((w) => r.comment.toLowerCase().includes(w))).length }))
    .filter((t) => t.count >= 2)
    .sort((a, b) => b.count - a.count)
    .slice(0, 6);
  if (!l.reviews_count) {
    return (
      <section id="reviews" className="scroll-mt-24 py-12">
        <h2 className="flex items-center gap-2 text-[22px] font-medium"><StarIcon className="size-4" /> No reviews (yet)</h2>
        <p className="mt-2 text-ink-2">Be one of the first guests — reviews come only from completed stays.</p>
      </section>
    );
  }
  return (
    <section id="reviews" className="scroll-mt-24 py-12">
      {l.guest_favourite ? (
        <div className="flex flex-col items-center text-center">
          <div className="flex items-center gap-1">
            <Laurel className="h-[92px]" />
            <span className="text-[72px] leading-none font-semibold tracking-tight md:text-[88px]">{l.rating?.toFixed(2)}</span>
            <Laurel className="h-[92px]" flip />
          </div>
          <p className="mt-3 text-[22px] font-semibold">Guest favourite</p>
          <p className="mt-1 max-w-sm text-base text-ink-2">One of the most loved homes on Amina Stays based on ratings, reviews and reliability</p>
        </div>
      ) : (
        <h2 className="flex items-center gap-2 text-[26px] leading-[30px] font-medium">
          <StarIcon className="size-5" /> {l.rating?.toFixed(2)} · {l.reviews_count} reviews
        </h2>
      )}

      <div className="no-scrollbar mt-10 flex gap-0 overflow-x-auto pb-2 xl:grid xl:grid-cols-[1.2fr_repeat(6,1fr)]">
        <div className="min-w-44 shrink-0 pr-6 xl:min-w-0">
          <p className="text-sm font-medium">Overall rating</p>
          <div className="mt-2 space-y-0.5">
            {dist.map((c, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <span className="w-2">{5 - i}</span>
                <span className="h-1 flex-1 rounded-full bg-line">
                  <span className="block h-1 rounded-full bg-ink" style={{ width: `${reviews.length ? (c / reviews.length) * 100 : 0}%` }} />
                </span>
              </div>
            ))}
          </div>
        </div>
        {CATEGORIES.map((c) => (
          <div key={c.key} className="flex min-w-32 shrink-0 flex-col justify-between border-l border-line px-6 xl:min-w-0">
            <div>
              <p className="text-sm font-medium">{c.label}</p>
              <p className="text-lg font-semibold">{cats[c.key]?.toFixed(1) ?? "—"}</p>
            </div>
            <c.icon className="mt-6 size-8" strokeWidth={1.3} />
          </div>
        ))}
      </div>

      {!!mentions.length && (
        <div className="mt-10">
          <p className="text-lg leading-6 font-semibold">Guests mention</p>
          <div className="mt-4 flex flex-wrap gap-2">
            {mentions.map((m) => (
              <span key={m.label} className="flex h-14 items-center gap-2.5 rounded-2xl border border-line-soft px-4 text-sm font-medium">
                <Icon3D name={m.icon} size={24} /> {m.label} <span className="font-normal text-ink-3">{m.count}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="mt-10 grid gap-x-24 gap-y-10 md:grid-cols-2">
        {reviews.slice(0, 6).map((r) => <ReviewCard key={r.id} review={r} />)}
      </div>
      <div className="mt-10 flex flex-wrap items-center gap-6">
        {reviews.length > 6 && (
          <Dialog>
            <DialogTrigger asChild>
              <Button variant="soft" size="lg">Show all {reviews.length} reviews</Button>
            </DialogTrigger>
            <DialogContent title={`${reviews.length} reviews`} size="lg">
              <div className="space-y-10 p-6 sm:p-8">{reviews.map((r) => <ReviewCard key={r.id} review={r} full />)}</div>
            </DialogContent>
          </Dialog>
        )}
        <p className="text-sm text-ink-2 underline">Only guests who completed a stay can review</p>
      </div>
    </section>
  );
}

function ReviewCard({ review: r, full }: { review: Review; full?: boolean }) {
  return (
    <div>
      <div className="flex items-center gap-3">
        <Avatar name={r.guest} size={48} />
        <div>
          <p className="font-medium">{r.guest}</p>
          <p className="text-sm text-ink-2">{flag(r.country)} {regionName(r.country)}</p>
        </div>
      </div>
      <div className="mt-3 flex items-center gap-1.5 text-sm">
        <span className="flex gap-px">{Array.from({ length: 5 }).map((_, i) => <StarIcon key={i} className={cn("size-2.5", i >= r.rating && "text-line")} />)}</span>
        <span>·</span>
        <span className="font-medium">{new Date(r.date).toLocaleDateString("en-GB", { month: "long", year: "numeric" })}</span>
      </div>
      <p className={cn("mt-1 text-base leading-6", !full && "line-clamp-3")}>{r.comment}</p>
      {r.host_response && (
        <div className="mt-4 border-l-2 border-line pl-4">
          <p className="text-sm font-semibold">Response from Amina</p>
          <p className={cn("text-sm text-ink-2", !full && "line-clamp-2")}>{r.host_response}</p>
        </div>
      )}
    </div>
  );
}

function MeetHost({ listing: l }: { listing: ListingDetail }) {
  const { mpesa } = usePayOptions();
  const years = 2026 - l.host.since;
  return (
    <section className="py-12">
      <h2 className="text-[22px] leading-[26px] font-medium">Meet your host</h2>
      <div className="mt-8 grid gap-10 md:grid-cols-[minmax(0,380px)_1fr] md:gap-16">
        <div className="flex max-w-full items-center gap-6 self-start rounded-3xl bg-white px-6 py-8 shadow-[0_6px_20px_rgb(0_0_0/0.2)] max-[379px]:gap-4 max-[379px]:px-4">
          <div className="flex flex-1 flex-col items-center text-center">
            <div className="relative">
              <Avatar name={`${l.host.name} Mohamed`} size={104} className="bg-ink! text-[40px]!" />
              {l.host.verified && (
                <span className="absolute right-0 bottom-1 grid size-8 place-items-center rounded-full bg-brand-500 text-white ring-2 ring-white">
                  <CircleCheck className="size-4" strokeWidth={2.6} />
                </span>
              )}
            </div>
            <p className="mt-3 text-[28px] leading-8 font-semibold">{l.host.name}</p>
            {l.host.superhost && <p className="mt-1 flex items-center gap-1 text-sm font-medium"><Icon3D name="trophy" size={16} /> Superhost</p>}
          </div>
          <div className="w-24 divide-y divide-line">
            <Stat value={String(l.reviews_count)} label="Reviews" />
            <Stat value={l.rating ? `${l.rating.toFixed(2)}★` : "New"} label="Rating" />
            <Stat value={String(years)} label="Years hosting" />
          </div>
        </div>
        <div>
          {l.host.superhost && (
            <>
              <p className="text-lg font-semibold">{l.host.name} is a Superhost</p>
              <p className="mt-2 text-base text-ink-2">Superhosts are experienced, highly rated hosts who are committed to providing great stays for guests.</p>
            </>
          )}
          <p className="mt-8 text-lg font-semibold">Host details</p>
          <p className="mt-2 text-base">Response rate: 100%</p>
          <p className="text-base">Responds {l.host.response_time}</p>
          <p className="text-base">Speaks {l.host.languages.join(" and ")}</p>
          <Button variant="soft" size="lg" asChild className="mt-6">
            <Link href="/messages">Message host</Link>
          </Button>
          <p className="mt-8 flex max-w-md items-start gap-3 border-t border-line pt-6 text-xs text-ink-2">
            <Icon3D name="shield" size={24} />
            To protect your payment, always pay through Amina Stays — {mpesa ? "by M-Pesa or card on this site, USSD or SMS" : "by card on this site or through the link we text you"}. Amina will never ask you to send money another way.
          </p>
        </div>
      </div>
    </section>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="py-3 first:pt-0 last:pb-0">
      <p className="text-[22px] leading-6 font-semibold">{value}</p>
      <p className="text-[10px] font-semibold">{label}</p>
    </div>
  );
}

function ThingsToKnow({ listing: l }: { listing: ListingDetail }) {
  const blocks: { icon: Icon3DName; title: string; lines: string[]; more: React.ReactNode }[] = [
    {
      icon: "spiral-calendar",
      title: "Cancellation policy",
      lines: [l.cancellation.text, "Review this home's full policy for details."],
      more: <p>{l.cancellation.label}: {l.cancellation.text} If a guest has to leave because of a safety issue at the property, Amina refunds the unused nights in full.</p>,
    },
    {
      icon: "door",
      title: "House rules",
      lines: [`Check-in after ${hhmm(l.checkin_time)}`, `Checkout before ${hhmm(l.checkout_time)}`, `${l.max_guests} guests maximum`],
      more: (
        <ul className="space-y-3">
          <li>Check-in after {hhmm(l.checkin_time)} · checkout before {hhmm(l.checkout_time)}</li>
          <li>{l.access_method}{l.self_checkin ? " — your door code arrives by SMS on arrival morning" : ""}</li>
          {l.house_rules.map((r) => <li key={r}>{r}</li>)}
          <li>Pets {l.pets_allowed ? "allowed" : "not allowed"} · smoking {l.smoking_allowed ? "allowed" : "not allowed"} · events {l.events_allowed ? "allowed" : "not allowed"}</li>
          <li>Quiet hours {l.quiet_hours}</li>
        </ul>
      ),
    },
    {
      icon: "shield",
      title: "Safety & property",
      lines: [...l.safety_features.slice(0, 2), "Text HELP any time — it rings Amina"],
      more: (
        <ul className="space-y-3">
          {l.safety_features.map((s) => <li key={s}>{s}</li>)}
          <li>Text HELP any time, day or night — it rings Amina&apos;s phone and alerts the on-site guard.</li>
          {l.tra_licence && <li>Licensed by the Tourism Regulatory Authority · {l.tra_licence}</li>}
        </ul>
      ),
    },
  ];
  return (
    <section className="py-12">
      <h2 className="text-[22px] leading-[26px] font-medium">Things to know</h2>
      <div className="mt-6 grid gap-10 md:grid-cols-3">
        {blocks.map((b) => (
          <div key={b.title}>
            <Icon3D name={b.icon} size={40} />
            <h3 className="mt-4 font-medium">{b.title}</h3>
            <ul className="mt-2 space-y-1 text-base">
              {b.lines.map((line) => <li key={line}>{line}</li>)}
            </ul>
            <Dialog>
              <DialogTrigger asChild>
                <button type="button" className="mt-3 text-base font-semibold underline underline-offset-2">Show more</button>
              </DialogTrigger>
              <DialogContent title={b.title} size="md">
                <div className="p-6 text-base leading-relaxed">{b.more}</div>
              </DialogContent>
            </Dialog>
          </div>
        ))}
      </div>
      {l.tra_licence && (
        <p className="mt-10 text-sm text-ink-2">
          TRA licence <b className="font-medium text-ink">{l.tra_licence}</b> · <a className="underline" href="https://verify.tra.go.ke/" target="_blank" rel="noreferrer">verify</a>
        </p>
      )}
    </section>
  );
}

function ListingSkeleton() {
  return (
    <>
      <SiteHeader width="narrow" />
      <main className="container-narrow pt-6">
        <Skeleton className="h-8 w-1/2" />
        <Skeleton className="mt-6 h-[420px] w-full rounded-xl" />
        <div className="mt-8 grid gap-24 lg:grid-cols-[1fr_372px]">
          <div className="space-y-4">
            <Skeleton className="h-6 w-2/3" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-32 w-full" />
          </div>
          <Skeleton className="hidden h-80 rounded-xl lg:block" />
        </div>
      </main>
    </>
  );
}
