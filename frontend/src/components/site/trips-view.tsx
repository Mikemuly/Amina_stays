"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Luggage, Smartphone } from "lucide-react";
import Link from "next/link";

import { useConfig } from "@/components/providers";
import { AuthGate } from "@/components/site/auth-gate";
import { SiteHeader } from "@/components/site/header";
import { Photo } from "@/components/site/listing-card";
import { Button } from "@/components/ui/button";
import { Badge, EmptyState, Skeleton } from "@/components/ui/misc";
import { get } from "@/lib/api";
import { CHANNEL_LABEL, fmtDate, fmtRange, kes, nightsBetween, plural, STATUS_TONE } from "@/lib/format";
import type { TripCard } from "@/lib/types";

const UPCOMING = new Set(["held", "confirmed", "checked_in"]);

export function TripsView() {
  return (
    <AuthGate title="Log in to see your trips">
      <Trips />
    </AuthGate>
  );
}

function Trips() {
  const { data: trips, isLoading } = useQuery({ queryKey: ["trips"], queryFn: () => get<TripCard[]>("/api/bookings") });
  const { data: config } = useConfig();
  const upcoming = (trips ?? []).filter((t) => UPCOMING.has(t.status)).sort((a, b) => a.check_in.localeCompare(b.check_in));
  const past = (trips ?? []).filter((t) => t.status === "completed");
  const cancelled = (trips ?? []).filter((t) => ["cancelled", "no_show", "refund_due"].includes(t.status));

  return (
    <>
      <SiteHeader />
      <main className="container-narrow max-w-[1120px] pt-10 pb-24">
        <h1 className="text-[32px] font-bold tracking-tight">Trips</h1>
        {isLoading ? (
          <div className="mt-8 grid gap-6 md:grid-cols-2">
            {[0, 1].map((i) => <Skeleton key={i} className="h-72 rounded-2xl" />)}
          </div>
        ) : !trips?.length ? (
          <div className="mt-8 rounded-2xl border border-line-soft">
            <EmptyState
              icon={<Luggage className="size-10" strokeWidth={1.3} />}
              title="No trips booked… yet!"
              action={<Button asChild variant="dark" size="lg"><Link href="/">Start searching</Link></Button>}
            >
              Time to dust off your bags and start planning your next coastal escape. Booked by SMS, USSD or phone? Trips made with this number show up here too.
            </EmptyState>
          </div>
        ) : (
          <div className="space-y-14">
            {upcoming.length > 0 && (
              <section className="mt-8">
                <h2 className="sr-only">Upcoming</h2>
                <div className="grid gap-6 md:grid-cols-2">
                  {upcoming.map((t, i) => <UpcomingCard key={t.ref} trip={t} priority={i === 0} />)}
                </div>
              </section>
            )}
            {past.length > 0 && <TripList title="Where you've been" trips={past} />}
            {cancelled.length > 0 && <TripList title="Cancelled" trips={cancelled} />}
          </div>
        )}
        {config?.channels.ussd_code && (
          <p className="mt-14 flex items-center gap-2 text-sm text-ink-2">
            <Smartphone className="size-4" /> No data? Dial <b className="text-ink">{config.channels.ussd_code}</b> → &ldquo;My booking&rdquo; to manage a trip from any phone.
          </p>
        )}
      </main>
    </>
  );
}

function UpcomingCard({ trip: t, priority }: { trip: TripCard; priority?: boolean }) {
  const nights = nightsBetween(t.check_in, t.check_out);
  return (
    <Link href={`/trips/${t.ref}`} className="group block overflow-hidden rounded-2xl border border-line-soft shadow-soft transition-shadow hover:shadow-card">
      <div className="relative aspect-[16/9] overflow-hidden">
        <Photo src={t.unit.cover} alt={t.unit.name} className="size-full transition-transform duration-500 group-hover:scale-[1.03]" sizes="(min-width: 768px) 560px, 100vw" priority={priority} />
        <div className="absolute top-4 left-4 flex gap-2">
          <Badge tone={STATUS_TONE[t.status] ?? "neutral"} className="bg-white/95 shadow-sm">{t.status_label}</Badge>
          {t.balance_due > 0 && t.status !== "held" && <Badge tone="warning" className="shadow-sm">Balance {kes(t.balance_due)}</Badge>}
        </div>
      </div>
      <div className="flex items-center justify-between gap-4 p-5">
        <div className="min-w-0">
          <p className="truncate text-lg font-semibold">{t.unit.name}</p>
          <p className="text-ink-2">{fmtRange(t.check_in, t.check_out)} · {plural(nights, "night")} · {t.unit.area}</p>
          <p className="mt-1 text-sm text-ink-2">
            {t.status === "held" ? "Finish paying to confirm" : t.status === "checked_in" ? "You're staying here now" : `Check-in ${fmtDate(t.check_in, "EEEE d MMM")}`}
            {t.channel !== "web" && ` · booked by ${CHANNEL_LABEL[t.channel] ?? t.channel}`}
          </p>
        </div>
        <ChevronRight className="size-5 shrink-0 text-ink-2" />
      </div>
    </Link>
  );
}

function TripList({ title, trips }: { title: string; trips: TripCard[] }) {
  return (
    <section>
      <h2 className="text-[22px] font-bold tracking-tight">{title}</h2>
      <div className="mt-5 grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
        {trips.map((t) => (
          <Link key={t.ref} href={`/trips/${t.ref}`} className="flex items-center gap-4 rounded-xl p-2 -m-2 hover:bg-surface">
            <div className="size-16 shrink-0 overflow-hidden rounded-xl"><Photo src={t.unit.cover} alt={t.unit.name} className="size-full" sizes="64px" /></div>
            <div className="min-w-0">
              <p className="truncate font-semibold">{t.unit.name}</p>
              <p className="text-sm text-ink-2">{t.unit.area}</p>
              <p className="text-sm text-ink-2">{fmtDate(t.check_in, "d MMM")} – {fmtDate(t.check_out, "d MMM yyyy")}</p>
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}
