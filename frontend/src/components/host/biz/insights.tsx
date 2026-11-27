"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { format, parseISO, startOfWeek, subDays } from "date-fns";
import {
  Banknote, BedDouble, Bot, CalendarClock, CalendarRange, Coins, Hourglass, Landmark, Percent, Receipt, Smartphone, Sparkles, Timer, TrendingUp, Undo2,
  type LucideIcon,
} from "lucide-react";
import * as React from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Line, LineChart, Pie, PieChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { ErrorBlock, PageHeader } from "@/components/host/common";
import { usePayOptions } from "@/components/providers";
import { Skeleton } from "@/components/ui/misc";
import { get } from "@/lib/api";
import { CHANNEL_COLOR, CHANNEL_LABEL, fmtDate, kes, plural } from "@/lib/format";
import { cn } from "@/lib/utils";

import type { ForwardWeek, InsightsResponse, Kpis, SeriesPoint } from "./types";
import { Callout, Segmented, compactKes, pctChange } from "./ui";

type Range = 7 | 30 | 90 | 365;
const RANGES: { value: Range; label: string }[] = [
  { value: 7, label: "7 days" },
  { value: 30, label: "30 days" },
  { value: 90, label: "90 days" },
  { value: 365, label: "12 months" },
];

const PHONE = ["ussd", "sms", "voice"];
const CHANNEL_ORDER = Object.keys(CHANNEL_LABEL);
const METHOD: Record<string, { label: string; color: string }> = {
  mpesa: { label: "M-Pesa", color: "#0a7f3f" },
  card: { label: "Card", color: "#1e40af" },
  cash: { label: "Cash", color: "#6a6a6a" },
  bank: { label: "Bank transfer", color: "#b45309" },
};
const AXIS = { fontSize: 12, fill: "#6a6a6a" };

// ---------- metric cards ----------

type Good = "up" | "down" | "neutral";

function Delta({ value, unit, good }: { value: number | null; unit: "%" | " pts"; good: Good }) {
  if (value === null || !Number.isFinite(value)) return <span className="text-ink-3">no prior data</span>;
  if (value === 0) return <span className="font-semibold text-ink-2">— no change</span>;
  const positive = good === "neutral" ? null : (value > 0) === (good === "up");
  return (
    <span className={cn("font-semibold", positive === null ? "text-ink-2" : positive ? "text-success" : "text-danger")}>
      {value > 0 ? "▲" : "▼"} {Math.abs(value)}
      {unit}
    </span>
  );
}

interface Metric {
  label: string;
  value: React.ReactNode;
  icon: LucideIcon;
  delta: number | null;
  unit: "%" | " pts";
  good: Good;
  hint?: string;
}

function MetricCard({ m, big }: { m: Metric; big?: boolean }) {
  return (
    <div className="rounded-2xl border border-line-soft bg-white p-5">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[13px] font-semibold text-ink-2">{m.label}</p>
        <span className={cn("grid size-8 shrink-0 place-items-center rounded-full", big ? "bg-brand-50 text-brand-600" : "bg-surface text-ink-2")}>
          <m.icon className="size-4" />
        </span>
      </div>
      <p className={cn("mt-2 leading-none font-bold tracking-tight whitespace-nowrap tabular-nums", big ? "text-[30px]" : "text-[20px]")}>{m.value}</p>
      <p className="mt-2 flex flex-wrap items-center gap-x-1.5 text-[12.5px] text-ink-2">
        <Delta value={m.delta} unit={m.unit} good={m.good} />
        <span className="text-ink-3">vs previous</span>
      </p>
      {m.hint && <p className="mt-1 text-[12px] text-ink-3">{m.hint}</p>}
    </div>
  );
}

