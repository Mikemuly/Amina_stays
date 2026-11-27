"use client";

import { Bath, BedDouble, Camera, ImageOff, Plus, Star, Users } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { ErrorBlock, PageHeader } from "@/components/host/common";
import { Button } from "@/components/ui/button";
import { EmptyState, Skeleton } from "@/components/ui/misc";
import { kes, plural } from "@/lib/format";
import { sized } from "@/lib/img";
import { cn } from "@/lib/utils";

import { useAreas, useListings } from "./queries";
import type { Housekeeping, HostListing, ListingStatus } from "./types";
import { Segmented, humanize } from "./ui";

export const STATUS_META: Record<ListingStatus, { label: string; dot: string; text: string }> = {
  active: { label: "Listed", dot: "bg-success", text: "Bookable on every channel" },
  paused: { label: "Paused", dot: "bg-warning", text: "Hidden from search; existing bookings stay" },
  draft: { label: "Draft", dot: "bg-ink-3", text: "Only visible in the console" },
};

export const HOUSEKEEPING_META: Record<Housekeeping, { label: string; className: string }> = {
  clean: { label: "Clean", className: "bg-success-50 text-success" },
  dirty: { label: "Needs cleaning", className: "bg-danger-50 text-danger" },
  cleaning: { label: "Cleaning now", className: "bg-ocean-50 text-ocean-700" },
  inspect: { label: "Needs inspection", className: "bg-warning-50 text-warning" },
};

export function StatusChip({ status, className }: { status: ListingStatus; className?: string }) {
  const m = STATUS_META[status];
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full bg-white px-2.5 py-1 text-[12px] font-semibold text-ink shadow-sm", className)}>
      <span className={cn("size-2 rounded-full", m.dot)} />
      {m.label}
    </span>
  );
}

export function HousekeepingChip({ value, className }: { value: Housekeeping; className?: string }) {
  const m = HOUSEKEEPING_META[value] ?? HOUSEKEEPING_META.clean;
  return <span className={cn("inline-flex items-center rounded-full px-2.5 py-1 text-[12px] font-semibold", m.className, className)}>{m.label}</span>;
}

type Filter = "all" | ListingStatus;

export function ListingsPage() {
  const { data, isLoading, error, refetch } = useListings();
  const { data: areas } = useAreas();
  const [filter, setFilter] = React.useState<Filter>("all");

  const areaName = (slug: string) => areas?.find((a) => a.slug === slug)?.name ?? humanize(slug);
  const listings = data ?? [];
  const count = (s: ListingStatus) => listings.filter((l) => l.status === s).length;
  const shown = filter === "all" ? listings : listings.filter((l) => l.status === filter);
  const needsCleaning = listings.filter((l) => l.housekeeping !== "clean").length;

  return (
    <>
      <PageHeader
        title="Listings"
        subtitle="Your homes as guests find them on the website, USSD, SMS and voice — one listing, every channel."
        actions={
          <Button asChild variant="brand">
            <Link href="/host/listings/new">
              <Plus className="size-4" /> New listing
            </Link>
          </Button>
        }
      />

      {error ? (
        <ErrorBlock error={error} retry={refetch} />
      ) : (
        <>
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
            <Segmented<Filter>
              label="Filter listings by status"
              value={filter}
              onChange={setFilter}
              options={[
                { value: "all", label: "All", count: listings.length },
                { value: "active", label: "Listed", count: count("active") },
                { value: "paused", label: "Paused", count: count("paused") },
                { value: "draft", label: "Drafts", count: count("draft") },
              ]}
            />
            {!isLoading && listings.length > 0 && (
              <p className="text-[13px] text-ink-2">
                {plural(count("active"), "home")} bookable
                {needsCleaning > 0 && <span className="text-danger"> · {needsCleaning} not guest-ready</span>}
              </p>
            )}
          </div>

          {isLoading ? (
            <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="overflow-hidden rounded-2xl border border-line-soft bg-white">
                  <Skeleton className="aspect-[4/3] rounded-none" />
                  <div className="space-y-2 p-4">
                    <Skeleton className="h-4 w-2/3" />
                    <Skeleton className="h-3 w-1/3" />
                  </div>
                </div>
              ))}
            </div>
          ) : shown.length === 0 ? (
            <EmptyState
              icon={<ImageOff className="size-5" />}
              title={filter === "all" ? "No homes yet" : `No ${STATUS_META[filter as ListingStatus].label.toLowerCase()} homes`}
              action={
                filter === "all" ? (
                  <Button asChild variant="dark">
                    <Link href="/host/listings/new">
                      <Plus className="size-4" /> Create your first listing
                    </Link>
                  </Button>
                ) : undefined
              }
            >
              {filter === "all" ? "Add a home with photos, prices and arrival details — it goes live on every channel at once." : "Try another filter."}
            </EmptyState>
          ) : (
            <ul className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
              {shown.map((l) => (
                <li key={l.id}>
                  <ListingTile listing={l} areaName={areaName(l.area)} />
                </li>
              ))}
              {filter === "all" && (
                <li>
                  <Link
                    href="/host/listings/new"
                    className="flex h-full min-h-64 flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-line bg-white/60 p-6 text-center text-ink-2 transition hover:border-ink-3 hover:bg-white hover:text-ink"
                  >
                    <span className="grid size-12 place-items-center rounded-full bg-surface">
                      <Plus className="size-5" />
                    </span>
                    <span className="text-[15px] font-semibold">Add another home</span>
                    <span className="max-w-56 text-[13px]">Start as a draft — publish when photos and prices are ready.</span>
                  </Link>
                </li>
              )}
            </ul>
          )}
        </>
      )}
    </>
  );
}

