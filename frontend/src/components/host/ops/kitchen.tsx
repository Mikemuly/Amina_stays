"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ChefHat, ChevronLeft, ChevronRight, Leaf, MessageSquareText, Printer, Send, Users } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { ErrorBlock, PageHeader } from "@/components/host/common";
import { Button } from "@/components/ui/button";
import { Badge, EmptyState, Skeleton, Spinner } from "@/components/ui/misc";
import { get, post, qs } from "@/lib/api";
import { fmtDate, fmtLong, plural } from "@/lib/format";
import { cn } from "@/lib/utils";

import { Segmented } from "./bits";
import { addDaysISO, kenyaDate, kenyaHour, shortStyle, smsSegments, useHostAction, useNow } from "./lib";
import type { BreakfastRow, KitchenData } from "./types";

const PRINT_CSS = `
@media print {
  @page { margin: 14mm; }
  body * { visibility: hidden !important; }
  #kitchen-sheet, #kitchen-sheet * { visibility: visible !important; }
  #kitchen-sheet { position: absolute; inset: 0 auto auto 0; width: 100%; }
}`;

const dietaryList = (d: string) => d.split(/[,;]/).map((x) => x.trim()).filter(Boolean);

export function KitchenView() {
  const now = useNow(60_000);
  const today = now ? kenyaDate(now) : "";
  const tomorrow = today ? addDaysISO(today, 1) : "";
  const [picked, setPicked] = React.useState<string | null>(null);
  // After 11:00 the kitchen is planning tomorrow's breakfasts.
  const date = picked ?? (now && kenyaHour(now) >= 11 ? tomorrow : today);

  const q = useQuery({
    queryKey: ["host", "ops", "kitchen", date],
    queryFn: () => get<KitchenData>(`/api/host/kitchen${qs({ date })}`),
    enabled: Boolean(date),
    placeholderData: keepPreviousData,
    refetchInterval: 30_000,
  });
  const send = useHostAction(() => post<{ sent_to: string[] }>("/api/host/kitchen", { date }), {
    success: (r) => `Breakfast sheet sent to ${r.sent_to.join(", ")} by SMS`,
  });
  const data = q.data;
  const rows = data?.rows ?? [];
  const label = date === today ? "Today" : date === tomorrow ? "Tomorrow" : date ? fmtDate(date, "EEE d MMM") : "";

  return (
    <div>
      {/* Rendered in place (not hoisted) so the print rules disappear when leaving this page. */}
      <style>{PRINT_CSS}</style>
      <PageHeader
        title="Breakfast & kitchen"
        subtitle="The cook's sheet for each morning, built from what guests chose on the web, by SMS or USSD."
        actions={
          <>
            <Button variant="soft" onClick={() => window.print()} disabled={!rows.length}>
              <Printer className="size-4" /> Print
            </Button>
            <Button variant="dark" loading={send.isPending} disabled={!rows.length} onClick={() => send.mutate()}>
              <Send className="size-4" /> Send to cook by SMS
            </Button>
          </>
        }
      />

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <Segmented
          label="Morning"
          value={date === today ? "today" : date === tomorrow ? "tomorrow" : "other"}
          onChange={(v) => v !== "other" && setPicked(v === "today" ? today : tomorrow)}
          options={[
            { value: "today", label: "Today" },
            { value: "tomorrow", label: "Tomorrow" },
          ]}
        />
        <div className="flex items-center rounded-full border border-line bg-white p-0.5">
          <Button variant="ghost" size="icon-sm" aria-label="Previous morning" disabled={!date} onClick={() => setPicked(addDaysISO(date, -1))}>
            <ChevronLeft className="size-4" />
          </Button>
          <input
            type="date"
            aria-label="Pick a morning"
            value={date}
            onChange={(e) => e.target.value && setPicked(e.target.value)}
            className="h-8 rounded-full bg-transparent px-2 text-sm font-semibold outline-none focus-visible:ring-2 focus-visible:ring-ink"
          />
          <Button variant="ghost" size="icon-sm" aria-label="Next morning" disabled={!date} onClick={() => setPicked(addDaysISO(date, 1))}>
            <ChevronRight className="size-4" />
          </Button>
        </div>
        {q.isFetching && data && <Spinner className="size-4" />}
      </div>

      {q.error && !data ? (
        <ErrorBlock error={q.error} retry={() => q.refetch()} />
      ) : !data ? (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-28 rounded-2xl" />
            ))}
          </div>
          <Skeleton className="h-72 rounded-2xl" />
        </div>
      ) : rows.length === 0 ? (
        <EmptyState icon={<ChefHat className="size-5" />} title={`No breakfasts for ${label.toLowerCase() === "today" || label.toLowerCase() === "tomorrow" ? label.toLowerCase() : label}`}>
          Guests add breakfast when they book, from their trip page, or by replying BREAKFAST to any SMS. The sheet goes to the cook automatically at 6pm the
          evening before.
        </EmptyState>
      ) : (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div id="kitchen-sheet" className={cn("min-w-0 space-y-4", q.isPlaceholderData && "opacity-70")}>
            <div className="hidden print:block">
              <h1 className="text-2xl font-bold">Breakfast sheet · {fmtLong(data.date)}</h1>
              <p className="mt-1 text-sm">Amina Stays · {plural(data.people, "person", "people")}</p>
            </div>
            <Summary rows={rows} people={data.people} />
            <Sheet rows={rows} />
          </div>
          <SmsPreview text={data.text} date={data.date} />
        </div>
      )}
    </div>
  );
}

