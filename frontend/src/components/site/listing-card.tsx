"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { useAuthDialog, useMe } from "@/components/providers";
import { useMoney } from "@/components/site/locale";
import { Icon3D } from "@/components/ui/icon3d";
import { del, post } from "@/lib/api";
import { fmtRange } from "@/lib/format";
import { sized, srcSet } from "@/lib/img";
import type { ListingCard as Card } from "@/lib/types";
import { cn } from "@/lib/utils";

export function Photo({ src, alt, className, sizes = "(min-width: 1280px) 20vw, (min-width: 768px) 33vw, 100vw", priority }: {
  src: string; alt: string; className?: string; sizes?: string; priority?: boolean;
}) {
  const [failed, setFailed] = React.useState(false);
  if (failed || !src) return <div className={cn("bg-gradient-to-br from-ocean-100 via-sand-100 to-brand-100", className)} aria-label={alt} />;
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={sized(src, 960)}
      srcSet={srcSet(src)}
      sizes={sizes}
      alt={alt}
      loading={priority ? "eager" : "lazy"}
      decoding="async"
      onError={() => setFailed(true)}
      className={cn("object-cover text-transparent", className)} // Firefox paints alt text over a loading photo otherwise
    />
  );
}

export const typeLabel = (t: string) => (t ? t.charAt(0).toUpperCase() + t.slice(1).replace(/_/g, " ") : "Home");
export const cardTitle = (l: Pick<Card, "property_type" | "area">) => `${typeLabel(l.property_type)} in ${l.area.name}`;

export function StarIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("size-3", className)} fill="currentColor" aria-hidden>
      <path d="M15.1 1.58l-4.13 8.88-9.86 1.27a1 1 0 0 0-.54 1.74l7.3 6.57-1.97 9.85a1 1 0 0 0 1.48 1.06l8.62-5 8.63 5a1 1 0 0 0 1.48-1.06l-1.97-9.85 7.3-6.57a1 1 0 0 0-.55-1.73l-9.86-1.28-4.12-8.88a1 1 0 0 0-1.82 0z" />
    </svg>
  );
}

export function WishlistHeart({ slug, saved, className }: { slug: string; saved: boolean; className?: string }) {
  const qc = useQueryClient();
  const { data: me } = useMe();
  const { requireLogin } = useAuthDialog();
  const [on, setOn] = React.useState(saved);
  const [prevSaved, setPrevSaved] = React.useState(saved);
  if (saved !== prevSaved) {
    setPrevSaved(saved);
    setOn(saved);
  }
  const m = useMutation({
    mutationFn: (next: boolean) => (next ? post("/api/me/wishlist", { slug }) : del(`/api/me/wishlist/${slug}`)),
    onSuccess: (_, next) => {
      toast.success(next ? "Saved to your wishlist" : "Removed from wishlist");
      qc.invalidateQueries({ queryKey: ["wishlist"] });
    },
    onError: (e, next) => {
      setOn(!next);
      toast.error((e as Error).message);
    },
  });
  return (
    <button
      type="button"
      aria-label={on ? "Remove from wishlist" : "Save to wishlist"}
      aria-pressed={on}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        if (!me?.authenticated) return requireLogin("Log in to save homes you love");
        setOn(!on);
        m.mutate(!on);
      }}
      className={cn("grid size-8 place-items-center transition-transform hover:scale-110 active:scale-90", className)}
    >
      <svg viewBox="0 0 32 32" className="size-6" aria-hidden>
        <path
          d="M16 28c7-4.73 14-10 14-17a6.98 6.98 0 0 0-7-7c-1.8 0-3.58.68-4.95 2.05L16 8.1l-2.05-2.05a6.98 6.98 0 0 0-9.9 0A6.98 6.98 0 0 0 2 11c0 7 7 12.27 14 17z"
          className={cn("transition-colors", on ? "fill-brand-500" : "fill-black/50")}
          stroke="#fff"
          strokeWidth="2"
        />
      </svg>
    </button>
  );
}

export function GuestFavouriteBadge({ className, size = "md" }: { className?: string; size?: "sm" | "md" }) {
  return (
    <span
      className={cn(
        "rounded-[14px] bg-white/90 font-semibold text-ink shadow-badge backdrop-blur-sm",
        size === "sm" ? "px-2.5 py-1 text-[11px]" : "px-3 py-1.5 text-[13px]",
        className,
      )}
    >
      Guest favourite
    </span>
  );
}

