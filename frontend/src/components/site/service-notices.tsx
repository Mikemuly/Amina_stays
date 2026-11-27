"use client";

import { useQuery } from "@tanstack/react-query";
import { CalendarClock, TriangleAlert } from "lucide-react";

import { get } from "@/lib/api";
import { fmtDateTime, fmtTime } from "@/lib/format";
import type { ServiceNotice } from "@/lib/types";
import { cn } from "@/lib/utils";

const sameDay = (a: string, b: string) => new Date(a).toDateString() === new Date(b).toDateString();

/** Outages and planned work at the guest's home (the same alerts they get by SMS). Hidden when all is well. */
export function ServiceNotices({ unitSlug, className }: { unitSlug: string; className?: string }) {
  const { data } = useQuery({
    queryKey: ["notices", unitSlug],
    queryFn: () => get<ServiceNotice[]>(`/api/notices?unit=${encodeURIComponent(unitSlug)}`),
    refetchInterval: 60_000,
  });
  if (!data?.length) return null;
  return (
    <div className={cn("space-y-3", className)}>
      {data.map((n) => {
        const live = n.status === "active";
        const Icon = live ? TriangleAlert : CalendarClock;
        const when = live
          ? `Since ${fmtTime(n.starts_at)}${n.expected_end ? ` · expected back by ${sameDay(n.starts_at, n.expected_end) ? fmtTime(n.expected_end) : fmtDateTime(n.expected_end)}` : ""}`
          : `Planned for ${fmtDateTime(n.starts_at)}${n.expected_end ? ` until ${sameDay(n.starts_at, n.expected_end) ? fmtTime(n.expected_end) : fmtDateTime(n.expected_end)}` : ""}`;
        return (
          <div
            key={n.id}
            role="status"
            className={cn("flex gap-3 rounded-2xl border p-4", live ? "border-warning/40 bg-warning-50" : "border-line-soft bg-surface")}
          >
            <Icon className={cn("mt-0.5 size-5 shrink-0", live ? "text-warning" : "text-ink-2")} aria-hidden />
            <div className="min-w-0">
              <p className="font-semibold">{n.title}</p>
              <p className="text-[13.5px] text-ink-2">{when}</p>
              {n.message && <p className="mt-1 text-[14.5px] text-ink">{n.message}</p>}
              <p className="mt-1.5 text-[12.5px] text-ink-2">
                {live ? "We'll text you as soon as it's fixed - no need to report it." : "We'll remind you by text before it starts."} No data? Text ALERTS.
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
