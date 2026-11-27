"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { addMonths, differenceInCalendarDays, format, parseISO, startOfMonth, subMonths } from "date-fns";
import { ArrowRight, CalendarClock, CircleAlert, CircleCheck, Download, FileSpreadsheet, Info, TriangleAlert } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { ErrorBlock, LoadingBlock, Table, Td, Tr } from "@/components/host/common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge, Skeleton } from "@/components/ui/misc";
import { get, qs } from "@/lib/api";
import { fmtDate, fmtDateTime, iso, kes, plural } from "@/lib/format";
import { cn, flag } from "@/lib/utils";

import { useHostSettings } from "./queries";
import type { HostSettings, RegisterResponse, TraReturn } from "./types";
import { Callout, Field, StatTile, TableCard, countryName, downloadCsv, reservationHref, toCsv } from "./ui";

const ID_TYPES: Record<string, string> = { national_id: "National ID", passport: "Passport", alien_id: "Alien ID", driving_licence: "Driving licence" };

// ---------- guest register ----------

export function RegisterTab() {
  const [from, setFrom] = React.useState(() => iso(startOfMonth(new Date())));
  const [to, setTo] = React.useState(() => iso(new Date()));
  const params = { from, to };
  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ["host", "register", from, to],
    queryFn: () => get<RegisterResponse>(`/api/host/compliance/register${qs(params)}`),
    placeholderData: keepPreviousData,
    enabled: !!from && !!to,
  });
  const rows = data?.rows ?? [];
  const stays = new Set(rows.map((r) => r.ref)).size;
  const csv = `/api/host/compliance/register${qs({ ...params, export: "csv" })}`;
  const download = (e: React.MouseEvent) => {
    e.preventDefault();
    downloadCsv(csv, `guest-register-${from}-${to}.csv`, () =>
      toCsv([
        ["Ref", "Home", "Address", "Name", "Lead guest", "Minor", "ID type", "ID (last 4)", "Nationality", "Phone", "Check-in", "Check-out", "Arrived", "Left", "Vehicle"],
        ...rows.map((r) => [
          r.ref, r.unit, r.address, r.name, r.lead_guest ? "yes" : "", r.minor ? "yes" : "", r.id_type, r.id_last4, r.nationality, r.phone, r.check_in,
          r.check_out, r.arrived_at ?? "", r.left_at ?? "", r.vehicle,
        ]),
      ]),
    );
  };

  return (
    <div className="space-y-5">
      <div className="grid gap-4 lg:grid-cols-2">
        <Callout tone="trust" title="Tourism Enterprises Regulations 2025, r.26">
          Every guest staying the night goes in the register — name, nationality, ID or passport and dates — kept for 5 years and shown to TRA or the
          police on request. ID numbers are encrypted; only the last four characters ever appear here.
        </Callout>
        <Callout tone="info" title="PSRA visitor-log directive">
          Your gate guard keeps the visitor and vehicle log. At 07:30 they get today&apos;s arrivals by SMS — names, guest count, car plates and ETA — so
          nobody has to photocopy IDs at the gate.
        </Callout>
      </div>

      <TableCard
        title="Guest register"
        description={data ? `${plural(rows.length, "guest")} across ${plural(stays, "stay")} · ${fmtDate(data.from, "d MMM yyyy")} – ${fmtDate(data.to, "d MMM yyyy")}` : undefined}
        action={
          <div className="flex flex-wrap items-end gap-2">
            <Field label="From" className="[&_label]:mb-1 [&_label]:text-[12px]">
              <Input type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} className="h-9 w-40 text-sm" />
            </Field>
            <Field label="To" className="[&_label]:mb-1 [&_label]:text-[12px]">
              <Input type="date" value={to} min={from} onChange={(e) => setTo(e.target.value)} className="h-9 w-40 text-sm" />
            </Field>
            <Button asChild variant="dark" size="sm" className="h-9">
              <a href={csv} download onClick={download}>
                <Download className="size-4" /> Download CSV
              </a>
            </Button>
          </div>
        }
      >
        {data && data.missing_id > 0 && (
          <div className="px-5 pt-4">
            <Callout tone="warning" title={`${plural(data.missing_id, "guest")} without an ID on file`}>
              Lead guests get an SMS reminder two days before arrival and their door code waits until the ID is in. Travel companions can be added from
              the guest&apos;s trip page or at check-in.
            </Callout>
          </div>
        )}
        {error ? (
          <div className="p-5">
            <ErrorBlock error={error} retry={refetch} />
          </div>
        ) : isLoading ? (
          <div className="p-5">
            <LoadingBlock rows={5} />
          </div>
        ) : (
          <div className={cn("transition-opacity", isFetching && "opacity-60")}>
            <Table
              head={["Booking", "Home", "Guest", "ID", "Nationality", "Phone", "Stay", "Arrived", "Left", "Vehicle"]}
              empty="Nobody stayed in these dates."
              className="[&_table]:min-w-[1120px]"
            >
              {rows.map((r, i) => (
                <Tr key={`${r.ref}-${i}`} className={cn(!r.id_last4 && "bg-warning-50/40")}>
                  <Td>
                    <Link href={reservationHref(r.ref)} className="font-mono text-[13px] font-semibold hover:underline">
                      {r.ref}
                    </Link>
                  </Td>
                  <Td className="max-w-40 truncate text-ink-2" title={r.address}>
                    {r.unit}
                  </Td>
                  <Td>
                    <span className="font-medium">{r.name}</span>
                    <span className="mt-0.5 flex gap-1">
                      {r.lead_guest && <Badge tone="ocean">Lead</Badge>}
                      {r.minor && <Badge tone="warning">Minor</Badge>}
                    </span>
                  </Td>
                  <Td className="whitespace-nowrap">
                    {r.id_last4 ? (
                      <>
                        <span className="text-[13px] text-ink-2">{ID_TYPES[r.id_type] ?? r.id_type}</span> <span className="font-mono text-[13px]">{r.id_last4}</span>
                      </>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[13px] font-semibold text-warning">
                        <TriangleAlert className="size-3.5" /> Missing
                      </span>
                    )}
                  </Td>
                  <Td className="whitespace-nowrap">
                    {r.nationality ? (
                      <span title={countryName(r.nationality)}>
                        {flag(r.nationality)} <span className="text-[13px] text-ink-2">{r.nationality}</span>
                      </span>
                    ) : (
                      <span className="text-ink-3">—</span>
                    )}
                  </Td>
                  <Td className="font-mono text-[12.5px] whitespace-nowrap text-ink-2">{r.phone || "—"}</Td>
                  <Td className="whitespace-nowrap">
                    {fmtDate(r.check_in, "d MMM")} → {fmtDate(r.check_out, "d MMM")}
                  </Td>
                  <Td className="whitespace-nowrap text-ink-2">{r.arrived_at ? fmtDateTime(r.arrived_at) : "—"}</Td>
                  <Td className="whitespace-nowrap text-ink-2">{r.left_at ? fmtDateTime(r.left_at) : "—"}</Td>
                  <Td className="font-mono text-[12.5px]">{r.vehicle || <span className="font-sans text-ink-3">—</span>}</Td>
                </Tr>
              ))}
            </Table>
          </div>
        )}
      </TableCard>
    </div>
  );
}