function ListingTile({ listing: l, areaName }: { listing: HostListing; areaName: string }) {
  const cover = l.photos[0]?.src;
  return (
    <Link
      href={`/host/listings/${l.id}`}
      className="group block h-full overflow-hidden rounded-2xl border border-line-soft bg-white transition-shadow hover:shadow-card"
    >
      <div className="relative aspect-[4/3] overflow-hidden bg-surface">
        {cover ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={sized(cover, 720)} alt="" loading="lazy" className="size-full object-cover transition duration-500 group-hover:scale-[1.03]" />
        ) : (
          <div className="grid size-full place-items-center text-ink-3">
            <span className="flex flex-col items-center gap-2 text-[13px] font-medium">
              <ImageOff className="size-6" /> No photos yet
            </span>
          </div>
        )}
        <div className="absolute top-3 left-3 flex flex-wrap gap-1.5">
          <StatusChip status={l.status} />
          {l.is_featured && (
            <span className="inline-flex items-center gap-1 rounded-full bg-white px-2.5 py-1 text-[12px] font-semibold text-ink shadow-sm">
              <Star className="size-3.5 fill-brand-500 text-brand-500" /> Featured
            </span>
          )}
        </div>
        <span className="absolute top-3 right-3 inline-flex items-center gap-1 rounded-full bg-black/55 px-2 py-0.5 text-[11.5px] font-semibold text-white backdrop-blur">
          <Camera className="size-3.5" /> {l.photos.length}
        </span>
        <HousekeepingChip value={l.housekeeping} className="absolute bottom-3 left-3 shadow-sm" />
      </div>
      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="truncate text-[15px] font-bold">{l.name}</h3>
            <p className="truncate text-[13px] text-ink-2">
              {humanize(l.property_type)} · {areaName}
            </p>
          </div>
          <div className="shrink-0 text-right">
            <p className="text-[15px] font-bold tabular-nums">{kes(l.base_price)}</p>
            <p className="text-[12px] text-ink-2">per night</p>
          </div>
        </div>
        <div className="mt-3 flex items-center gap-4 border-t border-line-soft pt-3 text-[13px] text-ink-2">
          <span className="inline-flex items-center gap-1.5">
            <BedDouble className="size-4" /> {plural(l.bedrooms, "bedroom")}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Users className="size-4" /> {l.max_guests}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Bath className="size-4" /> {Number(l.bathrooms)}
          </span>
          <span className="ml-auto text-[12px]">min {plural(l.min_nights, "night")}</span>
        </div>
      </div>
    </Link>
  );
}