function metrics(k: Kpis, p: Kpis): { primary: Metric[]; secondary: Metric[] } {
  const pts = (a: number | null, b: number | null) => (a === null || b === null ? null : a - b);
  const prevNote = (v: string) => `Previous period: ${v}`;
  return {
    primary: [
      { label: "Occupancy", value: `${k.occupancy}%`, icon: BedDouble, delta: pts(k.occupancy, p.occupancy), unit: " pts", good: "up", hint: `${k.booked_nights} of ${k.available_nights} nights sold` },
      { label: "Average daily rate", value: kes(k.adr), icon: Coins, delta: pctChange(k.adr, p.adr), unit: "%", good: "up", hint: "Room revenue ÷ nights sold" },
      { label: "RevPAR", value: kes(k.revpar), icon: TrendingUp, delta: pctChange(k.revpar, p.revpar), unit: "%", good: "up", hint: "Room revenue ÷ nights available" },
      { label: "Room revenue", value: kes(k.room_revenue), icon: Banknote, delta: pctChange(k.room_revenue, p.room_revenue), unit: "%", good: "up", hint: "Earned on nights in this period" },
    ],
    secondary: [
      { label: "Cash collected", value: kes(k.collected), icon: Receipt, delta: pctChange(k.collected, p.collected), unit: "%", good: "up", hint: k.refunded ? `After ${kes(k.refunded)} refunds` : "Net of refunds" },
      { label: "New bookings", value: k.bookings, icon: CalendarRange, delta: pctChange(k.bookings, p.bookings), unit: "%", good: "up" },
      { label: "Avg lead time", value: `${k.lead_time_days} days`, icon: CalendarClock, delta: pctChange(k.lead_time_days, p.lead_time_days), unit: "%", good: "neutral", hint: prevNote(`${p.lead_time_days} days`) },
      { label: "Avg stay", value: plural(k.avg_stay_nights, "night"), icon: Hourglass, delta: pctChange(k.avg_stay_nights, p.avg_stay_nights), unit: "%", good: "up" },
      { label: "Cancellation rate", value: `${k.cancellation_rate}%`, icon: Undo2, delta: pts(k.cancellation_rate, p.cancellation_rate), unit: " pts", good: "down" },
      { label: "Direct bookings", value: `${k.direct_share}%`, icon: Percent, delta: pts(k.direct_share, p.direct_share), unit: " pts", good: "up", hint: "No Airbnb/Booking.com commission" },
      { label: "Add-on revenue", value: kes(k.addon_revenue), icon: Sparkles, delta: pctChange(k.addon_revenue, p.addon_revenue), unit: "%", good: "up", hint: "Breakfast, pickups, late checkout…" },
      { label: "Tourism levy due", value: kes(k.levy_due), icon: Landmark, delta: pctChange(k.levy_due, p.levy_due), unit: "%", good: "neutral", hint: "Collected in every quote" },
      {
        label: "Median reply time",
        value: k.response_minutes === null ? "—" : k.response_minutes < 60 ? `${k.response_minutes} min` : `${(k.response_minutes / 60).toFixed(1)} h`,
        icon: Timer,
        delta: pctChange(k.response_minutes, p.response_minutes),
        unit: "%",
        good: "down",
        hint: "When Ask Amina relays a question to you",
      },
      { label: "Auto-answered", value: `${k.auto_answer_rate}%`, icon: Bot, delta: pts(k.auto_answer_rate, p.auto_answer_rate), unit: " pts", good: "up", hint: `${plural(k.messages_in, "guest message")} this period` },
    ],
  };
}

// ---------- tooltips ----------

function TipBox({ title, rows }: { title: string; rows: { label: string; value: string; color?: string }[] }) {
  return (
    <div className="min-w-44 rounded-xl border border-line-soft bg-white px-3.5 py-2.5 text-[12.5px] shadow-float">
      <p className="mb-1.5 font-semibold text-ink">{title}</p>
      {rows.map((r) => (
        <p key={r.label} className="flex items-center justify-between gap-4 py-0.5">
          <span className="flex items-center gap-1.5 text-ink-2">
            {r.color && <span className="size-2 rounded-full" style={{ background: r.color }} />}
            {r.label}
          </span>
          <span className="font-semibold text-ink tabular-nums">{r.value}</span>
        </p>
      ))}
    </div>
  );
}

function firstPoint<T>(p: { active?: boolean; payload?: ReadonlyArray<{ payload?: unknown }> }): T | null {
  return p.active && p.payload?.length ? (p.payload[0].payload as T) : null;
}

// ---------- page ----------