/** Compact card for the home-page carousels (photo, one title line, one price · rating line). */
export function HomeCard({ listing: l, query = "", priority }: { listing: Card; query?: string; priority?: boolean }) {
  const p = l.price;
  const money = useMoney();
  return (
    <Link href={`/stays/${l.slug}${query}`} className="group block outline-none" aria-label={`${l.name}, ${l.area.name}`}>
      <div className="relative aspect-[20/19] overflow-hidden rounded-card bg-surface">
        <Photo src={l.photos[0]} alt={l.name} className="size-full transition-transform duration-500 group-hover:scale-[1.03]" sizes="(min-width: 1280px) 16vw, (min-width: 768px) 25vw, 45vw" priority={priority} />
        {l.guest_favourite && <GuestFavouriteBadge size="sm" className="absolute top-3 left-3" />}
        <WishlistHeart slug={l.slug} saved={l.wishlisted} className="absolute top-2 right-2" />
      </div>
      <h3 className="mt-2 truncate px-1 text-[13px] leading-4 font-medium">{cardTitle(l)}</h3>
      <p className="line-clamp-2 px-1 text-xs leading-4 text-ink-2">
        {p.total ? `${money(p.total)} for ${p.nights} night${p.nights !== 1 ? "s" : ""}` : `From ${money(p.from_nightly)} a night`}
        <span className="font-bold text-ink-disabled"> · </span>
        {l.rating ? (
          <>
            <StarIcon className="-mt-0.5 inline size-2.5" /> {l.rating.toFixed(2)}
          </>
        ) : "New"}
      </p>
    </Link>
  );
}

export function HomeCardSkeleton() {
  return (
    <div>
      <div className="aspect-[20/19] animate-pulse rounded-card bg-line-soft" />
      <div className="mt-2 h-3.5 w-3/4 animate-pulse rounded bg-line-soft" />
      <div className="mt-1.5 h-3 w-1/2 animate-pulse rounded bg-line-soft" />
    </div>
  );
}

