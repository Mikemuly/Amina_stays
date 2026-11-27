"use client";

import { useQuery } from "@tanstack/react-query";
import { addDays, isFriday, isSaturday, nextFriday, startOfToday } from "date-fns";
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { useConfig, useHydrated, usePayOptions } from "@/components/providers";
import { CarouselRow } from "@/components/site/carousel";
import { ExtraCard, ExtraDialog, useAddons } from "@/components/site/extras";
import { guestsLabel } from "@/components/site/guest-picker";
import { MobileTabs, SiteHeader } from "@/components/site/header";
import { HomeCard, HomeCardSkeleton, Photo } from "@/components/site/listing-card";
import { areaStyle, searchQuery, useAreas, useLastSearch } from "@/components/site/search-bar";
import { Icon3D, type Icon3DName } from "@/components/ui/icon3d";
import { get, qs } from "@/lib/api";
import { fmtRange, iso } from "@/lib/format";
import type { Addon, ListingCard as Card } from "@/lib/types";
import { cn } from "@/lib/utils";

type Results = { results: Card[]; count: number; nights: number | null };

// Extra rows on the Homes tab, built from each home's tags (each links to the matching search).
const HOME_ROWS: { tag: string; title: string }[] = [
  { tag: "beachfront", title: "Beachfront homes" },
  { tag: "pool", title: "Homes with a pool" },
  { tag: "family", title: "Room for the whole family" },
  { tag: "couples", title: "Hideaways for two" },
];

export const useHomes = () => useQuery({ queryKey: ["listings", ""], queryFn: () => get<Results>("/api/listings") });

/** "/" is Airbnb's "All" tab (homes, experiences and services); "/homes" keeps to homes. */
export function HomeView({ tab = "all" }: { tab?: "all" | "homes" }) {
  const params = useSearchParams();
  const router = useRouter();
  const legacy = params.toString();
  React.useEffect(() => {
    // old "/?area=…" links and bookmarks now live on the search page
    if (legacy) router.replace(`/s?${legacy}`);
  }, [legacy, router]);

  const hydrated = useHydrated();
  const { data, isLoading } = useHomes();
  const popular = [...(data?.results ?? [])].sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0));

  return (
    <>
      <SiteHeader mode="home" tab={tab} mobileSearch />
      <MobileTabs active={tab} />
      <ContinueSearch />
      <main className="container-site pb-6">
        <h1 className="sr-only">{tab === "homes" ? "Homes on the Kenyan coast" : "Homes, experiences and services on the Kenyan coast"}</h1>
        <Destinations />
        <CarouselRow title="Popular homes in Mombasa" href="/s?sort=rating">
          {isLoading ? Array.from({ length: 6 }).map((_, i) => <HomeCardSkeleton key={i} />) : popular.map((l, i) => <HomeCard key={l.id} listing={l} priority={i < 3} />)}
        </CarouselRow>
        {hydrated && <WeekendRow />}
        {tab === "all" ? (
          <>
            <ExtrasRow />
            <BookWithoutData />
          </>
        ) : (
          HOME_ROWS.map((r) => {
            const homes = popular.filter((l) => l.tags.includes(r.tag));
            return homes.length > 1 ? (
              <CarouselRow key={r.tag} title={r.title} href={`/s?tag=${r.tag}`}>
                {homes.map((l) => <HomeCard key={l.id} listing={l} />)}
              </CarouselRow>
            ) : null;
          })
        )}
        <WhyDirect />
        <div className="pointer-events-none sticky bottom-24 z-20 mt-10 flex justify-center md:bottom-6">
          <Link
            href="/help#prices"
            className="pointer-events-auto flex items-center gap-2 rounded-full bg-white py-2 pr-5 pl-3 text-sm font-medium shadow-[0_6px_20px_rgb(0_0_0/0.18)] transition-transform hover:scale-[1.03]"
          >
            <Icon3D name="label" size={26} />
            Prices include all fees
          </Link>
        </div>
      </main>
    </>
  );
}