export function InsightsPage() {
  const [days, setDays] = React.useState<Range>(30);
  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ["host", "insights", days],
    queryFn: () => get<InsightsResponse>(`/api/host/insights?days=${days}`),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <PageHeader
        title="Insights"
        subtitle={
          data
            ? `${fmtDate(data.kpis.period.start, "d MMM yyyy")} – ${fmtDate(subDays(parseISO(data.kpis.period.end), 1), "d MMM yyyy")}, compared with the ${days === 365 ? "12 months" : `${days} days`} before`
            : "How your homes are doing — occupancy, revenue and every booking channel."
        }
        actions={<Segmented<Range> label="Date range" value={days} onChange={setDays} options={RANGES} />}
      />
      {error ? (
        <ErrorBlock error={error} retry={refetch} />
      ) : isLoading || !data ? (
        <InsightsSkeleton />
      ) : (
        <div className={cn("space-y-6 transition-opacity", isFetching && "opacity-60")}>
          <Dashboard data={data} />
        </div>
      )}
    </>
  );
}

function InsightsSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-36 rounded-2xl" />
        ))}
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Skeleton className="h-80 rounded-2xl" />
        <Skeleton className="h-80 rounded-2xl" />
      </div>
    </div>
  );
}

function ChartCard({ title, subtitle, children, className, right }: { title: string; subtitle?: React.ReactNode; children: React.ReactNode; className?: string; right?: React.ReactNode }) {
  return (
    <section className={cn("rounded-2xl border border-line-soft bg-white p-5", className)}>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-[15px] font-bold">{title}</h2>
          {subtitle && <p className="mt-0.5 text-[13px] text-ink-2">{subtitle}</p>}
        </div>
        {right}
      </div>
      {children}
    </section>
  );
}