function Summary({ rows, people }: { rows: BreakfastRow[]; people: number }) {
  const styles = new Map<string, number>();
  rows.forEach((r) => styles.set(shortStyle(r.style_label), (styles.get(shortStyle(r.style_label)) ?? 0) + r.people));
  const dietary = rows.filter((r) => r.dietary).length;
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      <div className="rounded-2xl border border-line-soft bg-white p-5">
        <p className="flex items-center gap-2 text-[13px] font-semibold text-ink-2">
          <Users className="size-4" /> People
        </p>
        <p className="mt-2 text-[32px] leading-none font-bold tabular-nums">{people}</p>
        <p className="mt-2 text-[13px] text-ink-2">across {plural(rows.length, "home")}</p>
      </div>
      <div className="rounded-2xl border border-line-soft bg-white p-5 sm:col-span-2">
        <p className="flex items-center gap-2 text-[13px] font-semibold text-ink-2">
          <ChefHat className="size-4" /> To prepare
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {[...styles.entries()].map(([style, n]) => (
            <span key={style} className="inline-flex items-center gap-2 rounded-xl bg-surface px-3 py-2 text-sm font-semibold">
              <span className="grid min-w-7 place-items-center rounded-lg bg-white px-1.5 py-0.5 text-base tabular-nums shadow-sm">{n}</span>
              {style}
            </span>
          ))}
        </div>
        <p className={cn("mt-3 flex items-center gap-1.5 text-[13px]", dietary ? "font-semibold text-warning" : "text-ink-2")}>
          <Leaf className="size-3.5" /> {dietary ? `${plural(dietary, "home")} with dietary needs — see below` : "No dietary needs noted"}
        </p>
      </div>
    </div>
  );
}

function Sheet({ rows }: { rows: BreakfastRow[] }) {
  const groups = new Map<string, BreakfastRow[]>();
  rows.forEach((r) => groups.set(r.time || "08:00", [...(groups.get(r.time || "08:00") ?? []), r]));
  const times = [...groups.keys()].sort();
  return (
    <div className="overflow-hidden rounded-2xl border border-line-soft bg-white">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead>
            <tr className="border-b border-line-soft text-[12px] font-semibold tracking-wide text-ink-2 uppercase">
              <th className="px-5 py-3">Home</th>
              <th className="px-4 py-3">Guest</th>
              <th className="px-4 py-3 text-center">People</th>
              <th className="px-4 py-3">Breakfast</th>
              <th className="px-4 py-3">Dietary</th>
              <th className="px-5 py-3">Notes</th>
            </tr>
          </thead>
          {times.map((time) => {
            const g = groups.get(time)!;
            const people = g.reduce((n, r) => n + r.people, 0);
            return (
              <tbody key={time} className="divide-y divide-line-soft border-b border-line-soft last:border-b-0">
                <tr className="bg-surface/70">
                  <td colSpan={6} className="px-5 py-2">
                    <span className="font-mono text-[15px] font-bold tabular-nums">{time}</span>
                    <span className="ml-3 text-[13px] text-ink-2">
                      {plural(g.length, "home")} · {plural(people, "person", "people")}
                    </span>
                  </td>
                </tr>
                {g.map((r) => (
                  <tr key={r.ref} className="align-top">
                    <td className="px-5 py-3 font-semibold">{r.unit}</td>
                    <td className="px-4 py-3">
                      <span className="block">{r.guest}</span>
                      <Link href={`/host/reservations/${r.ref}`} className="font-mono text-xs text-ink-3 hover:text-ink hover:underline print:no-underline">
                        {r.ref}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-center text-base font-bold tabular-nums">{r.people}</td>
                    <td className="px-4 py-3">
                      <span className="block font-medium">{shortStyle(r.style_label)}</span>
                      {r.style_label.includes("(") && <span className="block text-xs text-ink-2">{r.style_label.slice(r.style_label.indexOf("(") + 1, -1)}</span>}
                    </td>
                    <td className="px-4 py-3">
                      {r.dietary ? (
                        <div className="flex flex-wrap gap-1">
                          {dietaryList(r.dietary).map((d) => (
                            <Badge key={d} tone="warning">
                              {d}
                            </Badge>
                          ))}
                        </div>
                      ) : (
                        <span className="text-ink-3">—</span>
                      )}
                    </td>
                    <td className="px-5 py-3 text-[13px] text-ink-2">{r.notes || <span className="text-ink-3">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            );
          })}
        </table>
      </div>
    </div>
  );
}

function SmsPreview({ text, date }: { text: string | null; date: string }) {
  return (
    <aside className="space-y-4 print:hidden">
      <section className="rounded-2xl border border-line-soft bg-white">
        <div className="border-b border-line-soft px-5 py-3.5">
          <h2 className="flex items-center gap-2 text-[15px] font-bold">
            <MessageSquareText className="size-4 text-ink-2" /> What the cook receives
          </h2>
          <p className="mt-0.5 text-[13px] text-ink-2">One SMS — readable on any phone.</p>
        </div>
        <div className="bg-surface/60 px-4 py-4">
          <div className="rounded-2xl rounded-bl-md bg-white px-3.5 py-2.5 text-[13px] leading-relaxed whitespace-pre-wrap shadow-sm ring-1 ring-line-soft">
            {text || "No breakfasts booked."}
          </div>
          {text && <p className="mt-2 text-right text-[11px] text-ink-3 tabular-nums">{plural(smsSegments(text), "SMS", "SMS")} · {text.length} characters</p>}
        </div>
        <p className="px-5 py-3.5 text-[13px] text-ink-2">
          Sent automatically at <span className="font-semibold text-ink">6pm</span> the evening before {fmtDate(date, "EEE d MMM")}. Use{" "}
          <span className="font-semibold text-ink">Send to cook</span> after a late change.
        </p>
      </section>
    </aside>
  );
}