/** Airbnb's "Continue your search": the last search, with a little deck of its photos, under the header. */
function ContinueSearch() {
  const last = useLastSearch();
  const { data: areas } = useAreas();
  const { data } = useHomes();
  if (!last) return null;
  const area = areas?.find((a) => a.slug === last.area);
  const homes = (data?.results ?? []).filter((l) => !last.area || l.area.slug === last.area);
  const photos = [area?.photo_url, ...homes.flatMap((l) => l.photos.slice(0, 2))].filter((p): p is string => !!p).slice(0, 3);
  const place = last.area ? (area?.name ?? last.area.replace(/-/g, " ")) : "Anywhere";
  const when = last.checkIn && last.checkOut ? fmtRange(last.checkIn, last.checkOut) : last.adults + last.children ? guestsLabel(last) : "";
  return (
    <div className="border-b border-line">
      <Link href={`/s${searchQuery(last)}`} className="group mx-auto flex w-fit max-w-full items-center gap-3 px-6 py-3 md:gap-4 md:px-12 md:py-[15px]">
        <PhotoDeck photos={photos} />
        <span className="flex min-w-0 items-center gap-1.5 text-sm leading-5 md:text-base">
          <span className="shrink-0 font-medium">Continue your search</span>
          <span className="truncate text-ink-2">{[place, when].filter(Boolean).join(" · ")}</span>
          <ArrowRight className="size-3 shrink-0 transition-transform group-hover:translate-x-0.5" strokeWidth={2.6} />
        </span>
      </Link>
    </div>
  );
}

// back to front: two tilted photos peek out from behind a straight one, and fan out on hover
const DECK_TILT = ["-translate-x-1 -rotate-[9deg] group-hover:-rotate-[14deg]", "translate-x-1 rotate-[8deg] group-hover:rotate-[13deg]", ""];

function PhotoDeck({ photos }: { photos: string[] }) {
  const deck = (photos.length ? photos : [""]).slice(0, 3).reverse();
  return (
    <span className="relative size-10 shrink-0 md:size-14" aria-hidden>
      {deck.map((src, i) => (
        <span
          key={`${i}-${src}`}
          className={cn(
            "absolute inset-0 overflow-hidden rounded-xl border-2 border-white bg-surface shadow-[0_2.8px_5.6px_rgb(0_0_0/0.1),0_1.4px_4.2px_rgb(0_0_0/0.04)] transition-transform duration-300",
            DECK_TILT[i + 3 - deck.length],
          )}
        >
          <Photo src={src} alt="" className="size-full" sizes="56px" />
        </span>
      ))}
    </span>
  );
}

function Destinations() {
  const { data: areas, isLoading } = useAreas();
  return (
    <CarouselRow title="Destinations for you" cols="tiles">
      {isLoading
        ? Array.from({ length: 5 }).map((_, i) => <div key={i} className="aspect-[53/50] animate-pulse rounded-2xl bg-line-soft" />)
        : (areas ?? []).map((a) => (
            <Link key={a.slug} href={`/s?area=${a.slug}`} className="group block">
              <div className="aspect-[53/50] overflow-hidden rounded-2xl bg-surface">
                <Photo src={a.photo_url} alt={a.name} className="size-full transition-transform duration-500 group-hover:scale-105" sizes="160px" />
              </div>
              <p className="mt-2 truncate text-[13px] font-medium">{a.name}</p>
              <p className="line-clamp-2 text-xs text-ink-2">{areaStyle(a).tagline}</p>
            </Link>
          ))}
    </CarouselRow>
  );
}

/** "Available this weekend": real availability and all-in totals for the coming Friday → Sunday. */
function WeekendRow() {
  const today = startOfToday();
  const start = isFriday(today) || isSaturday(today) ? today : nextFriday(today);
  const range = { checkIn: iso(start), checkOut: iso(addDays(start, 2)) };
  const query = qs({ check_in: range.checkIn, check_out: range.checkOut });
  const { data, isLoading } = useQuery({ queryKey: ["listings", query], queryFn: () => get<Results>(`/api/listings${query}`) });
  if (!isLoading && !data?.results.length) return null;
  const link = searchQuery({ ...range, adults: 0, children: 0, infants: 0 });
  return (
    <CarouselRow title="Available this weekend" subtitle={`${fmtRange(range.checkIn, range.checkOut)} · totals for 2 nights, fees included`} href={`/s${link}`}>
      {isLoading ? Array.from({ length: 6 }).map((_, i) => <HomeCardSkeleton key={i} />) : data!.results.map((l) => <HomeCard key={l.id} listing={l} query={link} />)}
    </CarouselRow>
  );
}

function ExtrasRow() {
  const { data: addons } = useAddons();
  const [open, setOpen] = React.useState<Addon | null>(null);
  if (!addons?.length) return null;
  const ordered = [...addons].sort((a, b) => Number(b.category === "experience") - Number(a.category === "experience"));
  return (
    <>
      <CarouselRow title="Make your stay special" subtitle="Experiences and services from Amina's own team" href="/services">
        {ordered.map((a) => <ExtraCard key={a.code} addon={a} onOpen={() => setOpen(a)} />)}
      </CarouselRow>
      <ExtraDialog addon={open} onClose={() => setOpen(null)} />
    </>
  );
}