function Dashboard({ data }: { data: InsightsResponse }) {
  const { kpis: k, previous: p, series, forward, days } = data;
  const m = metrics(k, p);
  const gradient = React.useId().replace(/[^a-zA-Z0-9]/g, "");
  const { mpesa } = usePayOptions();
  const tick = (d: string) => format(parseISO(d), days > 120 ? "MMM" : "d MMM");

  const channels = CHANNEL_ORDER.filter((c) => k.by_channel[c] || series.some((s) => s.bookings[c])).concat(
    Object.keys(k.by_channel).filter((c) => !CHANNEL_ORDER.includes(c)),
  );
  const buckets = bucketBookings(series, days);
  const totalBookings = channels.reduce((s, c) => s + (k.by_channel[c]?.bookings ?? 0), 0);
  const totalRevenue = channels.reduce((s, c) => s + (k.by_channel[c]?.revenue ?? 0), 0);
  const phone = PHONE.reduce((acc, c) => ({ n: acc.n + (k.by_channel[c]?.bookings ?? 0), kes: acc.kes + (k.by_channel[c]?.revenue ?? 0) }), { n: 0, kes: 0 });
  const donut = channels.filter((c) => k.by_channel[c]?.bookings).map((c) => ({ name: CHANNEL_LABEL[c] ?? c, value: k.by_channel[c].bookings, fill: CHANNEL_COLOR[c] ?? "#929292" }));
  const methods = Object.entries(k.by_method).sort((a, b) => b[1] - a[1]);
  const methodTotal = methods.reduce((s, [, v]) => s + v, 0);
  const mpesaListed = mpesa || methods.some(([key]) => key === "mpesa"); // with M-Pesa off, older M-Pesa payments may still be listed
  const pace = forward.map((w) => ({ ...w, ok: w.occupancy >= 30 ? w.occupancy : null, low: w.occupancy < 30 ? w.occupancy : null }));
  const lowWeeks = forward.filter((w) => w.occupancy < 30).length;

  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {m.primary.map((x) => (
          <MetricCard key={x.label} m={x} big />
        ))}
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {m.secondary.map((x) => (
          <MetricCard key={x.label} m={x} />
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <ChartCard title="Room revenue" subtitle={`${kes(k.room_revenue)} earned · ${kes(k.adr)} average a night`}>
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={series} margin={{ top: 6, right: 6, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id={`rev${gradient}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#e8553e" stopOpacity={0.28} />
                  <stop offset="100%" stopColor="#e8553e" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} stroke="#ebebeb" />
              <XAxis dataKey="date" tickFormatter={tick} tickLine={false} axisLine={false} minTickGap={28} tick={AXIS} />
              <YAxis tickFormatter={(v: number) => compactKes(v)} tickLine={false} axisLine={false} width={44} tick={AXIS} />
              <Tooltip
                cursor={{ stroke: "#dddddd" }}
                content={(tp) => {
                  const pt = firstPoint<SeriesPoint>(tp);
                  return pt ? <TipBox title={fmtDate(pt.date, "EEE d MMM yyyy")} rows={[{ label: "Room revenue", value: kes(pt.revenue), color: "#e8553e" }, { label: "Occupancy", value: `${pt.occupancy}%` }]} /> : null;
                }}
              />
              <Area type="monotone" dataKey="revenue" stroke="#e8553e" strokeWidth={2} fill={`url(#rev${gradient})`} activeDot={{ r: 4, strokeWidth: 0 }} />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Occupancy" subtitle={`${k.occupancy}% across all listed homes · nights sold on Airbnb/Booking.com included`}>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={series} margin={{ top: 6, right: 6, left: 0, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="#ebebeb" />
              <XAxis dataKey="date" tickFormatter={tick} tickLine={false} axisLine={false} minTickGap={28} tick={AXIS} />
              <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tickFormatter={(v: number) => `${v}%`} tickLine={false} axisLine={false} width={44} tick={AXIS} />
              <ReferenceLine y={k.occupancy} stroke="#929292" strokeDasharray="4 4" label={{ value: `avg ${k.occupancy}%`, position: "insideTopRight", fontSize: 11, fill: "#6a6a6a" }} />
              <Tooltip
                cursor={{ stroke: "#dddddd" }}
                content={(tp) => {
                  const pt = firstPoint<SeriesPoint>(tp);
                  return pt ? <TipBox title={fmtDate(pt.date, "EEE d MMM yyyy")} rows={[{ label: "Occupancy", value: `${pt.occupancy}%`, color: "#0e8388" }]} /> : null;
                }}
              />
              <Line type="monotone" dataKey="occupancy" stroke="#0e8388" strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 0 }} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <ChartCard
          title="New bookings by channel"
          subtitle={`Per ${buckets.mode} · ${plural(totalBookings, "booking")}`}
          right={<ChannelLegend channels={channels} />}
        >
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={buckets.rows} margin={{ top: 6, right: 6, left: 0, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="#ebebeb" />
              <XAxis dataKey="label" tickLine={false} axisLine={false} minTickGap={16} tick={AXIS} />
              <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={32} tick={AXIS} />
              <Tooltip
                cursor={{ fill: "rgba(0,0,0,0.04)" }}
                content={(tp) => {
                  const pt = firstPoint<BucketRow>(tp);
                  if (!pt) return null;
                  const rows = channels.filter((c) => Number(pt[c] ?? 0) > 0).map((c) => ({ label: CHANNEL_LABEL[c] ?? c, value: String(pt[c]), color: CHANNEL_COLOR[c] }));
                  return <TipBox title={String(pt.title)} rows={rows.length ? rows : [{ label: "No new bookings", value: "" }]} />;
                }}
              />
              {channels.map((c, i) => (
                <Bar key={c} dataKey={c} stackId="ch" fill={CHANNEL_COLOR[c] ?? "#929292"} radius={i === channels.length - 1 ? [4, 4, 0, 0] : 0} maxBarSize={36} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Channel mix" subtitle="Share of new bookings">
          {donut.length === 0 ? (
            <p className="py-16 text-center text-sm text-ink-2">No bookings in this period.</p>
          ) : (
            <div className="relative">
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie data={donut} dataKey="value" nameKey="name" innerRadius={62} outerRadius={92} paddingAngle={2} stroke="none" />
                  <Tooltip
                    content={(tp) => {
                      const pt = firstPoint<{ name: string; value: number; fill: string }>(tp);
                      return pt ? <TipBox title={pt.name} rows={[{ label: "Bookings", value: `${pt.value} (${Math.round((pt.value / totalBookings) * 100)}%)`, color: pt.fill }]} /> : null;
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="pointer-events-none absolute inset-0 grid place-items-center">
                <div className="text-center">
                  <p className="text-2xl font-bold tabular-nums">{totalBookings}</p>
                  <p className="text-[12px] text-ink-2">bookings</p>
                </div>
              </div>
            </div>
          )}
        </ChartCard>
      </div>

      <section className="overflow-hidden rounded-2xl border border-line-soft bg-white">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line-soft px-5 py-4">
          <div>
            <h2 className="text-[15px] font-bold">Bookings by channel</h2>
            <p className="mt-0.5 text-[13px] text-ink-2">One platform, four doors — web, USSD, SMS and voice all land in the same calendar.</p>
          </div>
        </header>
        {phone.n > 0 && (
          <div className="px-5 pt-4">
            <Callout tone="info" icon={<Smartphone className="size-[18px]" />} title={`${plural(phone.n, "booking")} · ${kes(phone.kes)} came by USSD, SMS or voice`}>
              That&apos;s {totalBookings ? Math.round((phone.n / totalBookings) * 100) : 0}% of new bookings — guests the website alone would have missed.{" "}
              {mpesa ? "No smartphone, data or app needed: a basic phone and M-Pesa are enough." : "No smartphone, data or app needed to book: a basic phone is enough."}
            </Callout>
          </div>
        )}
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-left text-sm">
            <thead>
              <tr className="border-b border-line-soft text-[12px] font-semibold tracking-wide text-ink-2 uppercase">
                <th className="px-5 py-3">Channel</th>
                <th className="px-4 py-3 text-right">Bookings</th>
                <th className="px-4 py-3 text-right">Revenue</th>
                <th className="w-[34%] px-5 py-3">Share of bookings</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line-soft">
              {channels.map((c) => {
                const row = k.by_channel[c] ?? { bookings: 0, revenue: 0 };
                const share = totalBookings ? Math.round((row.bookings / totalBookings) * 100) : 0;
                const isPhone = PHONE.includes(c);
                return (
                  <tr key={c} className={cn(isPhone && "bg-ocean-50/40")}>
                    <td className="px-5 py-3">
                      <span className="flex items-center gap-2 font-semibold">
                        <span className="size-2.5 rounded-full" style={{ background: CHANNEL_COLOR[c] ?? "#929292" }} />
                        {CHANNEL_LABEL[c] ?? c}
                        {isPhone && <span className="rounded-full bg-ocean-100 px-2 py-0.5 text-[11px] font-bold text-ocean-700">Any phone</span>}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">{row.bookings}</td>
                    <td className="px-4 py-3 text-right font-semibold tabular-nums">{kes(row.revenue)}</td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-3">
                        <div className="h-2 flex-1 overflow-hidden rounded-full bg-line-soft">
                          <div className="h-full rounded-full" style={{ width: `${share}%`, background: CHANNEL_COLOR[c] ?? "#929292" }} />
                        </div>
                        <span className="w-10 text-right text-[13px] text-ink-2 tabular-nums">{share}%</span>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {channels.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-5 py-10 text-center text-ink-2">
                    No bookings in this period.
                  </td>
                </tr>
              )}
            </tbody>
            {channels.length > 0 && (
              <tfoot>
                <tr className="border-t border-line-soft font-semibold">
                  <td className="px-5 py-3">Total</td>
                  <td className="px-4 py-3 text-right tabular-nums">{totalBookings}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{kes(totalRevenue)}</td>
                  <td className="px-5 py-3 text-[13px] font-normal text-ink-2">Booking value incl. fees, add-ons & levy</td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <ChartCard
          title="On the books — next 8 weeks"
          subtitle={lowWeeks ? `${plural(lowWeeks, "week")} under 30% — a last-minute price rule or a broadcast to past guests can help` : "Occupancy already confirmed for the weeks ahead"}
        >
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={pace} margin={{ top: 6, right: 6, left: 0, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="#ebebeb" />
              <XAxis dataKey="week_start" tickFormatter={(d: string) => format(parseISO(d), "d MMM")} tickLine={false} axisLine={false} tick={AXIS} />
              <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tickFormatter={(v: number) => `${v}%`} tickLine={false} axisLine={false} width={44} tick={AXIS} />
              <Tooltip
                cursor={{ fill: "rgba(0,0,0,0.04)" }}
                content={(tp) => {
                  const pt = firstPoint<ForwardWeek>(tp);
                  return pt ? (
                    <TipBox
                      title={`Week of ${fmtDate(pt.week_start, "d MMM")}`}
                      rows={[
                        { label: "Occupancy", value: `${pt.occupancy}%`, color: pt.occupancy < 30 ? "#e8553e" : "#0e8388" },
                        { label: "Nights booked", value: `${pt.booked_nights} / ${pt.available_nights}` },
                      ]}
                    />
                  ) : null;
                }}
              />
              <Bar dataKey="ok" stackId="pace" fill="#0e8388" radius={[4, 4, 0, 0]} maxBarSize={48} />
              <Bar dataKey="low" stackId="pace" fill="#e8553e" radius={[4, 4, 0, 0]} maxBarSize={48} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="How guests paid" subtitle={`${kes(methodTotal)} received this period`}>
          {methods.length === 0 ? (
            <p className="py-12 text-center text-sm text-ink-2">No payments in this period.</p>
          ) : (
            <>
              <div className="flex h-3 overflow-hidden rounded-full bg-line-soft">
                {methods.map(([key, v]) => (
                  <div key={key} style={{ width: `${(v / methodTotal) * 100}%`, background: METHOD[key]?.color ?? "#929292" }} title={METHOD[key]?.label ?? key} />
                ))}
              </div>
              <ul className="mt-4 space-y-3">
                {methods.map(([key, v]) => (
                  <li key={key} className="flex items-center justify-between gap-3 text-[14px]">
                    <span className="flex items-center gap-2">
                      <span className="size-2.5 rounded-full" style={{ background: METHOD[key]?.color ?? "#929292" }} />
                      {METHOD[key]?.label ?? key}
                    </span>
                    <span className="text-right">
                      <span className="font-semibold tabular-nums">{kes(v)}</span>
                      <span className="ml-2 text-[12.5px] text-ink-2 tabular-nums">{Math.round((v / methodTotal) * 100)}%</span>
                    </span>
                  </li>
                ))}
              </ul>
              <p className="mt-4 text-[12.5px] text-ink-2">Only payments confirmed by {mpesaListed ? "an M-Pesa or card" : "a card"} callback count — never a screenshot.</p>
            </>
          )}
        </ChartCard>
      </div>
    </>
  );
}

function ChannelLegend({ channels }: { channels: string[] }) {
  return (
    <ul className="flex flex-wrap gap-x-3 gap-y-1">
      {channels.map((c) => (
        <li key={c} className="flex items-center gap-1.5 text-[12px] text-ink-2">
          <span className="size-2 rounded-full" style={{ background: CHANNEL_COLOR[c] ?? "#929292" }} />
          {CHANNEL_LABEL[c] ?? c}
        </li>
      ))}
    </ul>
  );
}

type BucketRow = Record<string, string | number>;

function bucketBookings(series: SeriesPoint[], days: number): { mode: "day" | "week" | "month"; rows: BucketRow[] } {
  const mode = days <= 31 ? "day" : days <= 120 ? "week" : "month";
  const rows = new Map<string, BucketRow>();
  for (const pt of series) {
    const d = parseISO(pt.date);
    const start = mode === "week" ? startOfWeek(d, { weekStartsOn: 1 }) : d;
    const key = mode === "month" ? format(d, "yyyy-MM") : format(start, "yyyy-MM-dd");
    const row = rows.get(key) ?? {
      key,
      label: mode === "month" ? format(d, "MMM") : format(start, "d MMM"),
      title: mode === "day" ? format(d, "EEE d MMM") : mode === "week" ? `Week of ${format(start, "d MMM")}` : format(d, "MMMM yyyy"),
    };
    for (const [ch, n] of Object.entries(pt.bookings)) row[ch] = Number(row[ch] ?? 0) + n;
    rows.set(key, row);
  }
  return { mode, rows: [...rows.values()] };
}
