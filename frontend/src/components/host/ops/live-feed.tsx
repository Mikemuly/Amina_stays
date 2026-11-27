"use client";

import { useQuery } from "@tanstack/react-query";
import { Radio } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { ErrorBlock } from "@/components/host/common";
import { usePayOptions } from "@/components/providers";
import { Skeleton } from "@/components/ui/misc";
import { get } from "@/lib/api";
import { cn } from "@/lib/utils";

import { activityMeta, KindBubble, MiniEmpty, OpsKeyframes } from "./bits";
import { relTime, useNow } from "./lib";
import type { ActivityItem } from "./types";

const feedChannels = (mpesa: boolean) => ["SMS", "USSD", "Voice", "Web", ...(mpesa ? ["M-Pesa"] : [])];

/** Everything happening across SMS, USSD, voice, web, payments and door locks — newest first, updating every 5 s. */
export function LiveFeed({ className, limit = 20 }: { className?: string; limit?: number }) {
  const { mpesa } = usePayOptions();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["host", "ops", "activity", limit],
    queryFn: () => get<ActivityItem[]>(`/api/host/activity?limit=${limit}`),
    refetchInterval: 5_000,
  });
  const now = useNow(15_000);

  // Items that arrive after the first load get a highlight as they slide in.
  const [baseline, setBaseline] = React.useState<number | null>(null);
  if (baseline === null && data) setBaseline(data.reduce((max, a) => Math.max(max, a.id), 0));
  const fresh = data && baseline !== null ? data.filter((a) => a.id > baseline).length : 0;

  return (
    <section className={cn("flex min-h-0 flex-col overflow-hidden rounded-2xl border border-line-soft bg-white", className)} aria-label="Live channel feed">
      <OpsKeyframes />
      <div className="flex items-start justify-between gap-3 border-b border-line-soft px-5 py-3.5">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-[15px] font-bold">
            <Radio className="size-4 text-brand-500" /> Live channel feed
          </h2>
          <p className="mt-0.5 truncate text-xs text-ink-2">{feedChannels(mpesa).join(" · ")} · door locks</p>
        </div>
        <span className="mt-0.5 inline-flex shrink-0 items-center gap-1.5 rounded-full bg-success-50 px-2.5 py-1 text-[11px] font-bold tracking-wider text-success uppercase">
          <span className="relative flex size-2">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-60" />
            <span className="relative inline-flex size-2 rounded-full bg-success" />
          </span>
          Live
        </span>
      </div>

      {fresh > 0 && (
        <p className="border-b border-line-soft bg-brand-50/60 px-5 py-1.5 text-xs font-semibold text-brand-700" aria-live="polite">
          {fresh} new since you opened this page
        </p>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="space-y-4 p-5">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="flex gap-3">
                <Skeleton className="size-9 rounded-full" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-3.5 w-4/5" />
                  <Skeleton className="h-3 w-1/3" />
                </div>
              </div>
            ))}
          </div>
        ) : error ? (
          <div className="p-5">
            <ErrorBlock error={error} retry={() => refetch()} />
          </div>
        ) : !data?.length ? (
          <MiniEmpty icon={<Radio />} title="Quiet for now">
            Bookings, payments and messages from every channel appear here the moment they happen.
          </MiniEmpty>
        ) : (
          <ol className="divide-y divide-line-soft">
            {data.map((a) => {
              const meta = activityMeta(a.kind, a.channel);
              const isNew = baseline !== null && a.id > baseline;
              return (
                <li
                  key={a.id}
                  className="flex gap-3 px-5 py-3 animate-fade-in"
                  style={isNew ? { animation: "ops-in .45s cubic-bezier(.2,.8,.2,1), ops-flash 3s ease-out" } : undefined}
                >
                  <KindBubble kind={a.kind} channel={a.channel} size={34} />
                  <div className="min-w-0 flex-1">
                    <p className="text-[13.5px] leading-snug font-medium text-ink">{a.title}</p>
                    <p className="mt-1 flex flex-wrap items-center gap-x-1.5 text-xs text-ink-2">
                      <span className="font-semibold" style={{ color: meta.color }}>
                        {meta.label}
                      </span>
                      {a.booking_ref && (
                        <>
                          <span aria-hidden>·</span>
                          <Link href={`/host/reservations/${a.booking_ref}`} className="font-medium hover:text-ink hover:underline">
                            {a.booking_ref}
                          </Link>
                        </>
                      )}
                      <span aria-hidden>·</span>
                      <time dateTime={a.created_at}>{relTime(a.created_at, now)}</time>
                    </p>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </div>
      <p className="border-t border-line-soft px-5 py-2.5 text-[11px] text-ink-3">Updates every 5 seconds · latest {limit} events</p>
    </section>
  );
}