const USSD_MENU = ["Book a stay", "Prices & homes", "My booking", "Breakfast", "Report problem", "Talk to Amina"];

function BookWithoutData() {
  const { data: config } = useConfig();
  const { mpesa } = usePayOptions();
  const c = config?.channels;
  const ways: { icon: Icon3DName; title: string; value?: string; fallback: string; text: string }[] = [
    { icon: "mobile-phone", title: "USSD", value: c?.ussd_code, fallback: "Dial our code", text: "Any phone, no internet" },
    { icon: "speech-balloon", title: "SMS · Ask Amina", value: c?.sms_number, fallback: "Text our number", text: "English or Kiswahili" },
    { icon: "antenna", title: "Voice · Call Amina", value: c?.voice_number, fallback: "Call our line", text: "A spoken menu, 24/7" },
  ];
  return (
    <section id="book-your-way" className="scroll-mt-28 pt-16">
      <div className="grid overflow-hidden rounded-3xl bg-surface lg:grid-cols-[1.25fr_1fr]">
        <div className="p-8 md:p-12">
          <p className="text-sm font-semibold text-brand-600">No data? No problem.</p>
          <h2 className="mt-2 max-w-lg text-[28px] leading-tight font-semibold tracking-tight md:text-[32px]">Book from any phone — even without internet.</h2>
          <p className="mt-3 max-w-lg text-[15px] leading-relaxed text-ink-2">
            Your phone number is your account on every channel.{" "}
            {mpesa
              ? "Start on USSD, pay with M-Pesa, and pick up your trip here — or never open a browser at all."
              : "Start on USSD, pay by card through the secure link we text you, and pick up your trip here."}
          </p>
          <div className="mt-8 grid gap-3 sm:grid-cols-3">
            {ways.map((w) => (
              <div key={w.title} className="rounded-2xl bg-white p-4 shadow-[0_1px_2px_rgb(0_0_0/0.06)]">
                <Icon3D name={w.icon} size={36} />
                <p className="mt-3 text-[13px] text-ink-2">{w.title}</p>
                <p className={cn("text-[15px] font-semibold", w.value && "font-mono")}>{w.value || w.fallback}</p>
                <p className="mt-0.5 text-xs text-ink-2">{w.text}</p>
              </div>
            ))}
          </div>
        </div>
        <div className="relative hidden items-center justify-center overflow-hidden bg-[linear-gradient(160deg,#ffe3da_0%,#cdeeec_100%)] p-10 lg:flex" aria-hidden>
          <div className="w-[230px] rounded-[38px] border-[9px] border-ink bg-[#dfe7e2] px-3 pt-10 pb-14 shadow-float">
            <div className="rounded-lg bg-white p-3 font-mono text-[12px] leading-[1.55] text-ink shadow-sm">
              <p>Karibu Amina Stays</p>
              {USSD_MENU.map((m, i) => (
                <p key={m}>{i + 1}. {m}</p>
              ))}
              <p className="text-danger">9. EMERGENCY</p>
              <div className="mt-2 h-6 rounded border border-line" />
              <div className="mt-2 flex justify-between text-[11px] font-semibold text-ocean-600">
                <span>Cancel</span>
                <span>Send</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export function WhyDirect() {
  const { mpesa } = usePayOptions();
  const items: { icon: Icon3DName; title: string; text: string }[] = [
    { icon: "money-bag", title: "No booking fees", text: `The price you see is the total — cleaning and the 2% tourism levy included. ${mpesa ? "Pay by M-Pesa, card, or 30% now and the rest later." : "Pay by card, in full or 30% now and the rest later."}` },
    { icon: "shield", title: "Safe by design", text: "Licensed by the Tourism Regulatory Authority, guarded 24/7, and a HELP line that rings Amina's phone — day or night." },
    { icon: "key", title: "Self check-in", text: "Your door code arrives by SMS on arrival morning and stops working at checkout. No waiting around for keys." },
    { icon: "hot-beverage", title: "A real host", text: "Swahili breakfast on your veranda, airport pickups, local tips — and answers in minutes, in your language." },
  ];
  return (
    <section className="pt-16">
      <h2 className="text-[22px] font-semibold tracking-tight md:text-[26px]">Why guests book direct with Amina</h2>
      <div className="mt-8 grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
        {items.map((i) => (
          <div key={i.title}>
            <Icon3D name={i.icon} size={48} />
            <h3 className="mt-3 text-base font-semibold">{i.title}</h3>
            <p className="mt-1 text-[15px] leading-relaxed text-ink-2">{i.text}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