// ---------- TRA monthly return ----------

export function TraReturnTab() {
  const [month, setMonth] = React.useState(() => format(subMonths(new Date(), 1), "yyyy-MM"));
  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ["host", "tra-return", month],
    queryFn: () => get<TraReturn>(`/api/host/compliance/tra-return${qs({ month })}`),
    placeholderData: keepPreviousData,
    enabled: /^\d{4}-\d{2}$/.test(month),
  });
  const monthDate = parseISO(`${month}-01`);
  const due = new Date(addMonths(monthDate, 1).getFullYear(), addMonths(monthDate, 1).getMonth(), 10);
  const daysLeft = differenceInCalendarDays(due, new Date());
  const countries = Object.entries(data?.visitors_by_country ?? {}).sort((a, b) => b[1] - a[1]);
  const totalVisitors = countries.reduce((s, [, n]) => s + n, 0);
  const kenyan = data?.visitors_by_country.KE ?? 0;
  const maxCountry = Math.max(1, ...countries.map(([, n]) => n));
  const csv = `/api/host/compliance/tra-return${qs({ month, export: "csv" })}`;
  const download = (e: React.MouseEvent) => {
    e.preventDefault();
    if (!data) return;
    downloadCsv(csv, `tra-return-${month}.csv`, () =>
      toCsv([
        ["Month", data.month],
        ["Units", data.units],
        ["Occupancy", data.occupancy],
        ["Room nights sold", data.room_nights_sold],
        ["Room nights available", data.room_nights_available],
        ["Guest nights", data.guest_nights],
        ["Arrivals", data.arrivals],
        ["Room revenue", data.room_revenue],
        ["Tourism levy", data.tourism_levy],
        [],
        ["Country of origin", "Guests"],
        ...countries,
      ]),
    );
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4 rounded-2xl border border-line-soft bg-white p-5">
        <div className="flex flex-wrap items-end gap-4">
          <Field label="Return for">
            <Input type="month" value={month} onChange={(e) => setMonth(e.target.value)} max={format(new Date(), "yyyy-MM")} className="h-10 w-48" />
          </Field>
          <div
            className={cn(
              "flex items-center gap-2.5 rounded-xl px-3.5 py-2.5 text-[13.5px]",
              daysLeft < 0 ? "bg-surface text-ink-2" : daysLeft <= 5 ? "bg-warning-50 text-warning" : "bg-ocean-50 text-ocean-700",
            )}
          >
            <CalendarClock className="size-4 shrink-0" />
            <span>
              Levy & return due by the 10th — <b>{fmtDate(due, "EEE d MMM yyyy")}</b>
              {daysLeft >= 0 ? ` (${daysLeft === 0 ? "today" : plural(daysLeft, "day") + " left"})` : " (past)"}
            </span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="soft">
            <a href={`/api/host/invoices${qs({ month, export: "csv" })}`} download title="Every invoice and credit note issued this month — for KRA / eTIMS reconciliation">
              <FileSpreadsheet className="size-4" /> Sales register
            </a>
          </Button>
          <Button asChild variant="dark">
            <a href={csv} download onClick={download} aria-disabled={!data}>
              <FileSpreadsheet className="size-4" /> Download CSV
            </a>
          </Button>
        </div>
      </div>

      {error ? (
        <ErrorBlock error={error} retry={refetch} />
      ) : isLoading || !data ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      ) : (
        <div className={cn("grid gap-6 transition-opacity lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]", isFetching && "opacity-60")}>
          <section className="rounded-2xl border border-line-soft bg-white p-5">
            <h2 className="text-[15px] font-bold">{fmtDate(monthDate, "MMMM yyyy")} at a glance</h2>
            <p className="mt-0.5 text-[13px] text-ink-2">The figures the Tourism Regulatory Authority asks for each month.</p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <StatTile label="Units" value={data.units} hint="Listed homes" />
              <StatTile label="Occupancy" value={`${data.occupancy}%`} hint="Bed-nights sold ÷ available" />
              <StatTile label="Nights sold" value={data.room_nights_sold} hint={`of ${data.room_nights_available} available`} />
              <StatTile label="Guest nights" value={data.guest_nights} hint="Every occupant, every night" />
              <StatTile label="Arrivals" value={data.arrivals} hint="Stays starting this month" />
              <StatTile label="Room revenue" value={kes(data.room_revenue)} className="sm:col-span-2 xl:col-span-1" />
              <StatTile label="Tourism levy (2%)" value={kes(data.tourism_levy)} hint="Already collected from guests" className="border-brand-100 bg-brand-50/50 sm:col-span-2" />
            </div>
          </section>

          <section className="rounded-2xl border border-line-soft bg-white p-5">
            <h2 className="text-[15px] font-bold">Visitors by country</h2>
            <p className="mt-0.5 text-[13px] text-ink-2">
              {totalVisitors ? `${plural(totalVisitors, "guest")} · ${Math.round((kenyan / totalVisitors) * 100)}% Kenyan residents` : "No guests this month."}
            </p>
            <ul className="mt-4 space-y-2.5">
              {countries.map(([code, n]) => (
                <li key={code} className="flex items-center gap-3 text-[14px]">
                  <span className="w-6 text-center text-lg leading-none" aria-hidden>
                    {code.length === 2 ? flag(code) : "🌍"}
                  </span>
                  <span className="w-32 truncate font-medium">{code.length === 2 ? countryName(code) : code}</span>
                  <span className="h-2 flex-1 overflow-hidden rounded-full bg-line-soft">
                    <span className="block h-full rounded-full bg-ocean-500" style={{ width: `${(n / maxCountry) * 100}%` }} />
                  </span>
                  <span className="w-8 text-right font-semibold tabular-nums">{n}</span>
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}
      <p className="flex items-start gap-2 text-[12.5px] text-ink-2">
        <Info className="mt-0.5 size-3.5 shrink-0" /> On the 5th of each month Amina gets an SMS reminder with last month&apos;s levy total. File the return on the TRA portal with
        the CSV above.
      </p>
    </div>
  );
}

// ---------- checklist ----------

type CheckState = "ok" | "warn" | "fail" | "info";

interface Check {
  key: string;
  title: string;
  why: string;
  state: CheckState;
  value: string;
}

function buildChecks(s: HostSettings): Check[] {
  const expiry = s.tra_licence_expiry ? differenceInCalendarDays(parseISO(s.tra_licence_expiry), new Date()) : null;
  const levy = Number(s.tourism_levy_percent);
  return [
    {
      key: "tra",
      title: "TRA licence number",
      why: "Shown on every listing and booking page (Tourism Enterprises Regulations 2025, r.19).",
      state: s.tra_licence_number ? "ok" : "fail",
      value: s.tra_licence_number || "Not set",
    },
    {
      key: "tra_expiry",
      title: "TRA licence valid",
      why: "Renew at least 45 days before it lapses — operating unlicensed risks closure.",
      state: expiry === null ? "fail" : expiry < 0 ? "fail" : expiry < 45 ? "warn" : "ok",
      value:
        expiry === null || !s.tra_licence_expiry
          ? "No expiry date"
          : expiry < 0
            ? `Expired ${fmtDate(s.tra_licence_expiry, "d MMM yyyy")}`
            : `Expires ${fmtDate(s.tra_licence_expiry, "d MMM yyyy")} · ${plural(expiry, "day")} left`,
    },
    {
      key: "odpc",
      title: "ODPC registration",
      why: "Data controllers handling guest IDs must register with the Data Commissioner (Data Protection Act 2019).",
      state: s.odpc_registration ? "ok" : "fail",
      value: s.odpc_registration || "Not set",
    },
    { key: "kra", title: "KRA PIN", why: "Needed for income tax, the tourism levy and any VAT filings.", state: s.kra_pin ? "ok" : "warn", value: s.kra_pin || "Not set" },
    {
      key: "levy",
      title: "Tourism levy",
      why: "2% of accommodation is added to every quote and reported monthly.",
      state: levy > 0 ? "ok" : "warn",
      value: `${levy}% on every booking`,
    },
    {
      key: "retention",
      title: "Guest register retention",
      why: "r.26 requires 5 years; after that ID numbers are erased automatically.",
      state: s.id_retention_days >= 1825 ? "ok" : "warn",
      value: `${s.id_retention_days} days (${(s.id_retention_days / 365).toFixed(1)} years)`,
    },
    {
      key: "id_code",
      title: "ID before door code",
      why: "No door code until the guest-register ID is in — the register stays complete.",
      state: s.require_id_before_code ? "ok" : "warn",
      value: s.require_id_before_code ? "On" : "Off",
    },
    {
      key: "simswap",
      title: "SIM-swap check",
      why: "Africa's Talking Insights flags a recently swapped SIM before a door code is sent.",
      state: s.sim_swap_check ? "ok" : "warn",
      value: s.sim_swap_check ? "On" : "Off",
    },
    {
      key: "vat",
      title: "VAT",
      why: "Register once taxable supplies pass KES 5m in 12 months; VAT is then added to quotes.",
      state: "info",
      value: s.vat_registered ? `Registered · ${Number(s.vat_percent)}%` : "Not registered",
    },
  ];
}

const STATE_META: Record<CheckState, { icon: React.ComponentType<{ className?: string }>; cls: string; label: string }> = {
  ok: { icon: CircleCheck, cls: "text-success", label: "Done" },
  warn: { icon: TriangleAlert, cls: "text-warning", label: "Check" },
  fail: { icon: CircleAlert, cls: "text-danger", label: "Missing" },
  info: { icon: Info, cls: "text-ink-2", label: "Info" },
};

export function ChecklistTab() {
  const { data: s, isLoading, error, refetch } = useHostSettings();
  if (error) return <ErrorBlock error={error} retry={refetch} />;
  if (isLoading || !s) return <LoadingBlock rows={6} />;
  const checks = buildChecks(s);
  const scored = checks.filter((c) => c.state !== "info");
  const passing = scored.filter((c) => c.state === "ok").length;
  const pct = Math.round((passing / scored.length) * 100);

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
      <section className="overflow-hidden rounded-2xl border border-line-soft bg-white">
        <ul className="divide-y divide-line-soft">
          {checks.map((c) => {
            const m = STATE_META[c.state];
            return (
              <li key={c.key} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-4">
                <m.icon className={cn("size-5 shrink-0", m.cls)} aria-label={m.label} />
                <div className="min-w-0 flex-1 basis-64">
                  <p className="text-[15px] font-semibold">{c.title}</p>
                  <p className="text-[13px] text-ink-2">{c.why}</p>
                </div>
                <span className={cn("font-mono text-[13px]", c.state === "fail" ? "text-danger" : c.state === "warn" ? "text-warning" : "text-ink")}>{c.value}</span>
                <Link href="/host/settings#compliance" className="inline-flex items-center gap-1 text-[13px] font-semibold text-ink-2 hover:text-ink" aria-label={`Edit ${c.title} in Settings`}>
                  Settings <ArrowRight className="size-3.5" />
                </Link>
              </li>
            );
          })}
        </ul>
      </section>
      <aside className="space-y-4 lg:sticky lg:top-6 lg:self-start">
        <div className="rounded-2xl border border-line-soft bg-white p-5">
          <p className="text-[13px] font-semibold text-ink-2">Compliance score</p>
          <p className="mt-1 text-4xl font-bold tracking-tight tabular-nums">
            {passing}
            <span className="text-xl font-semibold text-ink-3">/{scored.length}</span>
          </p>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-line-soft">
            <div className={cn("h-full rounded-full transition-all", pct === 100 ? "bg-success" : pct >= 70 ? "bg-ocean-500" : "bg-warning")} style={{ width: `${pct}%` }} />
          </div>
          <p className="mt-3 text-[13px] text-ink-2">{pct === 100 ? "Everything a TRA inspection or ODPC audit looks for is in place." : "Fix the flagged items in Settings → Business & policies."}</p>
          <Button asChild variant="dark" className="mt-4 w-full">
            <Link href="/host/settings#compliance">Open settings</Link>
          </Button>
        </div>
      </aside>
    </div>
  );
}