/** Swipeable photo strip with hover arrows and Airbnb-style pager dots (the active one stretches). */
export function PhotoCarousel({ photos, alt, priority, className, sizes, dotsClassName, counter }: {
  photos: string[]; alt: string; priority?: boolean; className?: string; sizes?: string; dotsClassName?: string; counter?: boolean;
}) {
  const ref = React.useRef<HTMLDivElement>(null);
  const [index, setIndex] = React.useState(0);
  const list = photos.length ? photos : [""];
  const go = (e: React.MouseEvent, d: number) => {
    e.preventDefault();
    e.stopPropagation();
    const el = ref.current;
    if (el) el.scrollBy({ left: d * el.clientWidth, behavior: "smooth" });
  };
  // a five-dot window that follows the active photo
  const start = Math.min(Math.max(index - 2, 0), Math.max(list.length - 5, 0));
  return (
    <div className={cn("group/photos relative overflow-hidden bg-surface", className)}>
      <div
        ref={ref}
        onScroll={(e) => setIndex(Math.round(e.currentTarget.scrollLeft / e.currentTarget.clientWidth))}
        className="no-scrollbar flex size-full snap-x snap-mandatory overflow-x-auto overscroll-x-contain"
      >
        {list.map((src, i) => (
          <Photo key={i} src={src} alt={`${alt} — photo ${i + 1}`} className="size-full shrink-0 snap-start" priority={priority && i === 0} sizes={sizes} />
        ))}
      </div>
      {list.length > 1 && (
        <>
          <ArrowButton side="left" hidden={index === 0} onClick={(e) => go(e, -1)} />
          <ArrowButton side="right" hidden={index >= list.length - 1} onClick={(e) => go(e, 1)} />
          {counter ? (
            <span className={cn("pointer-events-none absolute right-4 bottom-3 rounded bg-[rgb(34_34_34/0.66)] px-2 py-0.5 text-xs font-medium text-white tabular-nums", dotsClassName)}>
              {index + 1} / {list.length}
            </span>
          ) : (
            <div className={cn("pointer-events-none absolute inset-x-0 bottom-3 flex items-center justify-center gap-1.5", dotsClassName)}>
              {list.slice(start, start + 5).map((_, i) => {
                const n = start + i;
                // dots at the window's edges shrink when more photos lie beyond them
                const edge = (i === 0 && start > 0) || (i === 4 && start + 5 < list.length);
                return (
                  <span
                    key={n}
                    className={cn(
                      "rounded-full transition-all duration-300",
                      n === index ? "h-1.5 w-4 bg-white/95" : edge ? "size-1 bg-white/70" : "size-1.5 bg-white/70",
                    )}
                  />
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function ArrowButton({ side, hidden, onClick }: { side: "left" | "right"; hidden: boolean; onClick: (e: React.MouseEvent) => void }) {
  const Icon = side === "left" ? ChevronLeft : ChevronRight;
  return (
    <button
      type="button"
      aria-label={side === "left" ? "Previous photo" : "Next photo"}
      onClick={onClick}
      tabIndex={-1}
      className={cn(
        "absolute top-1/2 hidden size-8 -translate-y-1/2 place-items-center rounded-full bg-white/90 opacity-0 shadow-badge transition-[opacity,transform] group-hover/photos:opacity-100 hover:scale-105 hover:bg-white md:grid",
        side === "left" ? "left-3" : "right-3",
        hidden && "md:hidden",
      )}
    >
      <Icon className="size-3" strokeWidth={3} />
    </button>
  );
}

/** Rich search-results card: photo carousel, type + rating, name, rooms, dates, total price, perks. */
export function ListingCard({ listing: l, query = "", priority, checkIn, checkOut, onHover }: {
  listing: Card; query?: string; priority?: boolean; checkIn?: string; checkOut?: string; onHover?: (id: number | null) => void;
}) {
  const p = l.price;
  const money = useMoney();
  return (
    <Link
      href={`/stays/${l.slug}${query}`}
      className="group block outline-none"
      aria-label={`${l.name}, ${l.area.name}`}
      onMouseEnter={() => onHover?.(l.id)}
      onMouseLeave={() => onHover?.(null)}
    >
      <div className="relative">
        <PhotoCarousel photos={l.photos} alt={l.name} priority={priority} className="aspect-[20/19] rounded-card sm:aspect-[4/3]" sizes="(min-width: 1280px) 30vw, (min-width: 768px) 45vw, 100vw" />
        {l.guest_favourite && (
          <span className="absolute top-3 left-3 flex items-center gap-1 rounded-[14px] bg-white/90 px-3 py-1.5 text-[13px] font-semibold shadow-badge backdrop-blur-sm">
            {l.rating && l.rating >= 4.85 && <Icon3D name="trophy" size={16} />}
            Guest favourite
          </span>
        )}
        <WishlistHeart slug={l.slug} saved={l.wishlisted} className="absolute top-2.5 right-2.5" />
      </div>
      <div className="mt-3 space-y-0.5 px-1 text-[15px] leading-[19px] font-medium">
        <div className="flex items-start justify-between gap-2">
          <h3 className="truncate">{cardTitle(l)}</h3>
          {l.rating ? (
            <span className="flex shrink-0 items-center gap-1">
              <StarIcon /> {l.rating.toFixed(2)} ({l.reviews_count})
            </span>
          ) : (
            <span className="shrink-0">New</span>
          )}
        </div>
        <p className="truncate text-ink-2">{l.name}</p>
        <p className="truncate text-ink-2">
          {l.bedrooms} bedroom{l.bedrooms !== 1 ? "s" : ""} · {l.beds} bed{l.beds !== 1 ? "s" : ""} · {l.bathrooms} bath{l.bathrooms !== 1 ? "s" : ""}
        </p>
        {checkIn && checkOut && <p className="text-ink-2">{fmtRange(checkIn, checkOut)}</p>}
        <p className="pt-1">
          {p.total ? (
            <>
              <span className="underline decoration-1 underline-offset-2">{money(p.total)}</span>
              <span className="text-ink-2"> for {p.nights} night{p.nights !== 1 ? "s" : ""}</span>
            </>
          ) : (
            <>
              <span>{money(p.from_nightly)}</span>
              <span className="text-ink-2"> a night · sleeps {l.max_guests}</span>
            </>
          )}
        </p>
        <div className="flex flex-wrap gap-1.5 pt-1.5">
          {l.free_cancellation && <Perk>Free cancellation</Perk>}
          {l.breakfast_available && <Perk>Breakfast available</Perk>}
        </div>
      </div>
    </Link>
  );
}

function Perk({ children }: { children: React.ReactNode }) {
  return <span className="rounded-md bg-chip/75 px-1 py-0.5 text-[11px] leading-[15px] font-medium text-ink-2">{children}</span>;
}

export function ListingCardSkeleton() {
  return (
    <div>
      <div className="aspect-[20/19] animate-pulse rounded-card bg-line-soft sm:aspect-[4/3]" />
      <div className="mt-3 h-4 w-2/3 animate-pulse rounded bg-line-soft" />
      <div className="mt-2 h-4 w-1/2 animate-pulse rounded bg-line-soft" />
      <div className="mt-2 h-4 w-1/3 animate-pulse rounded bg-line-soft" />
    </div>
  );
}
